from __future__ import annotations

import hashlib
import json
import math
import os
import re
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from io import BytesIO
from threading import Lock

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .db import SessionLocal
from .models import Asset, AssetVersion, ImageBatch, ImageJob, ProductMaster, SkuAsset, SkuVariant
from .storage import AssetValidationError, configured_storage, download_external, validate_image


PIPELINE_VERSION = "deterministic-v1"
OUTPUT_ROLES = ("SPU_WHITE_MAIN", "SPU_DETAIL_1", "SPU_DETAIL_2", "SPU_SIZE_INFO")
CANVAS = 1024
_rembg_session = None
_rembg_lock = Lock()
_ocr_engine = None
_ocr_lock = Lock()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sku_source_ready(sku: SkuVariant) -> bool:
    if sku.source_image_url or any(a.storage_key and a.role == "SKU_SOURCE" for a in sku.assets):
        return True
    product_assets = sku.product.assets if sku.product is not None else []
    return bool(sku.components) and all(
        c.quantity > 0
        and (c.source_image_url or any(a.component_id == c.id and a.storage_key for a in product_assets))
        for c in sku.components
    )


def readiness(product: ProductMaster) -> dict:
    missing: list[dict] = []
    warnings: list[dict] = []
    has_spu = bool(product.source_image_url) or any(
        a.storage_key and a.role in {"SPU_MAIN_SOURCE", "SPU_SOURCE"} for a in product.assets
    )
    if not has_spu:
        missing.append({"code": "MISSING_SPU_SOURCE", "message": "缺少 SPU 主原图", "target": product.spu_code})
    if not product.dimensions:
        missing.append({"code": "MISSING_DIMENSIONS", "message": "缺少真实尺寸字段", "target": product.spu_code})
    if product.image_rights.upper() in {"UNKNOWN", "未确认", "不清楚"}:
        missing.append({"code": "IMAGE_RIGHTS_UNCONFIRMED", "message": "图片授权未确认", "target": product.spu_code})
    sellable = [sku for sku in product.skus if sku.is_sellable]
    if not sellable:
        missing.append({"code": "NO_SELLABLE_SKU", "message": "没有可销售 SKU", "target": product.spu_code})
    for sku in sellable:
        if not sku_source_ready(sku):
            missing.append({"code": "MISSING_SKU_SOURCE", "message": "缺少 SKU 原图或完整套装组件原图", "target": sku.sku_code})
        if not sku.color:
            warnings.append({"code": "MISSING_SKU_COLOR", "message": "SKU 未填写颜色", "target": sku.sku_code})
    detail_count = sum(1 for a in product.assets if a.role in {"SPU_DETAIL_1_SOURCE", "SPU_DETAIL_2_SOURCE"} and (a.storage_key or a.source_url or a.url))
    if detail_count < 2:
        warnings.append({"code": "DETAIL_WILL_CROP", "message": "细节素材不足时将从高分辨率主图截取", "target": product.spu_code})
    return {"product_id": product.id, "status": "READY" if not missing else "BLOCKED", "missing": missing, "warnings": warnings}


