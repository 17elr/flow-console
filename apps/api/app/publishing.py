from __future__ import annotations

import hashlib
import io
import json
import os
import re
import zipfile
from hashlib import sha256
from datetime import datetime, timezone
from pathlib import Path
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from PIL import Image
import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .image_pipeline import OUTPUT_ROLES
from .copywriting import clean_generated_description
from .miaoshou import MiaoshouError, configured_miaoshou, normalize_sku_classification
from .models import AssetVersion, MiaoshouDraft, ProductMaster, SkuAsset, Store, StoreAutomationConfig, StoreListing, ProductPackagingSelection, PackagingPreset
from .scene_pipeline import SCENE_ROLES
from .storage import configured_storage

PUBLISHING_PAYLOAD_VERSION = "temu-attrs-v14-public-image-base"
ALIEXPRESS_PACKAGE_VERSION = "miaoshou-local-format2-v3"
MIAOSHOU_FORMAT2_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "miaoshou-local-material-format2.xlsx"
MIAOSHOU_FORMAT2_HEADERS = (
    "* 货号", "* 产品名称", "货币类型", "货源链接", "货源平台", "详情描述", "属性",
    "规格1（test1）", "SKU规格2（容量）", "平台SKU", "* SKU售价", "SKU库存", "SKU重量(KG)", "SKU尺寸(CM)",
)


def _public_publish_image(provider, storage, source_key: str, public_base: str, cache: dict[str, str]) -> str:
    """Mirror a compact JPEG for ERP fetchers that reject large PNG objects."""
    if source_key in cache:
        return cache[source_key]
    raw = storage.get(source_key)
    with Image.open(io.BytesIO(raw)) as image:
        image = image.convert("RGB")
        image.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=78, optimize=True, progressive=False, subsampling=0)
    digest = sha256(out.getvalue()).hexdigest()[:20]
    key = f"publish-assets/{digest}.jpg"
    storage.put(key, out.getvalue(), "image/jpeg")
    url = f"{public_base}/{key}"
    cache[source_key] = url
    return url


def _verify_public_image_url(url: str) -> None:
    if not url.startswith(("http://", "https://")):
        raise MiaoshouError("公开图片链接未配置，无法让妙手抓取图片")
    try:
        response = httpx.head(url, follow_redirects=True, timeout=12.0)
        response.raise_for_status()
    except Exception as exc:
        raise MiaoshouError(f"公开图片链接无法访问，妙手将无法显示图片：{url}") from exc


def platform_key(store: Store) -> str:
    return "ALIEXPRESS" if store.platform.upper() == "ALIEXPRESS" else store.platform.upper()


def _parameter(parameters: dict, *names: str, default=None):
    def norm(value: object) -> str:
        return "".join(character for character in str(value or "").casefold() if character.isalnum())

    wanted = {norm(name) for name in names}
    for key, value in parameters.items():
        if norm(key) in wanted and value not in (None, ""):
            return value
    return default


def _latest_sku_assets(db: Session, product: ProductMaster) -> dict[int, SkuAsset]:
    sku_ids = [sku.id for sku in product.skus]
    rows = db.scalars(select(SkuAsset).where(SkuAsset.sku_id.in_(sku_ids)).order_by(SkuAsset.created_at.desc())).all() if sku_ids else []
    result: dict[int, SkuAsset] = {}
    for row in rows:
        result.setdefault(row.sku_id, row)
    return result


def _packaging_preset(db: Session, product: ProductMaster) -> PackagingPreset | None:
    selection = db.scalar(select(ProductPackagingSelection).where(ProductPackagingSelection.product_id == product.id))
    return db.get(PackagingPreset, selection.preset_id) if selection else None


def _style_sheet(sheet, widths: list[int]) -> None:
    sheet.freeze_panes = "A2"
    sheet.sheet_view.showGridLines = False
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor="176B4A")
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(vertical="center")
    sheet.row_dimensions[1].height = 24
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            cell.border = Border(bottom=Side(style="thin", color="D9E2DD"))
    sheet.auto_filter.ref = sheet.dimensions
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_view.zoomScale = 90
    for row in range(2, sheet.max_row + 1):
        sheet.row_dimensions[row].height = 34


