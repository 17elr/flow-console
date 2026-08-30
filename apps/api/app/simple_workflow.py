from __future__ import annotations

import csv
import io
import json
import zipfile

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .image_pipeline import OUTPUT_ROLES, PIPELINE_VERSION, dispatcher, input_fingerprint, readiness
from .models import AssetVersion, ImageBatch, ImageJob, MiaoshouDraft, ProductMaster, SceneProfile, SkuAsset, Store, ProductPackagingSelection, PackagingPreset
from .providers import configured_provider
from .scene_pipeline import SCENE_PIPELINE_VERSION, SCENE_ROLES, scene_fingerprint, scene_readiness
from .storage import configured_storage
from .copywriting import copy_payload
from .reviews import review_payload


def source_slots(product: ProductMaster) -> list[dict]:
    def local_asset(role: str, *, sku_id: int | None = None, component_id: int | None = None):
        candidates = [
            asset
            for asset in product.assets
            if asset.role == role
            and (sku_id is None or asset.sku_id == sku_id)
            and (component_id is None or asset.component_id == component_id)
        ]
        return sorted(candidates, key=lambda item: item.id, reverse=True)[0] if candidates else None

    main = local_asset("SPU_MAIN_SOURCE") or local_asset("SPU_SOURCE")
    slots = [{"slot": "spu-main", "label": "商品主原图", "required": True, "status": "UPLOADED" if main or product.source_image_url else "MISSING", "asset": main, "target": product.spu_code}]
    for number in (1, 2):
        role = f"SPU_DETAIL_{number}_SOURCE"
        asset = local_asset(role)
        slots.append({"slot": f"spu-detail-{number}", "label": f"细节原图 {number}（可选）", "required": False, "status": "UPLOADED" if asset else "OPTIONAL", "asset": asset, "target": product.spu_code})
    for sku in (item for item in product.skus if item.is_sellable):
        asset = local_asset("SKU_SOURCE", sku_id=sku.id)
        if sku.components and not (asset or sku.source_image_url):
            for component in sku.components:
                component_asset = local_asset("COMPONENT_SOURCE", component_id=component.id)
                slots.append({"slot": f"component-{component.id}", "label": f"{sku.sku_code} · {component.component_name}", "required": True, "status": "UPLOADED" if component_asset or component.source_image_url else "MISSING", "asset": component_asset, "target": component.component_code or component.component_name})
        else:
            slots.append({"slot": f"sku-{sku.id}", "label": f"SKU 原图 · {sku.sku_code}", "required": True, "status": "UPLOADED" if asset or sku.source_image_url else "MISSING", "asset": asset, "target": sku.sku_code})
    return slots


