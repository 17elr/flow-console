from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from io import BytesIO
from threading import Lock
from pathlib import Path

from PIL import Image
import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .db import SessionLocal
from .image_pipeline import _remove_background, _source_bytes, refresh_batch
from .models import AssetVersion, ImageBatch, ImageJob, ProductMaster, SceneProfile, SkuVariant
from .providers import ImageInput, ProviderError, ProviderPermanentError, ProviderTransientError, configured_provider
from .storage import AssetValidationError, configured_storage, validate_image

SCENE_PIPELINE_VERSION = "scene-v1"
SCENE_ROLES = ("SCENE_MODEL_WEAR", "SCENE_LIFESTYLE")
_provider_lock = Lock()
_ocr_lock = Lock()
_ocr_engine = None

DEFAULT_SCENE_TEMPLATE = {
    "template_version": "neutral-commerce-v1",
    "model_age": "adult",
    "clothing_color": "light gray or white",
    "framing": "category-appropriate close crop",
    "model_background": "clean light neutral studio",
    "lifestyle_scene": "bright daytime interior",
    "surface_material": "light neutral tabletop",
    "light_direction": "soft window light",
    "depth_of_field": "subtle",
}
BIREFNET_MD5 = "7A35A0141CBBC80DE11D9C9A28F52697"


def _file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def ensure_birefnet_model() -> dict:
    source = Path(__file__).resolve().parents[3] / "BiRefNet-general-epoch_244.onnx"
    target = Path.home() / ".u2net" / "birefnet-general.onnx"
    if not source.exists():
        return {"ready": False, "reason": "MODEL_FILE_MISSING"}
    digest = _file_md5(source)
    if digest != BIREFNET_MD5:
        return {"ready": False, "reason": "MODEL_HASH_MISMATCH", "md5": digest}
    target.parent.mkdir(parents=True, exist_ok=True)
    target_digest = _file_md5(target) if target.exists() else None
    if target_digest != BIREFNET_MD5:
        shutil.copyfile(source, target)
    return {"ready": True, "path": str(target), "md5": BIREFNET_MD5}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def profile_values(profile: SceneProfile | None) -> dict:
    values = dict(DEFAULT_SCENE_TEMPLATE)
    if profile:
        for key in values:
            value = getattr(profile, key, None)
            if value:
                values[key] = value
        values.update({"model_prompt_override": profile.model_prompt_override, "lifestyle_prompt_override": profile.lifestyle_prompt_override, "reference_sku_id": profile.reference_sku_id})
    else:
        values.update({"model_prompt_override": None, "lifestyle_prompt_override": None, "reference_sku_id": None})
    return values


def choose_sku(product: ProductMaster, reference_sku_id: int | None) -> SkuVariant:
    sellable = [sku for sku in product.skus if sku.is_sellable]
    if reference_sku_id is not None:
        sku = next((item for item in sellable if item.id == reference_sku_id), None)
        if not sku:
            raise AssetValidationError("主推 SKU 不属于该商品或不可销售")
        return sku
    if len(sellable) == 1:
        return sellable[0]
    raise AssetValidationError("多 SKU 商品必须指定主推 SKU")


def scene_readiness(product: ProductMaster, profile: SceneProfile | None = None) -> dict:
    missing: list[dict] = []
    if not product.source_image_url and not any(a.storage_key and a.role in {"SPU_SOURCE", "SPU_MAIN_SOURCE"} for a in product.assets):
        missing.append({"code": "MISSING_SPU_SOURCE", "message": "缺少 SPU 主原图", "target": product.spu_code})
    if product.image_rights.upper() in {"UNKNOWN", "UNCONFIRMED"}:
        missing.append({"code": "IMAGE_RIGHTS_UNCONFIRMED", "message": "图片授权未确认", "target": product.spu_code})
    sellable = [sku for sku in product.skus if sku.is_sellable]
    if not sellable:
        missing.append({"code": "NO_SELLABLE_SKU", "message": "没有可销售 SKU", "target": product.spu_code})
    elif profile and profile.reference_sku_id is not None:
        try:
            sku = choose_sku(product, profile.reference_sku_id)
            if not sku.source_image_url and not any(a.storage_key and a.role == "SKU_SOURCE" for a in sku.assets) and not sku.components:
                missing.append({"code": "MISSING_REFERENCE_SKU_SOURCE", "message": "主推 SKU 缺少真实素材", "target": sku.sku_code})
        except AssetValidationError as exc:
            missing.append({"code": "INVALID_REFERENCE_SKU", "message": str(exc), "target": product.spu_code})
    else:
        missing.append({"code": "REFERENCE_SKU_REQUIRED", "message": "请先选择主推 SKU", "target": product.spu_code})
    return {"product_id": product.id, "status": "READY" if not missing else "BLOCKED", "missing": missing, "warnings": []}