def build_listing_workbook(db: Session, product: ProductMaster, store: Store) -> bytes:
    copy = next((item for item in product.listing_copies if item.platform == platform_key(store)), None)
    if not copy:
        raise ValueError(f"Missing {store.platform} listing copy")
    bullets = json.loads(copy.bullet_points_json or "[]")
    sku_names = json.loads(copy.sku_names_json or "{}")
    sku_assets = _latest_sku_assets(db, product)
    config = db.scalar(select(StoreAutomationConfig).where(StoreAutomationConfig.store_id == store.id))
    multiplier = config.price_multiplier if config else 1.0
    workbook = Workbook()
    product_sheet = workbook.active
    product_sheet.title = "Product"
    product_sheet.append(["SPU", "Platform", "Store", "Title", "Category", "Price", "Currency", "Stock", "Dimensions", "Bullet Points", "Description"])
    product_sheet.append([product.spu_code, store.platform, store.name, product.title, product.category, round((product.price or 0) * multiplier, 2), product.currency, product.stock, product.dimensions, "\n".join(bullets), clean_generated_description(copy.description)])
    product_sheet["F2"].number_format = '"$"#,##0.00'
    _style_sheet(product_sheet, [18, 14, 24, 42, 18, 12, 10, 10, 18, 48, 60])

    sku_sheet = workbook.create_sheet("SKUs")
    sku_sheet.append(["SKU", "SKU Name", "Color", "Size", "Set Quantity", "Price", "Stock", "Image File"])
    for sku in product.skus:
        asset = sku_assets.get(sku.id)
        image_name = f"产品图片/{product.spu_code}/SKU图/{sku.sku_code}.png" if asset else ""
        sku_sheet.append([sku.sku_code, sku_names.get(str(sku.id), sku.sku_code), sku.color, sku.size, sku.quantity, round(((sku.price or product.price) or 0) * multiplier, 2), sku.stock, image_name])
        sku_sheet.cell(sku_sheet.max_row, 6).number_format = '"$"#,##0.00'
    _style_sheet(sku_sheet, [22, 28, 16, 16, 14, 12, 12, 42])

    image_sheet = workbook.create_sheet("Image Mapping")
    image_sheet.append(["Image Role", "SKU", "File", "Width", "Height", "SHA-256"])
    latest_assets: dict[tuple[str, int | None], AssetVersion] = {}
    for asset in db.scalars(select(AssetVersion).where(AssetVersion.product_id == product.id).order_by(AssetVersion.created_at.desc())).all():
        key = (asset.role, None)
        latest_assets.setdefault(key, asset)
    for role in [*OUTPUT_ROLES, *SCENE_ROLES]:
        asset = latest_assets.get((role, None))
        if asset:
            image_sheet.append([role, "", f"产品图片/{product.spu_code}/产品主图/{role}.png", asset.width, asset.height, asset.sha256])
    for sku in product.skus:
        link = sku_assets.get(sku.id)
        if link:
            asset = db.get(AssetVersion, link.asset_version_id)
            image_sheet.append(["SKU_WHITE", sku.sku_code, f"产品图片/{product.spu_code}/SKU图/{sku.sku_code}.png", asset.width, asset.height, asset.sha256])
    _style_sheet(image_sheet, [24, 22, 42, 10, 10, 66])

    parameter_sheet = workbook.create_sheet("Category Parameters")
    parameter_sheet.append(["Parameter", "Value"])
    parameters = json.loads(product.import_parameters_json or "{}")
    packaging = _packaging_preset(db, product)
    if packaging:
        parameters["外包装图片"] = f"产品图片/{product.spu_code}/尺寸图表/包装图{packaging.slot}.{packaging.mime_type.split('/')[-1].replace('jpeg', 'jpg')}"
    for key, value in parameters.items():
        parameter_sheet.append([key, "" if value is None else value])
    _style_sheet(parameter_sheet, [46, 70])

    instructions = workbook.create_sheet("Instructions")
    instructions.append(["Step", "Instruction"])
    instructions.append([1, "Import Product and SKUs using the target platform or ERP import function."])
    instructions.append([2, "Keep every SKU image mapped to the exact SKU code shown in the SKUs sheet."])
    instructions.append([3, "Review all fields and images before submitting the platform draft."])
    instructions.append([4, "This package creates a draft only. It does not authorize automatic live publishing."])
    _style_sheet(instructions, [10, 90])
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def build_aliexpress_workbook(db: Session, product: ProductMaster, store: Store) -> bytes:
    """Fill Miaoshou's official local-material format 2 workbook."""
    copy = next((item for item in product.listing_copies if item.platform == "ALIEXPRESS"), None)
    if not copy:
        raise ValueError("Missing AliExpress listing copy")
    parameters = json.loads(product.import_parameters_json or "{}")
    # The source AliExpress workbook is authoritative for currency and price.
    # Store pricing multipliers belong to API publishing, not local-material
    # import, where they would silently change the uploaded spreadsheet data.
    workbook = load_workbook(MIAOSHOU_FORMAT2_TEMPLATE)
    sheet = workbook.worksheets[0]
    if tuple(cell.value for cell in sheet[2]) != MIAOSHOU_FORMAT2_HEADERS:
        raise ValueError("Miaoshou local-material template headers changed")
    sheet.delete_rows(3, sheet.max_row - 2)
    sheet["H2"] = "规格1（颜色）"
    sheet["I2"] = "SKU规格2（尺寸）"

    source_link = _parameter(parameters, "货源下单链接", "货源链接", default="")
    source_id = source_link if str(source_link).startswith(("http://", "https://")) else product.spu_code
    source_platform = "1688" if "1688.com" in str(source_link) else ("速卖通" if "aliexpress." in str(source_link) else "手动创建")
    dimension_values = [
        _parameter(parameters, name, default=None) for name in (
            "包装最长边 CM(批量)", "包装次长边 CM(批量)", "包装最短边 CM(批量)"
        )
    ]
    dimensions = "；".join(str(value) for value in dimension_values) if all(value not in (None, "") for value in dimension_values) else ""
    kilograms = _parameter(parameters, "重量 KG(批量)", "包装重量 KG(批量)", "商品净重 KG(批量)", default=None)
    if kilograms in (None, "") and product.weight_g is not None:
        kilograms = round(product.weight_g / 1000, 3)
    skus = [sku for sku in product.skus if sku.is_sellable]
    if not skus:
        raise ValueError("No sellable SKUs for Miaoshou local-material import")
    for index, sku in enumerate(skus):
        sheet.append([
            product.spu_code,
            product.title if index == 0 else None,
            "CNY" if index == 0 else None,
            source_id if index == 0 else None,
            source_platform if index == 0 else None,
            clean_generated_description(copy.description) if index == 0 else None,
            None,
            _miaoshou_spec_name(sku),
            sku.size or None,
            sku.sku_code,
            round((sku.price if sku.price is not None else product.price) or 0, 2),
            sku.stock,
            kilograms,
            dimensions,
        ])
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _miaoshou_spec_name(sku) -> str:
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", (sku.color or sku.sku_code).strip()) or sku.sku_code