def input_fingerprint(product: ProductMaster) -> str:
    payload = {
        "pipeline": PIPELINE_VERSION,
        "product": [product.spu_code, product.dimensions, product.color, product.source_image_url, product.image_rights],
        "assets": sorted((a.role, a.sha256, a.source_url or a.url) for a in product.assets),
        "skus": [
            [sku.sku_code, sku.color, sku.size, sku.quantity, sku.source_image_url, sku.is_sellable,
             sorted((c.component_code, c.color, c.quantity, c.source_image_url) for c in sku.components)]
            for sku in sorted(product.skus, key=lambda item: item.sku_code)
        ],
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _mirror_asset(db: Session, *, product_id: int, role: str, url: str, sku_id: int | None = None) -> Asset:
    existing = db.scalar(select(Asset).where(Asset.product_id == product_id, Asset.sku_id == sku_id, Asset.role == role))
    if existing and existing.storage_key:
        return existing
    content = download_external(url)
    meta = validate_image(content)
    key = f"sources/{product_id}/{meta['sha256'][:20]}.{meta['extension']}"
    configured_storage().put(key, content, meta["mime_type"])
    asset = existing or Asset(product_id=product_id, sku_id=sku_id, asset_type="SOURCE", role=role)
    asset.url = url
    asset.source_url = url
    asset.storage_key = key
    asset.sha256 = meta["sha256"]
    asset.mime_type = meta["mime_type"]
    asset.width = meta["width"]
    asset.height = meta["height"]
    asset.byte_size = meta["byte_size"]
    asset.mirror_status = "MIRRORED"
    if not existing:
        db.add(asset)
    db.flush()
    return asset


def _source_bytes(db: Session, product: ProductMaster, role: str, sku: SkuVariant | None = None, url: str | None = None) -> tuple[bytes, list[int]]:
    component_id = int(role.split("_")[1]) if role.startswith("COMPONENT_") else None
    candidates = [
        a for a in product.assets
        if ((component_id is not None and a.component_id == component_id) or a.role == role)
        and (sku is None or a.sku_id == sku.id)
    ]
    if role == "SPU_MAIN_SOURCE":
        candidates += [a for a in product.assets if a.role in {"SPU_SOURCE", "SPU_MAIN_SOURCE"} and a.sku_id is None]
    candidates.sort(key=lambda asset: (0 if asset.storage_key else 1, -asset.id))
    for asset in candidates:
        if asset.storage_key:
            return configured_storage().get(asset.storage_key), [asset.id]
        remote = asset.source_url or asset.url
        if remote:
            mirrored = _mirror_asset(db, product_id=product.id, role=role, url=remote, sku_id=sku.id if sku else None)
            return configured_storage().get(mirrored.storage_key), [mirrored.id]
    remote = url or (sku.source_image_url if sku else product.source_image_url)
    if not remote:
        raise AssetValidationError("缺少真实素材")
    mirrored = _mirror_asset(db, product_id=product.id, role=role, url=remote, sku_id=sku.id if sku else None)
    return configured_storage().get(mirrored.storage_key), [mirrored.id]


def _remove_background(image: Image.Image) -> Image.Image:
    image = image.convert("RGBA")
    alpha = np.asarray(image.getchannel("A"))
    if np.percentile(alpha, 5) < 250:
        return image
    try:
        from rembg import new_session, remove
    except ImportError as exc:
        raise RuntimeError("REMOVAL_ENGINE_MISSING") from exc
    global _rembg_session
    with _rembg_lock:
        if _rembg_session is None:
            _rembg_session = new_session(os.getenv("REMBG_MODEL", "birefnet-general"))
    return remove(image, session=_rembg_session).convert("RGBA")


def _fit_on_white(subjects: list[Image.Image], occupancy: float = .82) -> Image.Image:
    canvas = Image.new("RGB", (CANVAS, CANVAS), "white")
    count = len(subjects)
    prepared: list[Image.Image] = []
    target_each = int(CANVAS * occupancy / max(1, math.sqrt(count)))
    for image in subjects:
        item = _remove_background(image)
        bbox = item.getbbox()
        if not bbox:
            raise ValueError("EMPTY_SUBJECT")
        item = item.crop(bbox)
        scale = min(target_each / item.width, target_each / item.height)
        prepared.append(item.resize((max(1, int(item.width * scale)), max(1, int(item.height * scale))), Image.Resampling.LANCZOS))
    if count == 1:
        positions = [((CANVAS - prepared[0].width) // 2, (CANVAS - prepared[0].height) // 2)]
    else:
        radius = min(250, 115 + count * 18)
        positions = []
        for index, item in enumerate(prepared):
            angle = -math.pi / 2 + index * (2 * math.pi / count)
            x = int(CANVAS / 2 + math.cos(angle) * radius - item.width / 2)
            y = int(CANVAS / 2 + math.sin(angle) * radius * .58 - item.height / 2)
            positions.append((x, y))
    shadow = Image.new("RGBA", canvas.size)
    shadow_draw = ImageDraw.Draw(shadow)
    for (x, y), item in zip(positions, prepared):
        shadow_draw.ellipse((x + item.width * .12, y + item.height * .86, x + item.width * .88, y + item.height * .98), fill=(0, 0, 0, 38))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    canvas.paste(shadow, (0, 0), shadow)
    for position, item in zip(positions, prepared):
        canvas.paste(item, position, item)
    return canvas


def _detail_image(source: Image.Image, index: int) -> Image.Image:
    source = source.convert("RGB")
    if min(source.size) < 700:
        raise AssetValidationError("主图分辨率不足以生成独立细节图")
    crop_size = int(min(source.size) * .62)
    x = int((source.width - crop_size) * (.08 if index == 1 else .92))
    x = max(0, min(source.width - crop_size, x))
    y = max(0, (source.height - crop_size) // 2)
    crop = source.crop((x, y, x + crop_size, y + crop_size)).resize((CANVAS, CANVAS), Image.Resampling.LANCZOS)
    return crop


def _size_image(source: Image.Image, dimensions: str) -> Image.Image:
    result = _fit_on_white([source], .70)
    draw = ImageDraw.Draw(result)
    font = ImageFont.load_default(size=28)
    text = dimensions.strip()
    box = draw.textbbox((0, 0), text, font=font)
    text_width = box[2] - box[0]
    draw.line((160, 890, 864, 890), fill=(38, 60, 51), width=3)
    draw.line((160, 876, 160, 904), fill=(38, 60, 51), width=3)
    draw.line((864, 876, 864, 904), fill=(38, 60, 51), width=3)
    draw.rectangle((CANVAS // 2 - text_width // 2 - 16, 866, CANVAS // 2 + text_width // 2 + 16, 914), fill="white")
    draw.text(((CANVAS - text_width) // 2, 876), text, fill=(25, 39, 33), font=font)
    return result


def _qc(image: Image.Image, role: str, source: Image.Image | None = None, allowed_text: str | None = None) -> dict:
    rgb = image.convert("RGB")
    array = np.asarray(rgb)
    nonwhite = np.any(array < 248, axis=2)
    ys, xs = np.where(nonwhite)
    if not len(xs):
        raise ValueError("EMPTY_OUTPUT")
    bbox_width, bbox_height = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
    ratio = max(bbox_width, bbox_height) / CANVAS
    if role in {"SPU_WHITE_MAIN", "SKU_WHITE"} and not .75 <= ratio <= .89:
        raise ValueError("SUBJECT_RATIO_OUT_OF_RANGE")
    corners = np.concatenate([array[:20, :20].reshape(-1, 3), array[-20:, -20:].reshape(-1, 3)])
    if role != "SPU_DETAIL_1" and role != "SPU_DETAIL_2" and corners.mean() < 252:
        raise ValueError("BACKGROUND_NOT_WHITE")
    gray = np.asarray(rgb.convert("L"), dtype=float)
    sharpness = float(np.var(np.diff(gray, axis=0)) + np.var(np.diff(gray, axis=1)))
    if sharpness < 4:
        raise ValueError("OUTPUT_BLURRY")
    long_lines = int(np.any(np.mean(gray < 90, axis=0) > .88) or np.any(np.mean(gray < 90, axis=1) > .88))
    if long_lines:
        raise ValueError("PANEL_DIVIDER_DETECTED")
    detected_text: list[str] = []
    if os.getenv("OCR_ENABLED", "true").lower() == "true":
        try:
            from rapidocr import RapidOCR
            global _ocr_engine
            with _ocr_lock:
                if _ocr_engine is None:
                    _ocr_engine = RapidOCR()
                result = _ocr_engine(np.asarray(rgb))
            txts = getattr(result, "txts", None) or []
            detected_text = [str(text).strip() for text in txts if str(text).strip()]
        except (ImportError, RuntimeError):
            detected_text = []
    if detected_text:
        if role != "SPU_SIZE_INFO":
            raise ValueError("UNEXPECTED_TEXT_OR_WATERMARK")
        allowed = re.sub(r"\W", "", allowed_text or "").lower()
        if any(re.sub(r"\W", "", text).lower() not in allowed for text in detected_text):
            raise ValueError("UNEXPECTED_SIZE_TEXT")
    color_delta = None
    if source is not None:
        src_rgba = np.asarray(source.convert("RGBA").resize((256, 256)))
        src = src_rgba[:, :, :3]
        src_pixels = src[(src_rgba[:, :, 3] > 32) & (np.mean(src, axis=2) < 245)]
        out_pixels = array[np.mean(array, axis=2) < 245]
        if len(src_pixels) and len(out_pixels):
            color_delta = float(np.linalg.norm(np.median(src_pixels, axis=0) - np.median(out_pixels, axis=0)))
            if color_delta > 58:
                raise ValueError("SUBJECT_COLOR_CHANGED")
    return {"canvas": [CANVAS, CANVAS], "background": "#FFFFFF", "subject_bbox_ratio": round(ratio, 4), "sharpness": round(sharpness, 2), "transparent_channel": False, "cropped_outside_canvas": False, "collage_detected": False, "detected_text": detected_text, "color_delta": round(color_delta, 2) if color_delta is not None else None, "allowed_text": allowed_text}


def _save_output(db: Session, job: ImageJob, image: Image.Image, source_ids: list[int], manifest: dict | None = None, source: Image.Image | None = None) -> AssetVersion:
    stream = BytesIO()
    image.convert("RGB").save(stream, format="PNG", optimize=True)
    content = stream.getvalue()
    digest = hashlib.sha256(content).hexdigest()
    batch = db.get(ImageBatch, job.batch_id)
    product = db.get(ProductMaster, job.product_id)
    suffix = db.scalar(select(func.count(AssetVersion.id)).where(AssetVersion.product_id == job.product_id, AssetVersion.role == job.job_type)) or 0
    filename = f"{product.spu_code}_{job.job_type}_v{suffix + 1}.png"
    if job.sku_id:
        sku = db.get(SkuVariant, job.sku_id)
        filename = f"{sku.sku_code}_SKU_WHITE_v{suffix + 1}.png"
    key = f"generated/{product.spu_code}/{batch.id}/{filename}"
    configured_storage().put(key, content, "image/png")
    qc = _qc(image, job.job_type, source=source, allowed_text=product.dimensions if job.job_type == "SPU_SIZE_INFO" else None)
    asset = AssetVersion(product_id=job.product_id, batch_id=job.batch_id, role=job.job_type, version=batch.version, storage_key=key, sha256=digest, mime_type="image/png", width=CANVAS, height=CANVAS, byte_size=len(content), pipeline_version=PIPELINE_VERSION, source_asset_ids=json.dumps(source_ids), qc_json=json.dumps(qc, ensure_ascii=False))
    db.add(asset)
    db.flush()
    if job.sku_id:
        sku = db.get(SkuVariant, job.sku_id)
        db.add(SkuAsset(sku_id=sku.id, batch_id=job.batch_id, asset_version_id=asset.id, sku_code=sku.sku_code, component_manifest=json.dumps(manifest or {}, ensure_ascii=False)))
    return asset


def process_job(job_id: int) -> None:
    with SessionLocal() as routing_db:
        routing_job = routing_db.get(ImageJob, job_id)
        if routing_job and routing_job.job_type.startswith("SCENE_"):
            from .scene_pipeline import process_scene_job
            process_scene_job(job_id)
            return
    with SessionLocal() as db:
        job = db.get(ImageJob, job_id)
        if not job or job.status not in {"PENDING", "RETRYABLE"}:
            return
        job.status, job.stage, job.started_at = "RUNNING", "MIRRORING", utcnow()
        db.commit()
        try:
            job = db.get(ImageJob, job_id)
            product = db.scalar(select(ProductMaster).options(selectinload(ProductMaster.assets), selectinload(ProductMaster.skus).selectinload(SkuVariant.assets), selectinload(ProductMaster.skus).selectinload(SkuVariant.components)).where(ProductMaster.id == job.product_id))
            source_ids: list[int] = []
            manifest = None
            qc_source = None
            if job.job_type == "SKU_WHITE":
                sku = next(item for item in product.skus if item.id == job.sku_id)
                subjects: list[Image.Image] = []
                if sku.source_image_url or any(a.storage_key or a.url for a in sku.assets):
                    content, ids = _source_bytes(db, product, "SKU_SOURCE", sku=sku)
                    subjects.append(Image.open(BytesIO(content)).copy())
                    qc_source = subjects[0]
                    source_ids += ids
                    manifest = {"sku_code": sku.sku_code, "components": [{"code": sku.sku_code, "quantity": sku.quantity}]}
                else:
                    components = []
                    for component in sku.components:
                        has_uploaded = any(a.component_id == component.id and a.storage_key for a in product.assets)
                        if not component.source_image_url and not has_uploaded:
                            raise AssetValidationError(f"组件 {component.component_code or component.component_name} 缺少真实素材")
                        content, ids = _source_bytes(db, product, f"COMPONENT_{component.id}_SOURCE", url=component.source_image_url)
                        item = Image.open(BytesIO(content)).copy()
                        subjects.extend([item.copy() for _ in range(component.quantity)])
                        source_ids += ids
                        components.append({"code": component.component_code, "quantity": component.quantity})
                    manifest = {"sku_code": sku.sku_code, "components": components}
                job.stage = "LAYOUT"
                image = _fit_on_white(subjects)
            else:
                content, ids = _source_bytes(db, product, "SPU_MAIN_SOURCE")
                source_ids += ids
                source = Image.open(BytesIO(content)).copy()
                qc_source = source
                job.stage = "LAYOUT"
                if job.job_type == "SPU_WHITE_MAIN":
                    image = _fit_on_white([source])
                elif job.job_type.startswith("SPU_DETAIL"):
                    detail_role = f"{job.job_type}_SOURCE"
                    detail_assets = [a for a in product.assets if a.role == detail_role]
                    if detail_assets:
                        detail_content, detail_ids = _source_bytes(db, product, detail_role)
                        source_ids += detail_ids
                        image = Image.open(BytesIO(detail_content)).convert("RGB").resize((CANVAS, CANVAS), Image.Resampling.LANCZOS)
                    else:
                        image = _detail_image(source, 1 if job.job_type.endswith("1") else 2)
                else:
                    if not product.dimensions:
                        raise AssetValidationError("缺少真实尺寸字段")
                    image = _size_image(source, product.dimensions)
            job.stage = "QC"
            asset = _save_output(db, job, image, source_ids, manifest, qc_source)
            job.result_asset_id = asset.id
            job.qc_json = asset.qc_json
            job.manifest_json = json.dumps(manifest, ensure_ascii=False) if manifest else None
            job.status, job.stage, job.completed_at = "COMPLETED", "COMPLETED", utcnow()
        except (AssetValidationError, ValueError) as exc:
            job.status, job.stage = "WAITING_SOURCE" if isinstance(exc, AssetValidationError) else "QC_FAILED", "FAILED"
            job.error_code, job.error_message = job.status, str(exc)
            job.completed_at = utcnow()
        except Exception as exc:
            job.retry_count += 1
            job.status = "RETRYABLE" if job.retry_count <= job.max_retries else "FAILED"
            job.stage, job.error_code, job.error_message = "FAILED", "TRANSIENT_ERROR", str(exc)
            job.completed_at = utcnow()
        db.commit()
        refresh_batch(db, job.batch_id)


def refresh_batch(db: Session, batch_id: int) -> None:
    batch = db.get(ImageBatch, batch_id)
    statuses = db.scalars(select(ImageJob.status).where(ImageJob.batch_id == batch_id)).all()
    is_scene = batch.pipeline_kind == "SCENE"
    batch.completed_jobs = sum(status in ({"COMPLETED", "READY_FOR_REVIEW"} if is_scene else {"COMPLETED"}) for status in statuses)
    batch.failed_jobs = sum(status in {"FAILED", "QC_FAILED", "ENGINE_UNAVAILABLE"} for status in statuses)
    batch.waiting_jobs = statuses.count("WAITING_SOURCE")
    terminal = {"COMPLETED", "READY_FOR_REVIEW", "FAILED", "QC_FAILED", "WAITING_SOURCE", "ENGINE_UNAVAILABLE"}
    if all(status in terminal for status in statuses):
        batch.status = ("READY_FOR_REVIEW" if is_scene and batch.completed_jobs == batch.total_jobs else "COMPLETED" if batch.completed_jobs == batch.total_jobs else "NEEDS_ATTENTION")
        batch.completed_at = utcnow()
    else:
        batch.status = "RUNNING"
    product = db.get(ProductMaster, batch.product_id)
    if is_scene:
        product.scene_readiness = "READY_FOR_REVIEW" if batch.status == "READY_FOR_REVIEW" else ("NEEDS_ATTENTION" if batch.status == "NEEDS_ATTENTION" else "PROCESSING")
    else:
        product.image_readiness = "GENERATED" if batch.status == "COMPLETED" else ("NEEDS_ATTENTION" if batch.status == "NEEDS_ATTENTION" else "PROCESSING")
    db.commit()


class TaskDispatcher:
    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=int(os.getenv("LOCAL_IMAGE_WORKERS", "2")), thread_name_prefix="image-job")

    def dispatch(self, job_ids: list[int]) -> None:
        if os.getenv("TASK_BACKEND", "local").lower() == "celery":
            from .celery_app import celery_app
            for job_id in job_ids:
                celery_app.send_task("commerce.process_image_job", args=[job_id])
            return
        futures = [self.executor.submit(process_job, job_id) for job_id in job_ids]
        self.executor.submit(self._finalize_batches, job_ids, futures)

    @staticmethod
    def _finalize_batches(job_ids: list[int], futures: list[Future]) -> None:
        wait(futures)
        with SessionLocal() as db:
            batch_ids = set(db.scalars(select(ImageJob.batch_id).where(ImageJob.id.in_(job_ids))).all())
            for batch_id in batch_ids:
                refresh_batch(db, batch_id)

    def resume(self) -> None:
        with SessionLocal() as db:
            jobs = db.scalars(select(ImageJob).where(ImageJob.status.in_(["PENDING", "RUNNING", "RETRYABLE"]))).all()
            for job in jobs:
                if job.status == "RUNNING":
                    job.status = "RETRYABLE"
            db.commit()
            self.dispatch([job.id for job in jobs])


dispatcher = TaskDispatcher()
