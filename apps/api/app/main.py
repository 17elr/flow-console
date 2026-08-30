from __future__ import annotations

import json
import os
from datetime import datetime
from contextlib import asynccontextmanager
from io import BytesIO
from typing import Optional
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from .db import Base, SessionLocal, engine, get_db
from .importer import import_workbook, template_workbook
from .models import (
    Asset,
    AssetVersion,
    ImageBatch,
    ImageJob,
    ImportBatch,
    ImportIssue,
    ProductMaster,
    SkuComponent,
    SkuVariant,
    SkuAsset,
    Store,
    StoreListing,
    SceneProfile,
    MiaoshouDraft,
    ListingCopy,
    ReviewDecision,
    AutomationRun,
    AutomationSchedule,
    StoreAutomationConfig,
    PackagingPreset,
    ProductPackagingSelection,
    utcnow,
)
from .providers import configured_provider
from .image_pipeline import OUTPUT_ROLES, dispatcher, input_fingerprint, readiness, sku_source_ready
from .storage import AssetValidationError, configured_storage, validate_image
from .schemas import (
    BatchOut,
    AssetOut,
    ImageBatchCreate,
    ImageBatchOut,
    ImageReadinessOut,
    ComponentCreate,
    ComponentOut,
    ListingCreate,
    ListingOut,
    OverviewOut,
    ProductDetail,
    ProductPatch,
    ProductSummary,
    SkuOut,
    SkuPatch,
    StoreOut,
    SceneBatchCreate, SceneProfileOut, ProviderStatusOut, SimpleProductCreate, GenerateAllCreate, MiaoshouDraftCreate, ListingCopyUpdate, ReviewDecisionCreate, AutomationScheduleCreate, AutomationSchedulePatch, StoreAutomationPatch, AutomationRunCreate, PackagingSelectionPatch, PackagingBulkPatch, FinishedDraftRetryCreate,
)
from .scene_pipeline import DEFAULT_SCENE_TEMPLATE, SCENE_PIPELINE_VERSION, SCENE_ROLES, choose_sku, ensure_birefnet_model, scene_fingerprint, scene_readiness, profile_values
from .simple_workflow import create_all_batches, workflow_payload
from .miaoshou import configured_miaoshou
from .copywriting import copy_payload, update_copy, upsert_generated_copy
from .reviews import save_image_decision, save_product_decision
from .publishing import create_store_drafts
from .automation import automation_scheduler, recover_interrupted_runs, run_automation, run_payload, schedule_payload
from .finished_import import import_finished_package


SAMPLE_IMAGE = "https://images.unsplash.com/photo-1515562141207-7a88fb7ce338?auto=format&fit=crop&w=480&q=80"


def seed(db: Session) -> None:
    if not db.scalar(select(Store).limit(1)):
        db.add_all(
            [
                Store(name="环球饰品（深圳）", platform="TEMU", mode="全托管", currency="USD"),
                Store(name="Global Jewelry Store", platform="AliExpress", mode="POP", currency="USD"),
                Store(name="饰品测试店-2", platform="TEMU", mode="POP", currency="USD"),
            ]
        )
        db.flush()
    if db.scalar(select(ProductMaster).limit(1)):
        db.commit()
        return
    samples = [
        ("SPU-DEMO-001", "S925银莫桑石六爪项链", "925银", "银色", "45cm", 9.9, 180, True),
        ("SPU-DEMO-002", "18K金色心形耳钉", "合金", "玫瑰金", "8mm", 6.8, 96, False),
        ("SPU-DEMO-003", "珍珠贝母项链", None, "白色", "40cm", 12.8, 42, False),
        ("SPU-DEMO-004", "钻石四叶草手链", "合金", "金色", "17cm", 8.6, 73, True),
        ("SPU-DEMO-005", "简约圆环耳扣", "不锈钢", "银色", "12mm", 5.4, 210, True),
    ]
    stores = db.scalars(select(Store).order_by(Store.id)).all()
    for index, (spu, title, material, color, dimensions, price, stock, complete) in enumerate(samples):
        image = SAMPLE_IMAGE if complete else None
        product = ProductMaster(
            spu_code=spu,
            title=title,
            category="女士饰品",
            material=material,
            color=color,
            dimensions=dimensions,
            price=price,
            currency="USD",
            stock=stock,
            source_image_url=image,
            image_rights="AUTHORIZED" if complete else "UNKNOWN",
            status="WAITING_GENERATION" if complete else "WAITING_DATA",
        )
        db.add(product)
        db.flush()
        sku = SkuVariant(
            product_id=product.id,
            sku_code=f"{spu}-01",
            name=f"{color or '待补颜色'} / {dimensions or '待补尺寸'}",
            color=color,
            size=dimensions,
            material=material,
            quantity=1,
            price=price,
            stock=stock,
            source_image_url=image,
            is_sellable=True,
            status="WAITING_GENERATION" if complete else "WAITING_DATA",
        )
        db.add(sku)
        db.flush()
        if image:
            db.add_all(
                [
                    Asset(product_id=product.id, asset_type="SPU_SOURCE", url=image, rights_status="AUTHORIZED"),
                    Asset(product_id=product.id, sku_id=sku.id, asset_type="SKU_SOURCE", url=image, rights_status="AUTHORIZED"),
                ]
            )
        if index == 0:
            set_sku = SkuVariant(
                product_id=product.id,
                sku_code=f"{spu}-SET",
                name="银色项链双件套",
                color="银色",
                size="45cm",
                material="925银",
                quantity=2,
                price=16.8,
                stock=32,
                source_image_url=None,
                is_sellable=True,
                status="WAITING_DATA",
            )
            db.add(set_sku)
            db.flush()
            db.add_all(
                [
                    SkuComponent(sku_id=set_sku.id, component_code=f"{spu}-01", component_name="六爪项链", color="银色", quantity=1, source_image_url=image),
                    SkuComponent(sku_id=set_sku.id, component_code=f"{spu}-02", component_name="圆钻耳钉", color="银色", quantity=1, source_image_url=None),
                ]
            )
            product.status = "WAITING_DATA"
        store = stores[index % len(stores)]
        db.add(
            StoreListing(
                product_id=product.id,
                store_id=store.id,
                listing_title=title,
                price=price,
                status="NOT_READY",
            )
        )
    db.commit()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed(db)
        sync_image_readiness(db)
        recover_interrupted_runs(db)
    ensure_birefnet_model()
    dispatcher.resume()
    automation_scheduler.start()
    try:
        yield
    finally:
        automation_scheduler.stop()