def _jpeg_image(content: bytes) -> bytes:
    with Image.open(io.BytesIO(content)) as image:
        image = image.convert("RGB")
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=90)
        return output.getvalue()


def _aliexpress_material_package(db: Session, product: ProductMaster, store: Store) -> tuple[bytes, str]:
    stream = io.BytesIO()
    sku_assets = _latest_sku_assets(db, product)
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        root = "产品素材包模版2/本地导入素材/"
        archive.writestr("产品素材包模版2/", "")
        archive.writestr(root, "")
        archive.writestr(f"{root}产品导入表格.xlsx", build_aliexpress_workbook(db, product, store))
        image_root = f"{root}产品图片/{product.spu_code}/"
        archive.writestr(f"{root}产品图片/", "")
        archive.writestr(image_root, "")
        for folder in ("SKU图", "产品主图", "产品视频", "产品证书", "尺寸图表", "详情图"):
            archive.writestr(f"{image_root}{folder}/", "")
        assets = db.scalars(select(AssetVersion).where(
            AssetVersion.product_id == product.id,
            AssetVersion.role.in_([*OUTPUT_ROLES, *SCENE_ROLES]),
        ).order_by(AssetVersion.created_at.desc())).all()
        latest = {}
        for asset in assets:
            latest.setdefault(asset.role, asset)
        # Miaoshou shows only 产品主图 in the main product-image section. Put
        # every generated product image there, while also retaining detail
        # copies in 详情图 for description-image import.
        main_roles = (
            "SPU_WHITE_MAIN", "SPU_DETAIL_1", "SPU_DETAIL_2",
            "SPU_SIZE_INFO", "SCENE_MODEL_WEAR", "SCENE_LIFESTYLE",
        )
        detail_roles = main_roles
        for index, role in enumerate(main_roles, 1):
            if asset := latest.get(role):
                archive.writestr(f"{image_root}产品主图/主图_{index}.jpg", _jpeg_image(configured_storage().get(asset.storage_key)))
        for index, role in enumerate(detail_roles, 1):
            if asset := latest.get(role):
                archive.writestr(f"{image_root}详情图/详情图_{index}.jpg", _jpeg_image(configured_storage().get(asset.storage_key)))
        if asset := latest.get("SPU_SIZE_INFO"):
            archive.writestr(f"{image_root}尺寸图表/尺寸图表.jpg", _jpeg_image(configured_storage().get(asset.storage_key)))
        packaging = _packaging_preset(db, product)
        if packaging:
            try:
                content = configured_storage().get(packaging.storage_key)
            except FileNotFoundError:
                content = None
            if content:
                archive.writestr(f"{image_root}详情图/详情图_{len(detail_roles) + 1}.jpg", _jpeg_image(content))
        seen_colors = set()
        for sku in product.skus:
            if not sku.is_sellable or not (link := sku_assets.get(sku.id)):
                continue
            color = _miaoshou_spec_name(sku)
            if color in seen_colors:
                continue
            seen_colors.add(color)
            asset = db.get(AssetVersion, link.asset_version_id)
            archive.writestr(f"{image_root}SKU图/{color}_1.jpg", _jpeg_image(configured_storage().get(asset.storage_key)))
    return stream.getvalue(), f"{product.spu_code}-{store.platform.lower()}-import.zip"