def workflow_payload(db: Session, product: ProductMaster) -> dict:
    slots = source_slots(product)
    batch_query = select(ImageBatch).options(selectinload(ImageBatch.jobs).selectinload(ImageJob.result_asset)).where(ImageBatch.product_id == product.id)
    finished = db.scalar(batch_query.where(ImageBatch.pipeline_kind == "FINISHED_UPLOAD").order_by(ImageBatch.created_at.desc()).limit(1))
    deterministic = db.scalar(batch_query.where(ImageBatch.pipeline_kind == "DETERMINISTIC").order_by(ImageBatch.created_at.desc()).limit(1))
    scene = db.scalar(batch_query.where(ImageBatch.pipeline_kind == "SCENE").order_by(ImageBatch.created_at.desc()).limit(1))
    jobs = list(finished.jobs) if finished else list(deterministic.jobs if deterministic else []) + list(scene.jobs if scene else [])
    outputs = [{"job_id": job.id, "role": job.job_type, "sku_id": job.sku_id, "status": job.status, "error": job.error_message, "qc": (json.loads(job.qc_json) if job.qc_json else None), "asset": ({"id": job.result_asset.id, "width": job.result_asset.width, "height": job.result_asset.height, "sha256": job.result_asset.sha256} if job.result_asset else None)} for job in jobs]
    expected = 6 + len([sku for sku in product.skus if sku.is_sellable])
    complete = sum(1 for item in outputs if item["asset"] is not None and item["status"] in {"COMPLETED", "READY_FOR_REVIEW"})
    running = any(item["status"] in {"PENDING", "RUNNING", "RETRYABLE"} for item in outputs)
    missing = [] if finished else [slot for slot in slots if slot["required"] and slot["status"] == "MISSING"]
    if missing:
        status = "WAITING_SOURCE"
    elif running:
        status = "GENERATING"
    elif complete >= expected:
        status = "READY_TO_PUBLISH"
    elif outputs:
        status = "NEEDS_ATTENTION"
    else:
        status = "READY_TO_GENERATE"
    drafts = db.scalars(select(MiaoshouDraft).where(MiaoshouDraft.product_id == product.id).order_by(MiaoshouDraft.created_at.desc())).all()
    serial_slots = [{**slot, "asset": ({"id": slot["asset"].id, "width": slot["asset"].width, "height": slot["asset"].height} if slot["asset"] else None)} for slot in slots]
    product_data = {"id": product.id, "spu_code": product.spu_code, "title": product.title, "category": product.category, "price": product.price, "stock": product.stock, "dimensions": product.dimensions, "skus": [{"id": sku.id, "sku_code": sku.sku_code, "color": sku.color, "size": sku.size, "quantity": sku.quantity, "price": sku.price, "stock": sku.stock, "is_sellable": sku.is_sellable} for sku in product.skus]}
    stores = [{"store_id": store.id, "name": store.name, "platform": store.platform, "mode": store.mode, "status": "AVAILABLE"} for store in db.scalars(select(Store).where(Store.active.is_(True)).order_by(Store.id)).all()]
    latest_drafts = []
    seen_store_ids: set[int] = set()
    for item in drafts:
        if item.store_id in seen_store_ids:
            continue
        seen_store_ids.add(item.store_id)
        latest_drafts.append(item)
    draft_data = [{"id": item.id, "store_id": item.store_id, "channel": item.channel, "status": item.status, "external_id": item.external_id, "error_message": item.error_message, "package_available": bool(item.package_key)} for item in latest_drafts]
    copies = [copy_payload(item) for item in product.listing_copies]
    review = review_payload(product, outputs, expected)
    packaging_selection = db.scalar(select(ProductPackagingSelection).where(ProductPackagingSelection.product_id == product.id))
    packaging = db.get(PackagingPreset, packaging_selection.preset_id) if packaging_selection else None
    packaging_data = ({"id": packaging.id, "slot": packaging.slot, "filename": packaging.original_filename, "width": packaging.width, "height": packaging.height} if packaging else None)
    publish_blockers = (["请选择外包装图片"] if finished and not packaging else [])
    return {"product": product_data, "image_source": "FINISHED_UPLOAD" if finished else "GENERATED", "slots": serial_slots, "status": status, "missing_count": len(missing), "outputs": outputs, "output_count": complete, "expected_output_count": expected, "stores": stores, "drafts": draft_data, "listing_copies": copies, "review": review, "packaging_selection": packaging_data, "publish_blockers": publish_blockers}