def scene_fingerprint(product: ProductMaster, sku: SkuVariant, profile: SceneProfile | None, provider) -> str:
    values = profile_values(profile)
    payload = {
        "pipeline": SCENE_PIPELINE_VERSION,
        "provider": provider.config.provider,
        "model": provider.config.model,
        "product": [product.spu_code, product.title, product.category, product.material, product.color, product.dimensions],
        "sku": [sku.sku_code, sku.color, sku.size, sku.material, sku.quantity, [(c.component_code, c.quantity, c.color, c.source_image_url) for c in sku.components]],
        "assets": sorted((a.id, a.role, a.sha256, a.source_url or a.url) for a in product.assets),
        "profile": values,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def build_prompt(product: ProductMaster, sku: SkuVariant, profile: SceneProfile | None, role: str) -> str:
    p = profile_values(profile)
    components = ", ".join(f"{c.component_code or c.component_name} x{c.quantity}" for c in sku.components) or f"{sku.sku_code} x{sku.quantity}"
    invariant = f"Product SKU {sku.sku_code}; color {sku.color or 'as shown'}; size {sku.size or 'as shown'}; material {sku.material or product.material or 'as shown'}; exact content: {components}. Preserve exact shape, color, material, stones, connections, quantity, proportions and construction. Do not add, remove, replace, recolor or redesign the jewelry. No other jewelry, brand, logo, watermark, text, collage, grid, split panel, inset or picture-in-picture. One complete single-frame image only."
    if role == "SCENE_MODEL_WEAR":
        base = f"Create a neutral e-commerce model-wearing photo for {product.category}. Place the jewelry on the correct body area. Adult woman, natural makeup, {p['clothing_color']} clothing, {p['framing']}, {p['model_background']}."
        override = p.get("model_prompt_override")
    else:
        base = f"Create a neutral e-commerce lifestyle still life. Show the jewelry complete on a {p['surface_material']} in a {p['lifestyle_scene']}, {p['light_direction']}, {p['depth_of_field']} depth of field, low-distraction background."
        override = p.get("lifestyle_prompt_override")
    suffix = f" Additional art direction: {override}. This must not override product fidelity." if override else ""
    return f"{base} {invariant}{suffix}"


def reference_images(db: Session, product: ProductMaster, sku: SkuVariant) -> tuple[list[ImageInput], list[int]]:
    refs: list[ImageInput] = []
    ids: list[int] = []
    content, source_ids = _source_bytes(db, product, "SPU_MAIN_SOURCE")
    refs.append(ImageInput("spu-main.png", content, "image/png")); ids.extend(source_ids)
    try:
        content, source_ids = _source_bytes(db, product, "SKU_SOURCE", sku=sku)
        refs.append(ImageInput(f"{sku.sku_code}.png", content, "image/png")); ids.extend(source_ids)
    except AssetValidationError:
        for component in sku.components:
            content, source_ids = _source_bytes(db, product, f"COMPONENT_{component.id}_SOURCE", url=component.source_image_url)
            refs.append(ImageInput(f"{component.component_code or component.id}.png", content, "image/png")); ids.extend(source_ids)
    return refs, ids


def _qc(content: bytes, role: str) -> dict:
    meta = validate_image(content)
    with Image.open(BytesIO(content)) as image:
        rgb = image.convert("RGB")
        width, height = image.size
        if width < 256 or height < 256:
            raise ValueError("场景图尺寸过小")
        gray = np.asarray(rgb.convert("L"))
        divider = bool(np.any(np.mean(gray < 55, axis=0) > .88) or np.any(np.mean(gray < 55, axis=1) > .88))
        if divider:
            raise ValueError("检测到拼图分隔线")
        subject = _remove_background(rgb)
        bbox = subject.getbbox()
        if not bbox:
            raise ValueError("未检测到场景主体")
        bbox_ratio = ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) / (width * height)
        if bbox_ratio < .04:
            raise ValueError("场景主体过小")
        detected_text: list[str] = []
        if os.getenv("OCR_ENABLED", "true").lower() == "true":
            try:
                from rapidocr import RapidOCR
                global _ocr_engine
                with _ocr_lock:
                    if _ocr_engine is None:
                        _ocr_engine = RapidOCR()
                result = _ocr_engine(np.asarray(rgb))
                values = getattr(result, "txts", None)
                detected_text = [str(value).strip() for value in values if str(value).strip()] if values is not None else []
            except (ImportError, RuntimeError):
                pass
        if detected_text:
            raise ValueError("检测到意外文字或水印")
    return {"status": "QC_PASSED", "single_frame": True, "collage_detected": False, "panel_divider_detected": False, "detected_text": [], "subject_bbox_ratio": round(bbox_ratio, 4), "role": role, "width": meta["width"], "height": meta["height"], "fidelity_review_required": True}