def listing_package(db: Session, product: ProductMaster, store: Store) -> tuple[bytes, str]:
    if platform_key(store) == "ALIEXPRESS":
        return _aliexpress_material_package(db, product, store)
    stream = io.BytesIO()
    sku_assets = _latest_sku_assets(db, product)
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        workbook = build_listing_workbook(db, product, store)
        root = "本地导入素材/"
        archive.writestr(f"{root}产品导入表格.xlsx", workbook)
        packaging = _packaging_preset(db, product)
        if packaging:
            extension = packaging.mime_type.split("/")[-1].replace("jpeg", "jpg")
            try:
                packaging_content = configured_storage().get(packaging.storage_key)
            except FileNotFoundError:
                # Packaging is optional for Miaoshou local-material imports. A
                # stale preset record must not block the complete product pack.
                packaging_content = None
            if packaging_content:
                archive.writestr(f"{root}产品图片/{product.spu_code}/尺寸图表/包装图{packaging.slot}.{extension}", packaging_content)
        for asset in db.scalars(select(AssetVersion).where(AssetVersion.product_id == product.id, AssetVersion.role.in_([*OUTPUT_ROLES, *SCENE_ROLES])).order_by(AssetVersion.created_at.desc())).all():
            name = f"{root}产品图片/{product.spu_code}/产品主图/{asset.role}.png"
            if name not in archive.namelist():
                archive.writestr(name, configured_storage().get(asset.storage_key))
        for sku in product.skus:
            link = sku_assets.get(sku.id)
            if link:
                asset = db.get(AssetVersion, link.asset_version_id)
                archive.writestr(f"{root}产品图片/{product.spu_code}/SKU图/{sku.sku_code}.png", configured_storage().get(asset.storage_key))
    return stream.getvalue(), f"{product.spu_code}-{store.platform.lower()}-import.zip"


def create_aliexpress_import_packages(
    db: Session,
    product: ProductMaster,
    state: dict,
    store_ids: list[int],
    *,
    force: bool = False,
) -> list[dict]:
    """Create local AliExpress import packages without calling any platform API."""
    results: list[dict] = []
    for store_id in store_ids:
        store = db.get(Store, store_id)
        if not store or not store.active:
            results.append({"store_id": store_id, "status": "FAILED", "error": "店铺不存在或已停用"})
            continue
        if platform_key(store) != "ALIEXPRESS":
            results.append({"store_id": store.id, "status": "FAILED", "error": "导入包只能为速卖通店铺生成"})
            continue
        copy = next((item for item in product.listing_copies if item.platform == "ALIEXPRESS"), None)
        if not copy or copy.status != "REVIEWED":
            results.append({"store_id": store.id, "status": "FAILED", "error": "请先确认速卖通英文文案"})
            continue

        key = f"{publishing_key(db, product, store, state, auto_publish=False)}:manual-import:{ALIEXPRESS_PACKAGE_VERSION}"
        draft = db.scalar(select(MiaoshouDraft).where(MiaoshouDraft.idempotency_key == key))
        if draft and draft.status == "PACKAGE_READY" and draft.package_key and not force:
            results.append({
                "store_id": store.id,
                "status": "PACKAGE_READY",
                "draft_id": draft.id,
                "package_available": True,
                "idempotent": True,
            })
            continue
        if not draft:
            draft = MiaoshouDraft(
                product_id=product.id,
                store_id=store.id,
                idempotency_key=key,
                channel="ALIEXPRESS",
                status="PENDING",
                attempt_count=1,
            )
            db.add(draft)
            db.flush()
        else:
            draft.status = "PENDING"
            draft.error_message = None
            draft.attempt_count = (draft.attempt_count or 0) + 1

        try:
            package, filename = listing_package(db, product, store)
            package_key = f"publish/{product.spu_code}/{store.id}/{key[:16]}-{filename}"
            configured_storage().put(package_key, package, "application/zip")
            draft.status = "PACKAGE_READY"
            draft.external_id = None
            draft.package_key = package_key
            draft.error_message = None
            draft.response_json = json.dumps(
                {"mode": "manual_import", "filename": filename, "byte_size": len(package)},
                ensure_ascii=False,
            )
            listing = db.scalar(
                select(StoreListing).where(
                    StoreListing.product_id == product.id,
                    StoreListing.store_id == store.id,
                )
            )
            if not listing:
                listing = StoreListing(
                    product_id=product.id,
                    store_id=store.id,
                    listing_title=product.title,
                    price=product.price,
                    status="PACKAGE_READY",
                )
                db.add(listing)
            elif not listing.external_product_id:
                listing.status = "PACKAGE_READY"
                listing.response_json = draft.response_json
            results.append({
                "store_id": store.id,
                "status": "PACKAGE_READY",
                "draft_id": draft.id,
                "package_available": True,
                "idempotent": False,
            })
        except (OSError, ValueError) as exc:
            draft.status = "FAILED"
            draft.error_message = str(exc)
            results.append({"store_id": store.id, "status": "FAILED", "draft_id": draft.id, "error": str(exc)})
    db.commit()
    return results