def create_all_batches(db: Session, product: ProductMaster, force: bool, reference_sku_id: int | None = None) -> tuple[ImageBatch, ImageBatch]:
    ready = readiness(product)
    if ready["missing"]:
        raise ValueError("请先补齐商品主原图、尺寸和全部 SKU/组件原图")
    deterministic_fingerprint = input_fingerprint(product)
    deterministic = None if force else db.scalar(select(ImageBatch).where(ImageBatch.product_id == product.id, ImageBatch.pipeline_kind == "DETERMINISTIC", ImageBatch.input_fingerprint == deterministic_fingerprint).order_by(ImageBatch.version.desc()).limit(1))
    new_jobs: list[ImageJob] = []
    if not deterministic:
        version = (db.scalar(select(func.max(ImageBatch.version)).where(ImageBatch.product_id == product.id, ImageBatch.pipeline_kind == "DETERMINISTIC")) or 0) + 1
        skus = [sku for sku in product.skus if sku.is_sellable]
        deterministic = ImageBatch(product_id=product.id, input_fingerprint=deterministic_fingerprint, pipeline_version=PIPELINE_VERSION, pipeline_kind="DETERMINISTIC", version=version, status="PENDING", total_jobs=len(OUTPUT_ROLES) + len(skus))
        db.add(deterministic)
        db.flush()
        jobs = [ImageJob(batch_id=deterministic.id, product_id=product.id, job_type=role) for role in OUTPUT_ROLES]
        jobs += [ImageJob(batch_id=deterministic.id, product_id=product.id, sku_id=sku.id, job_type="SKU_WHITE") for sku in skus]
        db.add_all(jobs)
        new_jobs += jobs
    sku = next((item for item in product.skus if item.id == reference_sku_id and item.is_sellable), None) or next((item for item in product.skus if item.is_sellable), None)
    if not sku:
        raise ValueError("请至少创建一个可销售 SKU")
    profile = db.scalar(select(SceneProfile).where(SceneProfile.product_id == product.id))
    if not profile:
        profile = SceneProfile(product_id=product.id, reference_sku_id=sku.id)
        db.add(profile)
        db.flush()
    else:
        profile.reference_sku_id = sku.id
    provider = configured_provider()
    if scene_readiness(product, profile)["missing"]:
        raise ValueError("场景图缺少主推 SKU 的真实素材")
    scene_fp = scene_fingerprint(product, sku, profile, provider)
    scene = None if force else db.scalar(select(ImageBatch).where(ImageBatch.product_id == product.id, ImageBatch.pipeline_kind == "SCENE", ImageBatch.input_fingerprint == scene_fp).order_by(ImageBatch.version.desc()).limit(1))
    if not scene:
        version = (db.scalar(select(func.max(ImageBatch.version)).where(ImageBatch.product_id == product.id, ImageBatch.pipeline_kind == "SCENE")) or 0) + 1
        scene = ImageBatch(product_id=product.id, input_fingerprint=scene_fp, pipeline_version=SCENE_PIPELINE_VERSION, pipeline_kind="SCENE", provider=provider.config.provider, model=provider.config.model, prompt_version=profile.template_version, reference_sku_id=sku.id, version=version, status="PENDING", total_jobs=2)
        db.add(scene)
        db.flush()
        jobs = [ImageJob(batch_id=scene.id, product_id=product.id, sku_id=sku.id, job_type=role) for role in SCENE_ROLES]
        db.add_all(jobs)
        new_jobs += jobs
    db.commit()
    dispatcher.dispatch([job.id for job in new_jobs])
    return deterministic, scene


def listing_package(db: Session, product: ProductMaster, store: Store) -> tuple[bytes, str]:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        product_csv = io.StringIO()
        writer = csv.writer(product_csv)
        writer.writerow(["SPU", "Title", "Category", "Price", "Stock", "Dimensions", "Store"])
        writer.writerow([product.spu_code, product.title, product.category, product.price, product.stock, product.dimensions, store.name])
        archive.writestr("product.csv", product_csv.getvalue().encode("utf-8-sig"))
        sku_csv = io.StringIO()
        writer = csv.writer(sku_csv)
        writer.writerow(["SKU", "Color", "Size", "Quantity", "Price", "Stock", "Image"])
        sku_ids = [sku.id for sku in product.skus]
        assets = db.scalars(select(SkuAsset).where(SkuAsset.sku_id.in_(sku_ids)).order_by(SkuAsset.created_at.desc())).all() if sku_ids else []
        by_sku = {}
        for item in assets:
            by_sku.setdefault(item.sku_id, item)
        for sku in product.skus:
            sku_asset = by_sku.get(sku.id)
            filename = f"images/{sku.sku_code}.png" if sku_asset else ""
            writer.writerow([sku.sku_code, sku.color, sku.size, sku.quantity, sku.price or product.price, sku.stock, filename])
            if sku_asset:
                version = db.get(AssetVersion, sku_asset.asset_version_id)
                archive.writestr(filename, configured_storage().get(version.storage_key))
        archive.writestr("skus.csv", sku_csv.getvalue().encode("utf-8-sig"))
        platform = "ALIEXPRESS" if store.platform.upper() == "ALIEXPRESS" else store.platform.upper()
        listing_copy = next((item for item in product.listing_copies if item.platform == platform), None)
        if listing_copy:
            archive.writestr("listing-copy.txt", f"Title\n{listing_copy.title}\n\nDescription\n{listing_copy.description}\n\nBullet Points\n".encode("utf-8") + "\n".join(json.loads(listing_copy.bullet_points_json)).encode("utf-8"))
        for asset in db.scalars(select(AssetVersion).where(AssetVersion.product_id == product.id, AssetVersion.role.in_([*OUTPUT_ROLES, *SCENE_ROLES])).order_by(AssetVersion.created_at.desc())).all():
            name = f"images/{asset.role}.png"
            if name not in archive.namelist():
                archive.writestr(name, configured_storage().get(asset.storage_key))
    return stream.getvalue(), f"{product.spu_code}-{store.platform.lower()}-import.zip"