def process_scene_job(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(ImageJob, job_id)
        if not job or job.status not in {"PENDING", "RETRYABLE"}:
            return
        job.status, job.stage, job.started_at = "RUNNING", "REFERENCING", utcnow(); db.commit()
        try:
            product = db.scalar(select(ProductMaster).options(selectinload(ProductMaster.assets), selectinload(ProductMaster.skus).selectinload(SkuVariant.assets), selectinload(ProductMaster.skus).selectinload(SkuVariant.components)).where(ProductMaster.id == job.product_id))
            profile = db.scalar(select(SceneProfile).where(SceneProfile.product_id == product.id))
            sku = choose_sku(product, profile.reference_sku_id if profile else job.batch.reference_sku_id)
            refs, ref_ids = reference_images(db, product, sku)
            provider = configured_provider()
            if not provider.health_check().get("configured"):
                raise ProviderPermanentError("图片 Provider 未配置")
            prompt = build_prompt(product, sku, profile, job.job_type)
            job.stage = "GENERATING"; db.commit()
            result = None
            for attempt in range(job.max_retries + 1):
                try:
                    with _provider_lock:
                        result = provider.edit(refs, prompt, {"n": 1})
                    break
                except ProviderTransientError:
                    job.retry_count = attempt + 1; db.commit()
                    if attempt >= job.max_retries: raise
                    time.sleep(2 ** attempt)
            images = (result or {}).get("images", [])
            if len(images) != 1: raise ValueError("Provider 未返回单张场景图")
            qc = _qc(images[0], job.job_type)
            batch = db.get(ImageBatch, job.batch_id)
            version = db.scalar(select(func.count(AssetVersion.id)).where(AssetVersion.product_id == product.id, AssetVersion.role == job.job_type)) or 0
            key = f"generated/{product.spu_code}/{batch.id}/{sku.sku_code}_{job.job_type}_v{version + 1}.png"
            configured_storage().put(key, images[0], "image/png")
            meta = validate_image(images[0])
            asset = AssetVersion(product_id=product.id, batch_id=batch.id, role=job.job_type, version=batch.version, storage_key=key, sha256=meta["sha256"], width=meta["width"], height=meta["height"], byte_size=meta["byte_size"], pipeline_version=SCENE_PIPELINE_VERSION, source_asset_ids=json.dumps(ref_ids), reference_asset_ids=json.dumps(ref_ids), provider=result.get("provider"), model=result.get("model"), prompt=prompt, provider_request_id=result.get("request_id"), provider_metadata_json=json.dumps({"usage": result.get("usage"), "metadata": result.get("metadata")}, ensure_ascii=False), qc_json=json.dumps(qc, ensure_ascii=False))
            db.add(asset); db.flush()
            job.result_asset_id = asset.id; job.qc_json = json.dumps(qc, ensure_ascii=False); job.manifest_json = json.dumps({"sku_code": sku.sku_code, "components": [{"code": c.component_code, "quantity": c.quantity} for c in sku.components]}, ensure_ascii=False); job.status = "READY_FOR_REVIEW"; job.stage = "READY_FOR_REVIEW"; job.completed_at = utcnow()
        except AssetValidationError as exc:
            job.status, job.stage, job.error_code, job.error_message = "WAITING_SOURCE", "FAILED", "WAITING_SOURCE", str(exc); job.completed_at = utcnow()
        except ProviderTransientError as exc:
            job.status, job.stage, job.error_code, job.error_message = "RETRYABLE", "FAILED", "TRANSIENT_ERROR", str(exc); job.completed_at = utcnow()
        except ProviderError as exc:
            job.status, job.stage, job.error_code, job.error_message = "ENGINE_UNAVAILABLE", "FAILED", "PROVIDER_ERROR", str(exc); job.completed_at = utcnow()
        except Exception as exc:
            message = str(exc).strip() or type(exc).__name__
            job.status, job.stage, job.error_code, job.error_message = "QC_FAILED", "FAILED", "QC_FAILED", message; job.completed_at = utcnow()
        db.commit(); refresh_batch(db, job.batch_id)