def publishing_key(db: Session, product: ProductMaster, store: Store, state: dict, *, auto_publish: bool = False) -> str:
    platform_copy = next((item for item in product.listing_copies if item.platform == platform_key(store)), None)
    config = db.scalar(select(StoreAutomationConfig).where(StoreAutomationConfig.store_id == store.id))
    payload = {
        "payload_version": PUBLISHING_PAYLOAD_VERSION,
        "publish_mode": "auto_publish" if auto_publish else "draft_only",
        "public_asset_base_url": os.getenv("PUBLIC_ASSET_BASE_URL", "").rstrip("/"),
        "spu": product.spu_code,
        "store": store.id,
        "review": state["review"]["fingerprint"],
        "copy": [platform_copy.id, platform_copy.updated_at.isoformat()] if platform_copy else None,
        "skus": [(sku.sku_code, sku.price, sku.stock) for sku in product.skus],
        "category_parameters": json.loads(product.import_parameters_json or "{}"),
        "store_config": [config.price_multiplier, config.visual_profile] if config else [1.0, "neutral-commerce"],
        "packaging": (lambda item: [item.id, item.sha256] if item else None)(_packaging_preset(db, product)),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _publish_verification_evidence(verification: dict) -> dict:
    return {
        "state": verification.get("state", "unknown"),
        "verified": bool(verification.get("verified")),
        "checked_at": verification.get("checked_at"),
        "error": verification.get("error"),
    }


def _save_existing_publish_verification(
    db: Session,
    draft: MiaoshouDraft,
    listing: StoreListing | None,
    verification: dict,
) -> None:
    # Historical PUBLISHED values may only mean the asynchronous task was
    # accepted. Miaoshou's published bucket is the authority for final state.
    draft.status = "PUBLISHED" if verification.get("verified") else "PUBLISHING"
    existing = json.loads(draft.response_json or "{}")
    existing["publish_verification"] = _publish_verification_evidence(verification)
    draft.response_json = json.dumps(existing, ensure_ascii=False)[:20000]
    draft.error_message = verification.get("error")
    if listing:
        listing.status = draft.status
        listing.external_product_id = draft.external_id
        listing.response_json = draft.response_json
        listing.error_message = draft.error_message
    db.commit()


def create_store_drafts(db: Session, product: ProductMaster, state: dict, store_ids: list[int], *, respect_automation_limits: bool = False, force: bool = False, auto_publish: bool = False) -> list[dict]:
    results: list[dict] = []
    provider = configured_miaoshou()
    for store_id in store_ids:
        store = db.get(Store, store_id)
        if not store or not store.active:
            results.append({"store_id": store_id, "status": "FAILED", "error": "店铺不存在或已停用"})
            continue
        copy = next((item for item in product.listing_copies if item.platform == platform_key(store)), None)
        if not copy or copy.status != "REVIEWED":
            results.append({"store_id": store.id, "status": "FAILED", "error": f"请先确认 {store.platform} 英文文案"})
            continue
        key = publishing_key(db, product, store, state, auto_publish=auto_publish)
        config = db.scalar(select(StoreAutomationConfig).where(StoreAutomationConfig.store_id == store.id))
        multiplier = config.price_multiplier if config else 1.0
        draft = db.scalar(select(MiaoshouDraft).where(MiaoshouDraft.idempotency_key == key))
        if draft:
            listing = db.scalar(select(StoreListing).where(StoreListing.product_id == product.id, StoreListing.store_id == store.id))
            if (
                store.platform.upper() == "TEMU"
                and draft.status in {"PUBLISHING", "PUBLISHED"}
                and not force
            ):
                try:
                    verification = provider.wait_for_publish(
                        draft.external_id or "", store.mode, attempts=1, interval=2.0
                    )
                    repair_response = None
                    publish_response = None
                    if not verification.get("verified") and auto_publish:
                        parameters = json.loads(product.import_parameters_json or "{}")
                        cid = _parameter(parameters, "妙手类目ID", "妙手类目ID cid", "类目ID", default="29542")
                        repair_response = provider.ensure_shop_item_number(store.external_shop_id or "", draft.external_id or "", cid, product.spu_code, store.mode, {sku.sku_code: int(sku.stock if sku.stock is not None else product.stock or 0) for sku in product.skus})
                        publish_response = provider.publish_product(
                            store.external_shop_id or "", draft.external_id or "", store.mode
                        )
                        verification = provider.wait_for_publish(draft.external_id or "", store.mode)
                    _save_existing_publish_verification(db, draft, listing, verification)
                    if repair_response is not None or publish_response is not None:
                        evidence = json.loads(draft.response_json or "{}")
                        evidence["item_number_repair"] = {
                            "updated": bool((repair_response or {}).get("updated")),
                            "response": (repair_response or {}).get("response", {}),
                        }
                        evidence["publish_retry"] = (publish_response or {}).get("response", {})
                        draft.response_json = json.dumps(evidence, ensure_ascii=False)[:20000]
                        if listing:
                            listing.response_json = draft.response_json
                        db.commit()
                    results.append({
                        "store_id": store.id,
                        "status": draft.status,
                        "draft_id": draft.id,
                        "external_id": draft.external_id,
                        "package_available": bool(draft.package_key),
                        "idempotent": True,
                        "verification_required": not verification.get("verified"),
                        "verification": _publish_verification_evidence(verification),
                    })
                except MiaoshouError as exc:
                    # A failed authority check cannot preserve a historical
                    # success claim. Keep the task pending and expose evidence.
                    verification = {
                        "state": "unknown",
                        "verified": False,
                        "checked_at": datetime.now(timezone.utc).isoformat(),
                        "error": str(exc),
                    }
                    _save_existing_publish_verification(db, draft, listing, verification)
                    results.append({
                        "store_id": store.id,
                        "status": "PUBLISHING",
                        "draft_id": draft.id,
                        "external_id": draft.external_id,
                        "error": str(exc),
                        "idempotent": True,
                        "verification_required": True,
                        "verification": _publish_verification_evidence(verification),
                    })
                continue
            # Older runs may have created the collection-box item before the
            # publish step was wired in. Upgrade those records in place instead
            # of treating them as complete and silently skipping publication.
            if draft.status == "DRAFT_CREATED" and not force and store.platform.upper() == "TEMU" and auto_publish:
                try:
                    claim_response = provider.claim_product(store.external_shop_id or "", draft.external_id or "", store.mode)
                    parameters = json.loads(product.import_parameters_json or "{}")
                    cid = _parameter(parameters, "妙手类目ID", "妙手类目ID cid", "类目ID", default="29542")
                    claim_verified = provider.wait_for_claim(store.external_shop_id or "", draft.external_id or "", cid, store.mode)
                    published = provider.publish_product(store.external_shop_id or "", draft.external_id or "", store.mode)
                    verification = provider.wait_for_publish(draft.external_id or "", store.mode)
                    draft.status = "PUBLISHED" if verification.get("verified") else "PUBLISHING"
                    existing = json.loads(draft.response_json or "{}")
                    existing["publish"] = published.get("response", {})
                    existing["claim"] = claim_response.get("response", {})
                    existing["claim_verification"] = claim_verified.get("response", {})
                    existing["publish_verification"] = _publish_verification_evidence(verification)
                    draft.response_json = json.dumps(existing, ensure_ascii=False)[:20000]
                    listing = db.scalar(select(StoreListing).where(StoreListing.product_id == product.id, StoreListing.store_id == store.id))
                    if listing:
                        listing.status = draft.status
                        listing.response_json = draft.response_json
                    db.commit()
                    results.append({"store_id": store.id, "status": draft.status, "draft_id": draft.id, "package_available": bool(draft.package_key), "idempotent": True, "verification_required": not verification.get("verified")})
                except MiaoshouError as exc:
                    results.append({"store_id": store.id, "status": "FAILED", "draft_id": draft.id, "error": str(exc), "idempotent": True})
                continue
            if draft.status in {"DRAFT_CREATED", "PUBLISHING", "PUBLISHED", "PACKAGE_READY"} and not force:
                results.append({"store_id": store.id, "status": draft.status, "draft_id": draft.id, "external_id": draft.external_id, "package_available": bool(draft.package_key), "idempotent": True})
                continue
            draft.status = "PENDING"
            draft.error_message = None
            draft.attempt_count = (draft.attempt_count or 0) + 1
        else:
            draft = MiaoshouDraft(product_id=product.id, store_id=store.id, idempotency_key=key, channel=store.platform, status="PENDING", attempt_count=1)
            db.add(draft)
            db.flush()
        if respect_automation_limits and config and not config.active:
            results.append({"store_id": store.id, "status": "SKIPPED", "error": "店铺未启用自动运行"})
            continue
        if respect_automation_limits and config:
            day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
            created_today = db.scalar(
                select(func.count(MiaoshouDraft.id)).where(
                    MiaoshouDraft.store_id == store.id,
                    MiaoshouDraft.created_at >= day_start,
                    MiaoshouDraft.status.in_(["DRAFT_CREATED", "PUBLISHED", "PACKAGE_READY"]),
                )
            ) or 0
            if created_today >= config.max_daily:
                results.append({"store_id": store.id, "status": "SKIPPED", "error": f"已达到店铺每日上限 {config.max_daily}"})
                continue
        listing = db.scalar(select(StoreListing).where(StoreListing.product_id == product.id, StoreListing.store_id == store.id))
        if not listing:
            listing = StoreListing(product_id=product.id, store_id=store.id, listing_title=product.title, price=round((product.price or 0) * multiplier, 2), status="PENDING")
            db.add(listing)
        if store.platform.upper() == "TEMU" and provider.status()["temu_api_ready"]:
            try:
                packaging = _packaging_preset(db, product)
                parameters = json.loads(product.import_parameters_json or "{}")
                classification_code, _classification_name = normalize_sku_classification(
                    _parameter(parameters, "SKU分类", default="单品")
                )
                package_length = _parameter(parameters, "包装最长边 CM(批量)", "包装最长边(cm)", "包装最长边（cm）", default="")
                package_width = _parameter(parameters, "包装次长边 CM(批量)", "包装次长边(cm)", "包装次长边（cm）", default="")
                package_height = _parameter(parameters, "包装最短边 CM(批量)", "包装最短边(cm)", "包装最短边（cm）", default="")
                package_weight = _parameter(parameters, "重量 KG(批量)", "包装重量 KG(批量)", "包装重量(kg)", "包装重量(g)", "包装重量（g）", default="")
                net_weight = _parameter(parameters, "重量 KG(批量)", "商品净重 KG(批量)", "商品净重(kg)", "商品净重(g)", "商品净重（g）", default="")
                sku_piece_count = int(_parameter(parameters, "SKU内单品件数", default=1) or 1)
                individually_packed = int(
                    _parameter(parameters, "individuallyPacked", "SKU是否独立包装", "是否独立包装", default=0)
                    in (1, "1", True, "是独立包装")
                )
                public_base = provider.public_asset_base_url
                if not public_base:
                    raise MiaoshouError("PUBLIC_ASSET_BASE_URL 未配置，无法创建带图片的妙手草稿")
                asset_storage = configured_storage()
                publish_image_cache: dict[str, str] = {}
                # The marketplace main-image list is exactly the six source roles,
                # in folder order. Never mix SKU assets or historical versions.
                main_role_order = (
                    "SPU_WHITE_MAIN",
                    "SPU_DETAIL_1",
                    "SPU_DETAIL_2",
                    "SPU_SIZE_INFO",
                    "SCENE_MODEL_WEAR",
                    "SCENE_LIFESTYLE",
                )
                candidates = db.scalars(
                    select(AssetVersion)
                    .where(AssetVersion.product_id == product.id, AssetVersion.role.in_(main_role_order))
                    .order_by(AssetVersion.created_at.desc(), AssetVersion.id.desc())
                ).all()
                latest_by_role: dict[str, AssetVersion] = {}
                for asset in candidates:
                    latest_by_role.setdefault(asset.role, asset)
                image_urls = [
                    _public_publish_image(provider, asset_storage, latest_by_role[role].storage_key, public_base, publish_image_cache)
                    for role in main_role_order
                    if role in latest_by_role
                ]
                if image_urls:
                    _verify_public_image_url(image_urls[0])
                packaging_urls = [
                    _public_publish_image(
                        provider, asset_storage, packaging.storage_key, public_base, publish_image_cache
                    )
                ] if packaging else []
                sku_links = _latest_sku_assets(db, product)
                sku_map = {}
                for sku in product.skus:
                    link = sku_links.get(sku.id)
                    sku_asset = db.get(AssetVersion, link.asset_version_id) if link else None
                    sku_map[f";{sku.sku_code};"] = {
                        "itemNum": sku.sku_code,
                        "length": str(package_length),
                        "width": str(package_width),
                        "height": str(package_height),
                        "imgUrl": _public_publish_image(provider, asset_storage, sku_asset.storage_key, public_base, publish_image_cache) if sku_asset else "",
                        "price": str(round(((sku.price or product.price) or 0) * multiplier, 2)),
                        "stock": int(sku.stock if sku.stock is not None else product.stock or 0),
                        "weight": package_weight,
                        "netWeight": net_weight,
                        "skuClassification": classification_code,
                        "skuClassificationNum": 1,
                        "skuClassificationQuantity": sku_piece_count,
                        "skuClassificationCount": sku_piece_count,
                        "skuClassificationNumber": sku_piece_count,
                        "skuNum": sku_piece_count,
                        "quantity": sku_piece_count,
                        "numberOfPieces": sku_piece_count,
                        "numberOfPiecesNew": sku_piece_count,
                        "pieceUnitCode": 1,
                        "pieceNewUnitCode": 1,
                        "mixedType": 1 if classification_code == 3 else 0,
                        "individuallyPacked": individually_packed,
                    }
                excel_title = str(_parameter(parameters, "商品标题", "商品名称", default=product.title) or product.title).strip()
                draft_payload = {"spu": product.spu_code, "title": excel_title, "description": clean_generated_description(copy.description), "price": round((product.price or 0) * multiplier, 2), "stock": product.stock, "store": store.name, "external_shop_id": store.external_shop_id, "category": product.category, "category_parameters": parameters, "packaging_img_urls": packaging_urls, "img_urls": image_urls, "description_img_urls": image_urls, "sku_map": sku_map, "dimensions": {"length": package_length, "width": package_width, "height": package_height}, "weight": package_weight}
                if platform_key(store) == "ALIEXPRESS":
                    response = provider.create_aliexpress_draft(draft_payload, key)
                    auto_publish = False
                else:
                    response = provider.create_draft(draft_payload, key)
                draft.external_id, draft.request_id = response["external_id"], response.get("request_id")
                response_payload = {"create": response.get("response", {}), "mode": "draft_only"}
                if auto_publish:
                    claim_response = provider.claim_product(store.external_shop_id or "", draft.external_id, store.mode)
                    cid = _parameter(parameters, "妙手类目ID", "妙手类目ID cid", "类目ID", default="29542")
                    claim_verified = provider.wait_for_claim(store.external_shop_id or "", draft.external_id, cid, store.mode)
                    provider.ensure_shop_item_number(store.external_shop_id or "", draft.external_id, cid, product.spu_code, store.mode, {sku.sku_code: int(sku.stock if sku.stock is not None else product.stock or 0) for sku in product.skus})
                    publish_response = provider.publish_product(store.external_shop_id or "", draft.external_id, store.mode)
                    verification = provider.wait_for_publish(draft.external_id, store.mode)
                    draft.status = "PUBLISHED" if verification.get("verified") else "PUBLISHING"
                    response_payload.update({
                        "mode": "auto_publish",
                        "claim": claim_response.get("response", {}),
                        "claim_verification": claim_verified.get("response", {}),
                        "publish": publish_response.get("response", {}),
                        "publish_verification": _publish_verification_evidence(verification),
                    })
                else:
                    draft.status = "DRAFT_CREATED"
                draft.response_json = json.dumps(response_payload, ensure_ascii=False)[:20000]
                listing.status, listing.external_product_id, listing.response_json = draft.status, draft.external_id, draft.response_json
            except MiaoshouError as exc:
                draft.status, draft.error_message = "FAILED", str(exc)
                listing.status, listing.error_message = "FAILED", str(exc)
        else:
            package, filename = listing_package(db, product, store)
            package_key = f"publish/{product.spu_code}/{store.id}/{key[:16]}-{filename}"
            configured_storage().put(package_key, package, "application/zip")
            draft.status, draft.package_key = "PACKAGE_READY", package_key
            listing.status, listing.response_json = "PACKAGE_READY", json.dumps({"package_key": package_key})
        results.append({"store_id": store.id, "status": draft.status, "draft_id": draft.id, "external_id": draft.external_id, "package_available": bool(draft.package_key), "error": draft.error_message, "idempotent": False, "verification_required": draft.status == "PUBLISHING"})
    db.commit()
    return results