app = FastAPI(title="AI Commerce Product Center", version="0.1.0", lifespan=lifespan)
origins = [
    item.strip()
    for item in os.getenv(
        "API_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    if item.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    provider = configured_provider()
    return {
        "ok": True,
        "module": "commerce-automation-workflow",
        "image_provider": provider.health_check(),
    }


@app.get("/api/overview", response_model=OverviewOut)
def overview(db: Session = Depends(get_db)) -> dict:
    latest = db.scalar(
        select(ImportBatch)
        .options(selectinload(ImportBatch.issues))
        .order_by(ImportBatch.created_at.desc())
        .limit(1)
    )
    return {
        "products": db.scalar(select(func.count(ProductMaster.id))) or 0,
        "skus": db.scalar(select(func.count(SkuVariant.id))) or 0,
        "waiting_data": db.scalar(
            select(func.count(ProductMaster.id)).where(ProductMaster.status == "WAITING_DATA")
        )
        or 0,
        "waiting_generation": db.scalar(
            select(func.count(ProductMaster.id)).where(ProductMaster.status == "WAITING_GENERATION")
        )
        or 0,
        "ready": db.scalar(
            select(func.count(ProductMaster.id)).where(ProductMaster.status == "READY")
        )
        or 0,
        "issues": db.scalar(
            select(func.count(ImportIssue.id)).where(ImportIssue.severity == "ERROR")
        )
        or 0,
        "stores": db.scalar(select(func.count(Store.id)).where(Store.active.is_(True))) or 0,
        "latest_batch": latest,
    }


def summarize(product: ProductMaster) -> dict:
    blocker_count = 0
    warning_count = 0
    if not product.material:
        blocker_count += 1
    if not product.source_image_url:
        warning_count += 1
    if product.image_rights.upper() in {"UNKNOWN", "未确认", "不清楚"}:
        warning_count += 1
    for sku in product.skus:
        if sku.is_sellable and not sku.source_image_url:
            blocker_count += 1
        if sku.is_sellable and not sku.color:
            blocker_count += 1
    return {
        "id": product.id,
        "spu_code": product.spu_code,
        "title": product.title,
        "category": product.category,
        "material": product.material,
        "price": product.price,
        "currency": product.currency,
        "stock": product.stock,
        "source_image_url": product.source_image_url,
        "image_rights": product.image_rights,
        "status": product.status,
        "image_readiness": product.image_readiness,
        "scene_readiness": product.scene_readiness,
        "sku_count": len(product.skus),
        "ready_sku_count": sum(1 for sku in product.skus if sku.status == "WAITING_GENERATION"),
        "listing_count": len(product.listings),
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "updated_at": product.updated_at,
    }


def load_product(db: Session, product_id: int) -> ProductMaster:
    product = db.scalar(
        select(ProductMaster)
        .options(
            selectinload(ProductMaster.skus).selectinload(SkuVariant.components),
            selectinload(ProductMaster.assets),
            selectinload(ProductMaster.listings).selectinload(StoreListing.store),
            selectinload(ProductMaster.listing_copies),
            selectinload(ProductMaster.review_decisions),
        )
        .where(ProductMaster.id == product_id)
    )
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    return product


def sync_image_readiness(db: Session) -> None:
    products = db.scalars(
        select(ProductMaster)
        .options(
            selectinload(ProductMaster.assets),
            selectinload(ProductMaster.skus).selectinload(SkuVariant.components),
        )
    ).unique().all()
    for product in products:
        product.image_readiness = readiness(product)["status"]
        product.scene_readiness = scene_readiness(product, product.scene_profile)["status"] if product.scene_profile else "NOT_CONFIGURED"
    db.commit()


def detail_payload(product: ProductMaster) -> dict:
    return {
        **summarize(product),
        "dimensions": product.dimensions,
        "weight_g": product.weight_g,
        "cost": product.cost,
        "color": product.color,
        "skus": product.skus,
        "assets": product.assets,
        "listings": product.listings,
    }


def recalculate_product_status(product: ProductMaster) -> None:
    sellable_skus = [sku for sku in product.skus if sku.is_sellable]
    has_complete_product_data = (
        bool(product.material)
        and bool(product.source_image_url)
        and product.image_rights.upper() not in {"UNKNOWN", "未确认", "不清楚"}
    )
    has_complete_sku_data = bool(sellable_skus) and all(sku_source_ready(sku) and sku.color for sku in sellable_skus)
    product.status = (
        "WAITING_GENERATION"
        if has_complete_product_data and has_complete_sku_data
        else "WAITING_DATA"
    )


@app.get("/api/products", response_model=list[ProductSummary])
def products(
    q: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    store_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict]:
    sync_image_readiness(db)
    stmt = select(ProductMaster).options(
        selectinload(ProductMaster.skus), selectinload(ProductMaster.listings)
    )
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(ProductMaster.spu_code.ilike(pattern), ProductMaster.title.ilike(pattern))
        )
    if status and status != "ALL":
        stmt = stmt.where(ProductMaster.status == status)
    if store_id:
        stmt = stmt.join(StoreListing).where(StoreListing.store_id == store_id)
    items = db.scalars(stmt.order_by(ProductMaster.updated_at.desc())).unique().all()
    return [summarize(item) for item in items]


@app.get("/api/products/{product_id}", response_model=ProductDetail)
def product_detail(product_id: int, db: Session = Depends(get_db)) -> dict:
    return detail_payload(load_product(db, product_id))


@app.delete("/api/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)) -> dict:
    """Delete one local product and all of its workflow records.

    External marketplace drafts are intentionally left untouched: deleting a
    local record must never issue an irreversible remote marketplace delete.
    """
    product = db.scalar(select(ProductMaster).where(ProductMaster.id == product_id))
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    sku_ids = list(
        db.scalars(select(SkuVariant.id).where(SkuVariant.product_id == product_id)).all()
    )
    batch_ids = list(
        db.scalars(select(ImageBatch.id).where(ImageBatch.product_id == product_id)).all()
    )
    draft_count = db.scalar(
        select(func.count(MiaoshouDraft.id)).where(MiaoshouDraft.product_id == product_id)
    ) or 0

    try:
        # Clear children that reference SKU/batch/asset-version rows first.
        if sku_ids:
            db.execute(delete(SkuAsset).where(SkuAsset.sku_id.in_(sku_ids)))
            db.execute(delete(SkuComponent).where(SkuComponent.sku_id.in_(sku_ids)))
        if batch_ids:
            db.execute(delete(ImageJob).where(ImageJob.batch_id.in_(batch_ids)))
            db.execute(delete(AssetVersion).where(AssetVersion.batch_id.in_(batch_ids)))
        db.execute(delete(ImageJob).where(ImageJob.product_id == product_id))
        db.execute(delete(AssetVersion).where(AssetVersion.product_id == product_id))
        db.execute(delete(ImageBatch).where(ImageBatch.product_id == product_id))
        db.execute(delete(ProductPackagingSelection).where(ProductPackagingSelection.product_id == product_id))
        db.execute(delete(MiaoshouDraft).where(MiaoshouDraft.product_id == product_id))
        db.execute(delete(StoreListing).where(StoreListing.product_id == product_id))
        db.execute(delete(ListingCopy).where(ListingCopy.product_id == product_id))
        db.execute(delete(ReviewDecision).where(ReviewDecision.product_id == product_id))
        db.execute(delete(SceneProfile).where(SceneProfile.product_id == product_id))
        db.execute(delete(Asset).where(Asset.product_id == product_id))
        if sku_ids:
            db.execute(delete(SkuVariant).where(SkuVariant.id.in_(sku_ids)))
        db.delete(product)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "deleted": True,
        "product_id": product_id,
        "external_drafts_preserved": int(draft_count),
    }


@app.post("/api/simple-products")
def save_simple_product(payload: SimpleProductCreate, db: Session = Depends(get_db)) -> dict:
    product = db.scalar(select(ProductMaster).where(ProductMaster.spu_code == payload.spu_code.strip()))
    if not product:
        product = ProductMaster(spu_code=payload.spu_code.strip(), title=payload.title.strip(), category=payload.category.strip(), price=payload.price, stock=payload.stock, dimensions=payload.dimensions.strip(), image_rights="UNKNOWN", status="WAITING_DATA")
        db.add(product); db.flush()
    else:
        product.title, product.category, product.price, product.stock, product.dimensions = payload.title.strip(), payload.category.strip(), payload.price, payload.stock, payload.dimensions.strip()
    existing = {sku.sku_code: sku for sku in product.skus}
    for row in payload.skus:
        sku = existing.get(row.sku_code.strip())
        if not sku:
            sku = SkuVariant(product_id=product.id, sku_code=row.sku_code.strip(), is_sellable=True)
            db.add(sku)
        sku.name = " / ".join(filter(None, [row.color, row.size])); sku.color = row.color; sku.size = row.size; sku.quantity = row.quantity; sku.price = row.price if row.price is not None else payload.price; sku.stock = row.stock
    db.commit()
    return workflow_payload(db, load_product(db, product.id))


@app.get("/api/products/{product_id}/workflow")
def simple_product_workflow(product_id: int, db: Session = Depends(get_db)) -> dict:
    return workflow_payload(db, load_product(db, product_id))


@app.post("/api/products/{product_id}/listing-copies")
def generate_listing_copies(product_id: int, db: Session = Depends(get_db)) -> dict:
    product = load_product(db, product_id)
    for platform in ("TEMU", "ALIEXPRESS"):
        upsert_generated_copy(db, product, platform)
    db.commit()
    db.expire_all()
    return workflow_payload(db, load_product(db, product_id))


@app.put("/api/listing-copies/{copy_id}")
def save_listing_copy(copy_id: int, payload: ListingCopyUpdate, db: Session = Depends(get_db)) -> dict:
    record = db.get(ListingCopy, copy_id)
    if not record:
        raise HTTPException(status_code=404, detail="平台文案不存在")
    update_copy(record, payload.model_dump())
    db.commit()
    product_id = record.product_id
    db.expire_all()
    return workflow_payload(db, load_product(db, product_id))


@app.put("/api/reviews/images/{asset_id}")
def review_generated_image(asset_id: int, payload: ReviewDecisionCreate, db: Session = Depends(get_db)) -> dict:
    decision = payload.decision.upper()
    if decision not in {"APPROVED", "REJECTED"}:
        raise HTTPException(status_code=422, detail="审核结果必须是通过或驳回")
    asset = db.get(AssetVersion, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="生成图片不存在")
    save_image_decision(db, asset, decision, payload.note)
    db.commit()
    product_id = asset.product_id
    db.expire_all()
    return workflow_payload(db, load_product(db, product_id))


@app.put("/api/products/{product_id}/review")
def review_product(product_id: int, payload: ReviewDecisionCreate, db: Session = Depends(get_db)) -> dict:
    decision = payload.decision.upper()
    if decision not in {"APPROVED", "REJECTED"}:
        raise HTTPException(status_code=422, detail="审核结果必须是通过或驳回")
    product = load_product(db, product_id)
    state = workflow_payload(db, product)
    try:
        save_product_decision(db, product, state["review"], decision, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.expire_all()
    return workflow_payload(db, load_product(db, product_id))


def _slot_target(db: Session, product: ProductMaster, slot: str) -> tuple[str, Optional[SkuVariant], Optional[SkuComponent]]:
    if slot == "spu-main": return "SPU_MAIN_SOURCE", None, None
    if slot == "spu-detail-1": return "SPU_DETAIL_1_SOURCE", None, None
    if slot == "spu-detail-2": return "SPU_DETAIL_2_SOURCE", None, None
    if slot.startswith("sku-"):
        sku = db.get(SkuVariant, int(slot[4:]));
        if not sku or sku.product_id != product.id: raise HTTPException(status_code=404, detail="SKU 素材槽不存在")
        return "SKU_SOURCE", sku, None
    if slot.startswith("component-"):
        component = db.get(SkuComponent, int(slot[10:])); sku = db.get(SkuVariant, component.sku_id) if component else None
        if not component or not sku or sku.product_id != product.id: raise HTTPException(status_code=404, detail="组件素材槽不存在")
        return "COMPONENT_SOURCE", sku, component
    raise HTTPException(status_code=404, detail="素材槽不存在")


@app.put("/api/source-assets/{slot}")
def replace_source_slot(slot: str, product_id: int = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    product = load_product(db, product_id); role, sku, component = _slot_target(db, product, slot)
    content = file.file.read()
    try: meta = validate_image(content)
    except AssetValidationError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    existing = db.scalars(select(Asset).where(Asset.product_id == product.id, Asset.role == role, Asset.sku_id == (sku.id if sku else None), Asset.component_id == (component.id if component else None))).all()
    for item in existing: db.delete(item)
    key = f"sources/{product.id}/{meta['sha256'][:20]}-{role.lower()}.{meta['extension']}"; configured_storage().put(key, content, meta["mime_type"])
    asset = Asset(product_id=product.id, sku_id=sku.id if sku else None, component_id=component.id if component else None, asset_type="SOURCE", role=role, url=f"storage://{key}", storage_key=key, sha256=meta["sha256"], mime_type=meta["mime_type"], width=meta["width"], height=meta["height"], byte_size=meta["byte_size"], mirror_status="MIRRORED", rights_status="AUTHORIZED")
    db.add(asset)
    if role == "SPU_MAIN_SOURCE": product.image_rights = "AUTHORIZED"
    db.commit()
    return workflow_payload(db, load_product(db, product.id))


@app.delete("/api/source-assets/{asset_id}", status_code=204)
def delete_source_asset(asset_id: int, db: Session = Depends(get_db)) -> None:
    asset = db.get(Asset, asset_id)
    if not asset: raise HTTPException(status_code=404, detail="素材不存在")
    product_id = asset.product_id; db.delete(asset); db.flush()
    product = load_product(db, product_id); product.image_readiness = readiness(product)["status"]; db.commit()


@app.post("/api/products/{product_id}/generate-all")
def generate_all(product_id: int, payload: GenerateAllCreate, db: Session = Depends(get_db)) -> dict:
    product = load_product(db, product_id)
    try: create_all_batches(db, product, payload.force, payload.reference_sku_id)
    except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc
    return workflow_payload(db, load_product(db, product_id))


@app.put("/api/generated-assets/{asset_id}")
def replace_generated_asset(asset_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    asset = db.get(AssetVersion, asset_id)
    if not asset: raise HTTPException(status_code=404, detail="生成图片不存在")
    content = file.file.read()
    try: meta = validate_image(content)
    except AssetValidationError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    configured_storage().put(asset.storage_key, content, meta["mime_type"])
    asset.sha256, asset.mime_type, asset.width, asset.height, asset.byte_size = meta["sha256"], meta["mime_type"], meta["width"], meta["height"], meta["byte_size"]
    asset.qc_json = json.dumps({"status": "MANUAL_REPLACEMENT", "fidelity_review_required": True}, ensure_ascii=False); db.commit()
    return workflow_payload(db, load_product(db, asset.product_id))


@app.delete("/api/generated-assets/{asset_id}", status_code=204)
def delete_generated_asset(asset_id: int, db: Session = Depends(get_db)) -> None:
    asset = db.get(AssetVersion, asset_id)
    if not asset: raise HTTPException(status_code=404, detail="生成图片不存在")
    jobs = db.scalars(select(ImageJob).where(ImageJob.result_asset_id == asset.id)).all()
    for job in jobs: job.result_asset_id = None; job.status = "QC_FAILED"; job.error_message = "生成图片已人工删除"
    db.delete(asset); db.commit()


@app.get("/api/miaoshou/status")
def miaoshou_status() -> dict:
    return configured_miaoshou().status()


@app.get("/api/miaoshou/category-rules/{cid}")
def miaoshou_category_rules(cid: str) -> dict:
    """Read category fields/options for template mapping without exposing credentials."""
    if not cid.isdigit():
        raise HTTPException(status_code=422, detail="cid must be numeric")
    try:
        data = configured_miaoshou()._category_rules(cid)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    rules = data.get("productAttributeRules") or []
    return {
        "cid": cid,
        "attributes": [
            {
                "name": item.get("name"),
                "required": bool(item.get("required")),
                "values": [{"vid": value.get("vid"), "name": value.get("name")} for value in (item.get("values") or [])],
            }
            for item in rules
            if item.get("name")
        ],
    }


@app.post("/api/miaoshou/stores/sync")
def sync_miaoshou_stores(mode: str = Query(default="SEMI", pattern="^(SEMI|FULL)$"), db: Session = Depends(get_db)) -> dict:
    provider = configured_miaoshou()
    try:
        response = provider.list_shops(mode)
    except Exception as exc:
        from .miaoshou import MiaoshouError
        if isinstance(exc, MiaoshouError):
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        raise
    data = response.get("data") or {}
    candidates = data if isinstance(data, list) else next(
        (value for key, value in data.items() if isinstance(value, list) and key.lower() in {"list", "records", "rows", "shoplist", "datalist"}),
        [],
    )
    synced = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        external_id = item.get("shopId") or item.get("shop_id") or item.get("id")
        name = item.get("shopName") or item.get("shop_name") or item.get("platformShopName") or item.get("shopNick") or item.get("name")
        if external_id is None or not name:
            continue
        external_id = str(external_id)
        raw_platform = str(item.get("platform") or item.get("platformCode") or item.get("site") or "").upper()
        is_aliexpress = "ALI" in raw_platform or "速卖通" in raw_platform
        store = db.scalar(select(Store).where(Store.external_shop_id == external_id))
        if not store:
            store = Store(name=str(name), platform="ALIEXPRESS" if is_aliexpress else "TEMU", mode="POP" if is_aliexpress else ("半托管" if mode == "SEMI" else "全托管"), currency="USD")
            db.add(store)
        store.name = str(name)
        if is_aliexpress:
            store.platform = "ALIEXPRESS"
            store.mode = "POP"
        store.external_shop_id = external_id
        store.active = True
        synced.append({"name": store.name, "external_shop_id": external_id, "mode": store.mode})
    db.commit()
    return {"mode": mode, "count": len(synced), "stores": synced, "request_id": response.get("request_id")}


@app.delete("/api/stores/{store_id}")
def deactivate_store(store_id: int, db: Session = Depends(get_db)) -> dict:
    """Hide a store from automation without deleting listings or draft history."""
    store = db.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="店铺不存在")
    store.active = False
    db.commit()
    return {"id": store.id, "active": False, "message": "店铺已移除（历史数据保留）"}


@app.get("/api/automation/overview")
def automation_overview(db: Session = Depends(get_db)) -> dict:
    runs = db.scalars(select(AutomationRun).order_by(AutomationRun.started_at.desc()).limit(20)).all()
    schedules = db.scalars(select(AutomationSchedule).order_by(AutomationSchedule.id)).all()
    stores = db.scalars(select(Store).where(Store.active.is_(True)).order_by(Store.id)).all()
    configs = {item.store_id: item for item in db.scalars(select(StoreAutomationConfig)).all()}
    drafts = db.scalars(select(MiaoshouDraft)).all()
    image_jobs = db.scalars(select(ImageJob)).all()
    completed_images = sum(job.status in {"COMPLETED", "READY_FOR_REVIEW"} for job in image_jobs)
    failed_images = sum(job.status in {"FAILED", "QC_FAILED", "ENGINE_UNAVAILABLE"} for job in image_jobs)
    image_total = completed_images + failed_images
    return {
        "metrics": {
            "active_schedules": sum(item.active for item in schedules),
            "draft_success": sum(item.status in {"DRAFT_CREATED", "PUBLISHED", "PACKAGE_READY"} for item in drafts),
            "draft_failed": sum(item.status == "FAILED" for item in drafts),
            "image_pass_rate": round(completed_images / image_total * 100, 1) if image_total else 0,
            "runs": len(runs),
        },
        "schedules": [schedule_payload(item) for item in schedules],
        "runs": [run_payload(item) for item in runs],
        "stores": [{"id": store.id, "name": store.name, "platform": store.platform, "mode": store.mode, "external_shop_id": store.external_shop_id, "automation_ready": store.platform.upper() != "TEMU" or bool(store.external_shop_id), "config": {"active": configs[store.id].active, "auto_publish": configs[store.id].auto_publish, "price_multiplier": configs[store.id].price_multiplier, "visual_profile": configs[store.id].visual_profile, "max_daily": configs[store.id].max_daily} if store.id in configs else {"active": True, "auto_publish": False, "price_multiplier": 1.0, "visual_profile": "neutral-commerce", "max_daily": 20}} for store in stores],
    }


@app.post("/api/automation/schedules")
def create_automation_schedule(payload: AutomationScheduleCreate, db: Session = Depends(get_db)) -> dict:
    if not payload.store_ids or not 1 <= payload.max_products <= 100:
        raise HTTPException(status_code=422, detail="请选择店铺，每次商品数必须为 1-100")
    try:
        datetime.strptime(payload.run_time, "%H:%M")
        ZoneInfo(payload.timezone)
    except (ValueError, ZoneInfoNotFoundError):
        raise HTTPException(status_code=422, detail="运行时间格式必须为 HH:MM")
    valid_store_count = db.scalar(select(func.count(Store.id)).where(Store.id.in_(payload.store_ids), Store.active.is_(True)))
    if valid_store_count != len(set(payload.store_ids)):
        raise HTTPException(status_code=422, detail="包含不存在或已停用的店铺")
    schedule = AutomationSchedule(name=payload.name.strip(), active=payload.active, run_time=payload.run_time, timezone=payload.timezone, store_ids_json=json.dumps(payload.store_ids), max_products=payload.max_products)
    db.add(schedule); db.commit(); db.refresh(schedule)
    return schedule_payload(schedule)


@app.patch("/api/automation/schedules/{schedule_id}")
def update_automation_schedule(schedule_id: int, payload: AutomationSchedulePatch, db: Session = Depends(get_db)) -> dict:
    schedule = db.get(AutomationSchedule, schedule_id)
    if not schedule: raise HTTPException(status_code=404, detail="调度计划不存在")
    values = payload.model_dump(exclude_unset=True)
    if "run_time" in values:
        try: datetime.strptime(values["run_time"], "%H:%M")
        except ValueError: raise HTTPException(status_code=422, detail="运行时间格式必须为 HH:MM")
    if "timezone" in values:
        try: ZoneInfo(values["timezone"])
        except ZoneInfoNotFoundError: raise HTTPException(status_code=422, detail="时区无效")
    if "max_products" in values and not 1 <= values["max_products"] <= 100:
        raise HTTPException(status_code=422, detail="每次商品数必须为 1-100")
    if "store_ids" in values:
        store_ids = values["store_ids"]
        if not store_ids:
            raise HTTPException(status_code=422, detail="请至少选择一个店铺")
        valid_store_count = db.scalar(select(func.count(Store.id)).where(Store.id.in_(store_ids), Store.active.is_(True)))
        if valid_store_count != len(set(store_ids)):
            raise HTTPException(status_code=422, detail="包含不存在或已停用的店铺")
    if "store_ids" in values: schedule.store_ids_json = json.dumps(values.pop("store_ids"))
    for key, value in values.items(): setattr(schedule, key, value)
    db.commit(); db.refresh(schedule); return schedule_payload(schedule)


@app.delete("/api/automation/schedules/{schedule_id}")
def delete_automation_schedule(schedule_id: int, db: Session = Depends(get_db)) -> dict:
    schedule = db.get(AutomationSchedule, schedule_id)
    if not schedule: raise HTTPException(status_code=404, detail="调度计划不存在")
    db.delete(schedule); db.commit()
    return {"id": schedule_id, "deleted": True}


@app.put("/api/automation/stores/{store_id}")
def update_store_automation(store_id: int, payload: StoreAutomationPatch, db: Session = Depends(get_db)) -> dict:
    if not db.get(Store, store_id): raise HTTPException(status_code=404, detail="店铺不存在")
    if not 0.1 <= payload.price_multiplier <= 10 or not 1 <= payload.max_daily <= 100:
        raise HTTPException(status_code=422, detail="价格倍率或每日上限无效")
    config = db.scalar(select(StoreAutomationConfig).where(StoreAutomationConfig.store_id == store_id))
    if not config:
        config = StoreAutomationConfig(store_id=store_id); db.add(config)
    for key, value in payload.model_dump().items(): setattr(config, key, value)
    db.commit(); db.refresh(config)
    return {"store_id": store_id, **payload.model_dump()}


@app.post("/api/automation/runs")
def start_automation_run(payload: AutomationRunCreate, db: Session = Depends(get_db)) -> dict:
    if not payload.store_ids or not 1 <= payload.max_products <= 100:
        raise HTTPException(status_code=422, detail="请选择店铺，每次商品数必须为 1-100")
    return run_payload(run_automation(db, payload.store_ids, payload.max_products))


@app.get("/api/automation/runs")
def list_automation_runs(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)) -> list[dict]:
    return [run_payload(item) for item in db.scalars(select(AutomationRun).order_by(AutomationRun.started_at.desc()).limit(limit)).all()]


@app.delete("/api/automation/runs/{run_id}")
def delete_automation_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    run = db.get(AutomationRun, run_id)
    if not run: raise HTTPException(status_code=404, detail="运行记录不存在")
    db.delete(run); db.commit()
    return {"id": run_id, "deleted": True}


@app.post("/api/products/{product_id}/miaoshou-drafts")
def create_miaoshou_drafts(product_id: int, payload: MiaoshouDraftCreate, db: Session = Depends(get_db)) -> dict:
    product = load_product(db, product_id); state = workflow_payload(db, product)
    if state["status"] != "READY_TO_PUBLISH": raise HTTPException(status_code=409, detail="请先补齐并检查全部生成图片")
    if state.get("publish_blockers"): raise HTTPException(status_code=409, detail="；".join(state["publish_blockers"]))
    if not payload.confirmed_review: raise HTTPException(status_code=409, detail="请先人工查看并确认全部生成图片")
    if not state["review"]["approved"]: raise HTTPException(status_code=409, detail="请先完成整款人工审核")
    return {"results": create_store_drafts(db, product, state, payload.store_ids, force=payload.force, auto_publish=payload.auto_publish)}


@app.get("/api/miaoshou-drafts/{draft_id}/package")
def download_miaoshou_package(draft_id: int, db: Session = Depends(get_db)) -> Response:
    draft = db.get(MiaoshouDraft, draft_id)
    if not draft or not draft.package_key: raise HTTPException(status_code=404, detail="导入包不存在")
    content = configured_storage().get(draft.package_key)
    return Response(content=content, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="listing-package-{draft.id}.zip"'})


@app.patch("/api/products/{product_id}", response_model=ProductDetail)
def update_product(
    product_id: int, payload: ProductPatch, db: Session = Depends(get_db)
) -> dict:
    product = load_product(db, product_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    recalculate_product_status(product)
    db.commit()
    return detail_payload(load_product(db, product_id))


@app.patch("/api/skus/{sku_id}", response_model=SkuOut)
def update_sku(sku_id: int, payload: SkuPatch, db: Session = Depends(get_db)) -> SkuVariant:
    sku = db.get(SkuVariant, sku_id)
    if not sku:
        raise HTTPException(status_code=404, detail="SKU 不存在")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(sku, key, value)
    sku.status = "WAITING_GENERATION" if sku_source_ready(sku) and sku.color else "WAITING_DATA"
    product = load_product(db, sku.product_id)
    recalculate_product_status(product)
    db.commit()
    return db.scalar(
        select(SkuVariant)
        .options(selectinload(SkuVariant.components))
        .where(SkuVariant.id == sku_id)
    )


@app.post("/api/skus/{sku_id}/components", response_model=ComponentOut)
def add_component(
    sku_id: int, payload: ComponentCreate, db: Session = Depends(get_db)
) -> SkuComponent:
    if not db.get(SkuVariant, sku_id):
        raise HTTPException(status_code=404, detail="SKU 不存在")
    component = SkuComponent(sku_id=sku_id, **payload.model_dump())
    db.add(component)
    db.commit()
    db.refresh(component)
    sku = db.get(SkuVariant, sku_id)
    product = load_product(db, sku.product_id)
    sku.status = "WAITING_GENERATION" if sku_source_ready(sku) and sku.color else "WAITING_DATA"
    recalculate_product_status(product)
    db.commit()
    return component


@app.delete("/api/components/{component_id}", status_code=204)
def delete_component(component_id: int, db: Session = Depends(get_db)) -> None:
    component = db.get(SkuComponent, component_id)
    if not component:
        raise HTTPException(status_code=404, detail="组件不存在")
    sku_id = component.sku_id
    db.delete(component)
    db.flush()
    sku = db.get(SkuVariant, sku_id)
    product = load_product(db, sku.product_id)
    sku.status = "WAITING_GENERATION" if sku_source_ready(sku) and sku.color else "WAITING_DATA"
    recalculate_product_status(product)
    db.commit()


def load_image_batch(db: Session, batch_id: int) -> ImageBatch:
    batch = db.scalar(
        select(ImageBatch)
        .options(selectinload(ImageBatch.jobs).selectinload(ImageJob.result_asset))
        .where(ImageBatch.id == batch_id)
    )
    if not batch:
        raise HTTPException(status_code=404, detail="图片批次不存在")
    return batch


@app.post("/api/source-assets", response_model=AssetOut)
def upload_source_asset(
    product_id: int = Form(...),
    role: str = Form(...),
    file: UploadFile = File(...),
    sku_id: Optional[int] = Form(default=None),
    component_id: Optional[int] = Form(default=None),
    rights_status: str = Form(default="AUTHORIZED"),
    db: Session = Depends(get_db),
) -> Asset:
    product = load_product(db, product_id)
    allowed_roles = {"SPU_MAIN_SOURCE", "SPU_DETAIL_1_SOURCE", "SPU_DETAIL_2_SOURCE", "SKU_SOURCE", "COMPONENT_SOURCE"}
    if role not in allowed_roles:
        raise HTTPException(status_code=422, detail="不支持的素材角色")
    sku = db.get(SkuVariant, sku_id) if sku_id else None
    component = db.get(SkuComponent, component_id) if component_id else None
    if sku and sku.product_id != product.id:
        raise HTTPException(status_code=422, detail="SKU 不属于该商品")
    if component:
        component_sku = db.get(SkuVariant, component.sku_id)
        if component_sku.product_id != product.id:
            raise HTTPException(status_code=422, detail="组件不属于该商品")
    content = file.file.read()
    try:
        meta = validate_image(content)
    except AssetValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    key = f"sources/{product.id}/{meta['sha256'][:20]}-{role.lower()}.{meta['extension']}"
    configured_storage().put(key, content, meta["mime_type"])
    asset = Asset(
        product_id=product.id,
        sku_id=sku.id if sku else None,
        component_id=component.id if component else None,
        asset_type="SOURCE",
        role=role,
        url=f"storage://{key}",
        source_url=None,
        storage_key=key,
        sha256=meta["sha256"],
        mime_type=meta["mime_type"],
        width=meta["width"],
        height=meta["height"],
        byte_size=meta["byte_size"],
        mirror_status="MIRRORED",
        rights_status=rights_status,
    )
    db.add(asset)
    if role == "SPU_MAIN_SOURCE":
        product.image_rights = rights_status
    if role == "SKU_SOURCE" and sku:
        sku.status = "WAITING_GENERATION" if sku.color else "WAITING_DATA"
    db.flush()
    product.image_readiness = readiness(load_product(db, product.id))["status"]
    db.commit()
    db.refresh(asset)
    return asset


@app.get("/api/image-provider/status", response_model=ProviderStatusOut)
def image_provider_status() -> dict:
    provider = configured_provider()
    return {**provider.health_check(), **provider.remote_health_check(), "capabilities": provider.get_capabilities()}


@app.get("/api/scene-templates")
def scene_templates() -> dict:
    return {"version": SCENE_PIPELINE_VERSION, "defaults": DEFAULT_SCENE_TEMPLATE}


@app.get("/api/products/{product_id}/scene-profile", response_model=SceneProfileOut)
def get_scene_profile(product_id: int, db: Session = Depends(get_db)) -> dict:
    product = load_product(db, product_id)
    profile = db.scalar(select(SceneProfile).where(SceneProfile.product_id == product_id))
    result = scene_readiness(product, profile)
    return {"product_id": product_id, **profile_values(profile), "template_version": profile.template_version if profile else DEFAULT_SCENE_TEMPLATE["template_version"], "status": result["status"], "missing": result["missing"]}


@app.patch("/api/products/{product_id}/scene-profile", response_model=SceneProfileOut)
def patch_scene_profile(product_id: int, payload: SceneBatchCreate, db: Session = Depends(get_db)) -> dict:
    product = load_product(db, product_id)
    profile = db.scalar(select(SceneProfile).where(SceneProfile.product_id == product_id))
    if not profile:
        profile = SceneProfile(product_id=product_id)
        db.add(profile)
    values = payload.model_dump(exclude_unset=True, exclude={"force"})
    if values.get("reference_sku_id") is not None:
        choose_sku(product, values["reference_sku_id"])
    for key, value in values.items():
        setattr(profile, key, value)
    db.flush()
    result = scene_readiness(product, profile)
    product.scene_readiness = result["status"]
    db.commit()
    return {"product_id": product_id, **profile_values(profile), "template_version": profile.template_version, "status": result["status"], "missing": result["missing"]}


@app.post("/api/products/{product_id}/scene-batches", response_model=ImageBatchOut)
def create_scene_batch(product_id: int, payload: SceneBatchCreate, db: Session = Depends(get_db)) -> ImageBatch:
    product = load_product(db, product_id)
    profile = db.scalar(select(SceneProfile).where(SceneProfile.product_id == product_id))
    if not profile:
        profile = SceneProfile(product_id=product_id)
        db.add(profile); db.flush()
    values = payload.model_dump(exclude_unset=True, exclude={"force"})
    if values.get("reference_sku_id") is not None:
        choose_sku(product, values["reference_sku_id"])
    for key, value in values.items(): setattr(profile, key, value)
    provider = configured_provider()
    sku = choose_sku(product, profile.reference_sku_id)
    ready = scene_readiness(product, profile)
    product.scene_readiness = ready["status"]
    if ready["missing"]:
        db.commit(); raise HTTPException(status_code=409, detail={"message": "场景素材未就绪", "missing": ready["missing"]})
    fingerprint = scene_fingerprint(product, sku, profile, provider)
    existing = db.scalar(select(ImageBatch).options(selectinload(ImageBatch.jobs).selectinload(ImageJob.result_asset)).where(ImageBatch.product_id == product_id, ImageBatch.pipeline_kind == "SCENE", ImageBatch.input_fingerprint == fingerprint).order_by(ImageBatch.version.desc()).limit(1))
    if existing and not payload.force: return existing
    version = (db.scalar(select(func.max(ImageBatch.version)).where(ImageBatch.product_id == product_id, ImageBatch.pipeline_kind == "SCENE")) or 0) + 1
    batch = ImageBatch(product_id=product_id, input_fingerprint=fingerprint, pipeline_version=SCENE_PIPELINE_VERSION, pipeline_kind="SCENE", provider=provider.config.provider, model=provider.config.model, prompt_version=profile.template_version, reference_sku_id=sku.id, version=version, status="PENDING", total_jobs=2)
    db.add(batch); db.flush()
    jobs = [ImageJob(batch_id=batch.id, product_id=product_id, sku_id=sku.id, job_type=role) for role in SCENE_ROLES]
    db.add_all(jobs); product.scene_readiness = "PROCESSING"; db.commit(); dispatcher.dispatch([job.id for job in jobs])
    return load_image_batch(db, batch.id)


@app.get("/api/scene-batches", response_model=list[ImageBatchOut])
def scene_batches(product_id: Optional[int] = Query(default=None), db: Session = Depends(get_db)) -> list[ImageBatch]:
    stmt = select(ImageBatch).options(selectinload(ImageBatch.jobs).selectinload(ImageJob.result_asset)).where(ImageBatch.pipeline_kind == "SCENE")
    if product_id: stmt = stmt.where(ImageBatch.product_id == product_id)
    return db.scalars(stmt.order_by(ImageBatch.created_at.desc()).limit(100)).unique().all()


@app.get("/api/scene-batches/{batch_id}", response_model=ImageBatchOut)
def scene_batch_detail(batch_id: int, db: Session = Depends(get_db)) -> ImageBatch:
    batch = load_image_batch(db, batch_id)
    if batch.pipeline_kind != "SCENE": raise HTTPException(status_code=404, detail="场景批次不存在")
    return batch


@app.post("/api/scene-jobs/{job_id}/retry", response_model=ImageBatchOut)
def retry_scene_job(job_id: int, db: Session = Depends(get_db)) -> ImageBatch:
    job = db.get(ImageJob, job_id)
    if not job or not job.batch or job.batch.pipeline_kind != "SCENE": raise HTTPException(status_code=404, detail="场景任务不存在")
    if job.status not in {"RETRYABLE", "WAITING_SOURCE", "QC_FAILED", "ENGINE_UNAVAILABLE"}: raise HTTPException(status_code=409, detail="当前任务不允许重试")
    job.status, job.stage, job.error_code, job.error_message = "PENDING", "QUEUED", None, None
    db.commit(); dispatcher.dispatch([job.id]); return load_image_batch(db, job.batch_id)


@app.get("/api/products/{product_id}/image-readiness", response_model=ImageReadinessOut)
def product_image_readiness(product_id: int, db: Session = Depends(get_db)) -> dict:
    product = load_product(db, product_id)
    result = readiness(product)
    product.image_readiness = result["status"]
    db.commit()
    return result


@app.post("/api/products/{product_id}/image-batches", response_model=ImageBatchOut)
def create_image_batch(product_id: int, payload: ImageBatchCreate, db: Session = Depends(get_db)) -> ImageBatch:
    product = load_product(db, product_id)
    ready = readiness(product)
    product.image_readiness = ready["status"]
    if ready["missing"]:
        db.commit()
        raise HTTPException(status_code=409, detail={"message": "商品图片素材未就绪", "missing": ready["missing"]})
    fingerprint = input_fingerprint(product)
    existing = db.scalar(
        select(ImageBatch)
        .options(selectinload(ImageBatch.jobs).selectinload(ImageJob.result_asset))
        .where(ImageBatch.product_id == product_id, ImageBatch.input_fingerprint == fingerprint)
        .order_by(ImageBatch.version.desc())
        .limit(1)
    )
    if existing and not payload.force:
        return existing
    latest_version = db.scalar(select(func.max(ImageBatch.version)).where(ImageBatch.product_id == product_id)) or 0
    sellable = [sku for sku in product.skus if sku.is_sellable]
    batch = ImageBatch(product_id=product_id, input_fingerprint=fingerprint, version=latest_version + 1, status="PENDING", total_jobs=len(OUTPUT_ROLES) + len(sellable))
    db.add(batch)
    db.flush()
    jobs = [ImageJob(batch_id=batch.id, product_id=product_id, job_type=role) for role in OUTPUT_ROLES]
    jobs.extend(ImageJob(batch_id=batch.id, product_id=product_id, sku_id=sku.id, job_type="SKU_WHITE") for sku in sellable)
    db.add_all(jobs)
    product.image_readiness = "PROCESSING"
    db.commit()
    dispatcher.dispatch([job.id for job in jobs])
    return load_image_batch(db, batch.id)


@app.get("/api/image-batches", response_model=list[ImageBatchOut])
def image_batches(product_id: Optional[int] = Query(default=None), db: Session = Depends(get_db)) -> list[ImageBatch]:
    stmt = select(ImageBatch).options(selectinload(ImageBatch.jobs).selectinload(ImageJob.result_asset))
    if product_id:
        stmt = stmt.where(ImageBatch.product_id == product_id)
    return db.scalars(stmt.order_by(ImageBatch.created_at.desc()).limit(100)).unique().all()


@app.get("/api/image-batches/{batch_id}", response_model=ImageBatchOut)
def image_batch_detail(batch_id: int, db: Session = Depends(get_db)) -> ImageBatch:
    return load_image_batch(db, batch_id)


@app.post("/api/image-jobs/{job_id}/retry", response_model=ImageBatchOut)
def retry_image_job(job_id: int, db: Session = Depends(get_db)) -> ImageBatch:
    job = db.get(ImageJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="图片任务不存在")
    if job.status not in {"RETRYABLE", "WAITING_SOURCE", "QC_FAILED"}:
        raise HTTPException(status_code=409, detail="该任务当前不允许重试")
    job.status, job.stage, job.error_code, job.error_message = "PENDING", "QUEUED", None, None
    db.commit()
    dispatcher.dispatch([job.id])
    return load_image_batch(db, job.batch_id)


@app.get("/api/assets/{asset_id}/content")
def asset_content(asset_id: int, kind: str = Query(default="generated"), db: Session = Depends(get_db)) -> Response:
    asset = db.get(Asset, asset_id) if kind == "source" else db.get(AssetVersion, asset_id)
    if not asset or not asset.storage_key:
        raise HTTPException(status_code=404, detail="图片不存在")
    try:
        content = configured_storage().get(asset.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="图片文件不存在") from exc
    return Response(content=content, media_type=asset.mime_type or "application/octet-stream", headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})


@app.post("/api/products/{product_id}/listings", response_model=ListingOut)
def add_listing(
    product_id: int, payload: ListingCreate, db: Session = Depends(get_db)
) -> StoreListing:
    product = db.get(ProductMaster, product_id)
    store = db.get(Store, payload.store_id)
    if not product or not store:
        raise HTTPException(status_code=404, detail="商品或店铺不存在")
    existing = db.scalar(
        select(StoreListing).where(
            StoreListing.product_id == product_id, StoreListing.store_id == payload.store_id
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="该店铺版本已经存在")
    listing = StoreListing(
        product_id=product_id,
        store_id=payload.store_id,
        listing_title=payload.listing_title or product.title,
        price=payload.price if payload.price is not None else product.price,
        status="NOT_READY",
    )
    db.add(listing)
    db.commit()
    return db.scalar(
        select(StoreListing)
        .options(selectinload(StoreListing.store))
        .where(StoreListing.id == listing.id)
    )


@app.get("/api/stores", response_model=list[StoreOut])
def stores(db: Session = Depends(get_db)) -> list[Store]:
    return db.scalars(
        select(Store).where(Store.active.is_(True)).order_by(Store.platform, Store.name)
    ).all()


@app.get("/api/imports", response_model=list[BatchOut])
def imports(db: Session = Depends(get_db)) -> list[ImportBatch]:
    return db.scalars(
        select(ImportBatch)
        .options(selectinload(ImportBatch.issues))
        .order_by(ImportBatch.created_at.desc())
        .limit(32)
    ).all()


@app.post("/api/imports/excel", response_model=BatchOut)
def import_excel(file: UploadFile = File(...), db: Session = Depends(get_db)) -> ImportBatch:
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 或 .xlsm 文件")
    content = file.file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件不能超过 15MB")
    try:
        return import_workbook(db, content, file.filename)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=f"Excel 解析失败：{exc}") from exc


@app.post("/api/imports/package", response_model=BatchOut)
def import_local_package(
    files: list[UploadFile] = File(...),
    relative_paths: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
) -> ImportBatch:
    if not files:
        raise HTTPException(status_code=400, detail="请选择商品资料文件夹")
    workbook_files = [item for item in files if (item.filename or "").lower().endswith((".xlsx", ".xlsm"))]
    if len(workbook_files) > 1:
        raise HTTPException(status_code=400, detail="资料文件夹最多包含一个 Excel 文件")
    if workbook_files:
        workbook = workbook_files[0]
        workbook_content = workbook.file.read()
        if len(workbook_content) > 15 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Excel 文件不能超过 15MB")
        batch = import_workbook(db, workbook_content, f"文件夹：{workbook.filename}")
        product_filter = ProductMaster.imported_batch_id == batch.id
    else:
        batch = ImportBatch(filename="本地图片文件夹", status="PROCESSING", total_rows=len(files))
        db.add(batch); db.flush()
        product_filter = ProductMaster.id.is_not(None)
    products = db.scalars(
        select(ProductMaster)
        .options(selectinload(ProductMaster.assets), selectinload(ProductMaster.skus).selectinload(SkuVariant.components))
        .where(product_filter)
    ).unique().all()
    product_by_code = {item.spu_code.lower(): item for item in products}
    sku_by_code = {sku.sku_code.lower(): sku for product in products for sku in product.skus}
    component_by_code = {
        component.component_code.lower(): (product, sku, component)
        for product in products for sku in product.skus for component in sku.components
        if component.component_code
    }
    image_extensions = {".png", ".jpg", ".jpeg", ".webp"}
    matched = 0
    for index, upload in enumerate(files):
        filename = upload.filename or ""
        if Path(filename).suffix.lower() not in image_extensions:
            continue
        content = upload.file.read()
        try:
            meta = validate_image(content)
        except AssetValidationError as exc:
            db.add(ImportIssue(batch_id=batch.id, sheet="Files", row_number=index + 1, identifier=filename, field="image", severity="ERROR", code="INVALID_LOCAL_IMAGE", message=str(exc)))
            continue
        stem = Path(filename).stem.lower().strip()
        product = None; sku = None; component = None; role = None
        if stem.endswith("__detail1") and stem[:-9] in product_by_code:
            product, role = product_by_code[stem[:-9]], "SPU_DETAIL_1_SOURCE"
        elif stem.endswith("__detail2") and stem[:-9] in product_by_code:
            product, role = product_by_code[stem[:-9]], "SPU_DETAIL_2_SOURCE"
        elif stem.endswith("__main") and stem[:-6] in product_by_code:
            product, role = product_by_code[stem[:-6]], "SPU_MAIN_SOURCE"
        elif stem in sku_by_code:
            sku = sku_by_code[stem]; product, role = sku.product, "SKU_SOURCE"
        elif stem in component_by_code:
            product, sku, component = component_by_code[stem]; role = "COMPONENT_SOURCE"
        elif stem in product_by_code:
            product, role = product_by_code[stem], "SPU_MAIN_SOURCE"
        if not product or not role:
            path_label = relative_paths[index] if index < len(relative_paths) else filename
            db.add(ImportIssue(batch_id=batch.id, sheet="Files", row_number=index + 1, identifier=path_label, field="filename", severity="WARNING", code="UNMATCHED_LOCAL_IMAGE", message="图片文件名未匹配 SPU、SKU 或组件编码"))
            continue
        key = f"sources/{product.id}/{meta['sha256'][:20]}-{role.lower()}.{meta['extension']}"
        configured_storage().put(key, content, meta["mime_type"])
        asset = Asset(product=product, sku=sku, component_id=component.id if component else None, asset_type="SOURCE", role=role, url=f"storage://{key}", storage_key=key, sha256=meta["sha256"], mime_type=meta["mime_type"], width=meta["width"], height=meta["height"], byte_size=meta["byte_size"], mirror_status="MIRRORED", rights_status="AUTHORIZED")
        db.add(asset)
        if role == "SPU_MAIN_SOURCE": product.image_rights = "AUTHORIZED"
        matched += 1
    db.flush()
    for product in products:
        for sku in product.skus:
            if sku.is_sellable:
                sku.status = "WAITING_GENERATION" if sku_source_ready(sku) and sku.color else "WAITING_DATA"
        recalculate_product_status(product)
        product.image_readiness = readiness(product)["status"]
    if matched and workbook_files:
        stale = db.scalars(select(ImportIssue).where(ImportIssue.batch_id == batch.id, ImportIssue.code == "MISSING_SKU_IMAGE")).all()
        for issue in stale:
            sku = next((item for item in sku_by_code.values() if item.sku_code == issue.identifier), None)
            if sku and sku_source_ready(sku): db.delete(issue)
    db.flush()
    issues = db.scalars(select(ImportIssue).where(ImportIssue.batch_id == batch.id)).all()
    batch.issue_rows = len(issues); batch.valid_rows = max(batch.total_rows - batch.issue_rows, 0); batch.status = "COMPLETED_WITH_ISSUES" if issues else "COMPLETED"
    db.commit()
    return db.scalar(select(ImportBatch).options(selectinload(ImportBatch.issues)).where(ImportBatch.id == batch.id))


@app.post("/api/imports/finished-images")
def import_finished_images(
    workbook: UploadFile = File(...),
    files: list[UploadFile] = File(...),
    relative_paths: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
) -> dict:
    if not (workbook.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=422, detail="请选择系统提供的 Excel 参数模板")
    workbook_content = workbook.file.read()
    if not workbook_content or len(workbook_content) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Excel 文件必须非空且不超过 15MB")
    uploads: list[tuple[str, str, bytes]] = []
    for index, upload in enumerate(files):
        filename = upload.filename or ""
        if Path(filename).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        path = relative_paths[index] if index < len(relative_paths) else filename
        uploads.append((filename, path, upload.file.read()))
    if not uploads:
        raise HTTPException(status_code=422, detail="所选文件夹中没有 PNG、JPG 或 WebP 图片")
    try:
        result = import_finished_package(db, workbook_content, uploads)
        result["draft_results"] = auto_create_finished_drafts(db, result)
        return result
    except (ValueError, AssetValidationError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _auto_packaging_preset(db: Session, product: ProductMaster) -> PackagingPreset | None:
    existing = db.scalar(select(ProductPackagingSelection).where(ProductPackagingSelection.product_id == product.id))
    if existing:
        return db.get(PackagingPreset, existing.preset_id)
    parameters = json.loads(product.import_parameters_json or "{}")
    package_type = str(parameters.get("外包装类型") or "").strip()
    preferred_slot = 2 if "硬包装" in package_type else 1
    preset = db.scalar(select(PackagingPreset).where(PackagingPreset.slot == preferred_slot))
    if not preset:
        preset = db.scalar(select(PackagingPreset).order_by(PackagingPreset.slot))
    if preset:
        db.add(ProductPackagingSelection(product_id=product.id, preset_id=preset.id))
    return preset


def _ensure_finished_review_ready(db: Session, product: ProductMaster, state: dict) -> dict:
    for platform in ("TEMU", "ALIEXPRESS"):
        copy = next((item for item in product.listing_copies if item.platform == platform), None)
        if not copy:
            copy = upsert_generated_copy(db, product, platform)
            db.flush()
        copy.status = "REVIEWED"
        copy.reviewed_at = utcnow()
        copy.issues_json = "[]"

    for output in state["outputs"]:
        asset = output.get("asset")
        if not asset:
            continue
        asset_row = db.get(AssetVersion, asset["id"])
        if asset_row:
            save_image_decision(db, asset_row, "APPROVED", "成品图导入后自动确认")
    db.commit()
    db.expire_all()

    refreshed = workflow_payload(db, load_product(db, product.id))
    if refreshed["review"]["can_approve"]:
        save_product_decision(db, load_product(db, product.id), refreshed["review"], "APPROVED", "成品图导入后自动确认")
        db.commit()
        db.expire_all()
        refreshed = workflow_payload(db, load_product(db, product.id))
    return refreshed


def auto_create_finished_drafts(db: Session, import_result: dict) -> list[dict]:
    results: list[dict] = []
    stores = db.scalars(
        select(Store).where(
            Store.active.is_(True),
            func.upper(Store.platform).in_(["TEMU", "ALIEXPRESS"]),
            Store.external_shop_id.is_not(None),
        ).order_by(Store.id)
    ).all()
    if not stores:
        return [{"status": "SKIPPED", "error": "没有可用的 TEMU 或速卖通妙手店铺授权"}]
    complete_by_id = {
        item["product_id"]: item
        for item in import_result.get("products", [])
        if not item.get("missing") and not item.get("conflicts")
    }
    for product_id in import_result.get("product_ids", []):
        product = load_product(db, product_id)
        if product_id not in complete_by_id:
            results.append({"product_id": product_id, "spu": product.spu_code, "status": "SKIPPED", "error": "图片或 SKU 匹配不完整"})
            continue
        packaging = _auto_packaging_preset(db, product)
        if not packaging:
            results.append({"product_id": product_id, "spu": product.spu_code, "status": "SKIPPED", "error": "未配置全局包装图，无法创建妙手草稿"})
            continue
        complete_by_id[product_id]["packaging_preset_id"] = packaging.id
        state = workflow_payload(db, product)
        state = _ensure_finished_review_ready(db, product, state)
        if state["status"] != "READY_TO_PUBLISH" or state.get("publish_blockers") or not state["review"]["approved"]:
            results.append({"product_id": product_id, "spu": product.spu_code, "status": "SKIPPED", "error": "导入后未达到创建草稿条件"})
            continue
        draft_results = create_store_drafts(db, load_product(db, product_id), state, [store.id for store in stores], force=True, auto_publish=False)
        for item in draft_results:
            results.append({"product_id": product_id, "spu": product.spu_code, **item})
    return results


@app.post("/api/imports/finished-images/auto-drafts")
def retry_finished_image_drafts(payload: FinishedDraftRetryCreate, db: Session = Depends(get_db)) -> dict:
    product_ids = list(dict.fromkeys(payload.product_ids))
    if not product_ids:
        raise HTTPException(status_code=422, detail="请选择需要创建草稿的商品")
    if len(product_ids) > 100:
        raise HTTPException(status_code=422, detail="单次最多处理 100 个商品")
    products = [
        {"product_id": product_id, "missing": [], "conflicts": []}
        for product_id in product_ids
    ]
    return {"draft_results": auto_create_finished_drafts(db, {"product_ids": product_ids, "products": products})}


def packaging_payload(item: PackagingPreset | None) -> dict | None:
    if not item:
        return None
    return {"id": item.id, "slot": item.slot, "filename": item.original_filename, "width": item.width, "height": item.height, "sha256": item.sha256}


@app.get("/api/packaging-presets")
def list_packaging_presets(db: Session = Depends(get_db)) -> list[dict]:
    by_slot = {item.slot: item for item in db.scalars(select(PackagingPreset).order_by(PackagingPreset.slot)).all()}
    return [{"slot": slot, "image": packaging_payload(by_slot.get(slot))} for slot in (1, 2)]


@app.put("/api/packaging-presets/{slot}")
def save_packaging_preset(slot: int, file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    if slot not in {1, 2}:
        raise HTTPException(status_code=404, detail="包装图片槽只支持 1 或 2")
    content = file.file.read()
    try:
        meta = validate_image(content)
    except AssetValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    item = db.scalar(select(PackagingPreset).where(PackagingPreset.slot == slot))
    key = f"packaging/preset-{slot}-{meta['sha256'][:20]}.{meta['extension']}"
    configured_storage().put(key, content, meta["mime_type"])
    if not item:
        item = PackagingPreset(slot=slot, storage_key=key, sha256=meta["sha256"], mime_type=meta["mime_type"], width=meta["width"], height=meta["height"], byte_size=meta["byte_size"])
        db.add(item)
    item.storage_key = key
    item.sha256 = meta["sha256"]
    item.mime_type = meta["mime_type"]
    item.width = meta["width"]
    item.height = meta["height"]
    item.byte_size = meta["byte_size"]
    item.original_filename = file.filename
    db.commit()
    db.refresh(item)
    return packaging_payload(item)


@app.delete("/api/packaging-presets/{slot}", status_code=204)
def delete_packaging_preset(slot: int, db: Session = Depends(get_db)) -> None:
    item = db.scalar(select(PackagingPreset).where(PackagingPreset.slot == slot))
    if not item:
        raise HTTPException(status_code=404, detail="包装图片不存在")
    if db.scalar(select(ProductPackagingSelection.id).where(ProductPackagingSelection.preset_id == item.id).limit(1)):
        raise HTTPException(status_code=409, detail="该包装图已被商品使用，请先改选另一张包装图")
    db.delete(item)
    db.commit()


@app.get("/api/packaging-presets/{slot}/content")
def packaging_preset_content(slot: int, db: Session = Depends(get_db)) -> Response:
    item = db.scalar(select(PackagingPreset).where(PackagingPreset.slot == slot))
    if not item:
        raise HTTPException(status_code=404, detail="包装图片不存在")
    return Response(content=configured_storage().get(item.storage_key), media_type=item.mime_type)


def select_packaging(db: Session, product_id: int, preset_id: int) -> dict:
    product = db.get(ProductMaster, product_id)
    preset = db.get(PackagingPreset, preset_id)
    if not product or not preset:
        raise HTTPException(status_code=404, detail="商品或包装图片不存在")
    selection = db.scalar(select(ProductPackagingSelection).where(ProductPackagingSelection.product_id == product_id))
    if not selection:
        selection = ProductPackagingSelection(product_id=product_id, preset_id=preset_id)
        db.add(selection)
    else:
        selection.preset_id = preset_id
    return {"product_id": product_id, "preset": packaging_payload(preset)}


@app.put("/api/products/{product_id}/packaging-selection")
def save_product_packaging(product_id: int, payload: PackagingSelectionPatch, db: Session = Depends(get_db)) -> dict:
    result = select_packaging(db, product_id, payload.preset_id)
    db.commit()
    return result


@app.put("/api/products/packaging-selection/bulk")
def save_bulk_product_packaging(payload: PackagingBulkPatch, db: Session = Depends(get_db)) -> dict:
    results = [select_packaging(db, product_id, payload.preset_id) for product_id in payload.product_ids]
    db.commit()
    return {"results": results}


@app.get("/api/imports/template")
def download_template() -> StreamingResponse:
    workbook = template_workbook()
    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=product-import-template.xlsx"},
    )
