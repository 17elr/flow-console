from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from hashlib import sha256
from datetime import datetime, timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from PIL import Image
import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .image_pipeline import OUTPUT_ROLES
from .miaoshou import MiaoshouError, configured_miaoshou, normalize_sku_classification
from .models import AssetVersion, MiaoshouDraft, ProductMaster, SkuAsset, Store, StoreAutomationConfig, StoreListing, ProductPackagingSelection, PackagingPreset
from .scene_pipeline import SCENE_ROLES
from .storage import configured_storage

PUBLISHING_PAYLOAD_VERSION = "temu-attrs-v14-public-image-base"


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
    product_sheet.append([product.spu_code, store.platform, store.name, product.title, product.category, round((product.price or 0) * multiplier, 2), product.currency, product.stock, product.dimensions, "\n".join(bullets), copy.description])
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
    """Build the AliExpress-specific draft workbook.

    AliExpress uses its own category/custom-attribute and SKU columns; keeping
    these sheets separate prevents TEMU-only fields from being imported.
    """
    copy = next((item for item in product.listing_copies if item.platform == "ALIEXPRESS"), None)
    if not copy:
        raise ValueError("Missing AliExpress listing copy")
    parameters = json.loads(product.import_parameters_json or "{}")
    bullets = json.loads(copy.bullet_points_json or "[]")
    sku_names = json.loads(copy.sku_names_json or "{}")
    config = db.scalar(select(StoreAutomationConfig).where(StoreAutomationConfig.store_id == store.id))
    multiplier = config.price_multiplier if config else 1.0
    workbook = Workbook()
    basic = workbook.active
    basic.title = "商品参数"
    basic.append(["产品编号", "店铺名称", "商品名称", "商品类目", "售价", "币种", "库存", "最小计量单位", "销售方式", "产品描述", "要点说明"])
    basic.append([product.spu_code, store.name, product.title, product.category, round((product.price or 0) * multiplier, 2), product.currency, product.stock, parameters.get("最小计量单位", "件/个"), parameters.get("销售方式", "按件出售"), copy.description, "\n".join(bullets)])
    _style_sheet(basic, [18, 28, 52, 32, 12, 10, 10, 16, 16, 80, 60])
    basic.row_dimensions[2].height = 110
    attrs = workbook.create_sheet("类目与属性")
    attrs.append(["属性名称", "当前值", "是否必填", "妙手可选值", "数据来源"])
    # Fixed AliExpress necklace category fields transcribed from the Miaoshou
    # editor. Values remain data-driven; the catalog is guidance for import.
    catalogs = {
        "Metals Type": ("金属类型", True, "SILVER,铜,不锈钢,钛,钨,沙金,锡合金,锡金,锌合金,铅锌合金,铜合金,无,铁合金,铝,铝合金,藏銀"),
        "Necklace Type": ("项链类型", True, "链式项链,短项链/领箱,多层项链,吊坠项链,项圈,能量项链,毛衣链"),
        "Material": ("材质", True, "不锈钢,SILVER,Velvet,锆石,玉,金刚石,钛钢,亚克力板,骨质,陶瓷,CLAY,人造珊瑚,CORAL,水晶,玻璃,HORN,LUcite,珍珠,塑料,树脂,莱茵石,半宝石,贝壳,硅胶,石头,木头,绸纱,COTTON,羽毛,蕾丝,皮质,ribbon,立方氧化锆,橄榄核,金刚菩提,菩提子,金属"),
        "Clasp Type": ("扣合类型", True, "磁吸,扣,其他,无扣,龙虾爪扣,盒子,棒状,鹦鹉,钩子,弹簧圈"),
        "Setting Material": ("镶嵌材质", True, "水钻,锆石,贝母,珍珠,人造宝石/半宝石,天然石,无"),
        "Style": ("风格", False, "Y2K,经典,TRENDY,运动/休闲,BOHEMIA,朋克风,OL风格,甜美浪漫,复古风,嘻哈摇滚,Hyperbole,民族风,宗教,新哥特,维京,自然,极简主义,冥想保健,可爱"),
        "Chain Type": ("链类型", False, "蛇链,O字链,新加坡链扭曲,索链,爆米花链,菲加罗链,绳链,水波链,无,珠串手链,STRAND,圆珠链,马鞍链,竹节链,刀片链,箱链"),
        "Shape\\pattern": ("形状\\图案", False, "动物,花朵,PLANT,面部,心型,镂空,Star,月亮,水滴,圆形,海洋,锁,蝴蝶,KeY,铆钉,十字架,ANCHOR,昆虫,数字,球形,FAIRY,羽毛,几何,蝴蝶结,钩子,方块,字母,皇冠,Peace"),
        "Compatibility": ("兼容性", False, "Ios,全兼容,Android"),
        "Occasion": ("场合", False, "宴会,纪念日,婚庆,生日,ENGAGEMENT"),
        "Certification": ("认证", False, "REACH检测报告"),
    }
    normalized = {str(k).replace("（", "(").replace("）", ")").strip(): v for k, v in parameters.items()}
    for english, (cn, required, allowed) in catalogs.items():
        value = normalized.get(english) or normalized.get(cn) or normalized.get(english.replace("\\", ""), "")
        attrs.append([cn, value, "是" if required else "否", allowed, "妙手速卖通类目"])
    for key, value in parameters.items():
        if str(key) not in {item[0] for item in catalogs.values()} and value not in (None, ""):
            attrs.append([str(key), value, "否", "", "商品导入数据"])
    _style_sheet(attrs, [28, 34, 12, 110, 30])
    attrs.freeze_panes = "A2"
    skus = workbook.create_sheet("销售属性_SKU")
    skus.append(["平台SKU", "商品SPU", "金属颜色", "自定义名称", "售价", "库存", "重量(kg)", "长度(cm)", "宽度(cm)", "高度(cm)", "特殊商品类型", "物流属性", "是否申请停售", "图片文件"])
    for item in product.skus:
        skus.append([item.sku_code, product.spu_code, item.color or "", sku_names.get(str(item.id), item.name or item.sku_code), round(((item.price or product.price) or 0) * multiplier, 2), item.stock, round((product.weight_g or 10) / 1000, 3), 10, 10, 2, parameters.get("特殊商品类型", "普货"), parameters.get("物流属性", "普货"), "否", f"产品图片/{product.spu_code}/SKU图/{item.sku_code}.png"])
    _style_sheet(skus, [24, 18, 18, 32, 12, 10, 14, 14, 14, 14, 16, 20, 14, 42])
    images = workbook.create_sheet("产品图片")
    images.append(["图片用途", "图片文件", "是否必需"])
    for role in OUTPUT_ROLES:
        images.append([role, f"产品图片/{product.spu_code}/产品主图/{role}.png", "是"])
    packaging = _packaging_preset(db, product)
    if packaging:
        extension = packaging.mime_type.split("/")[-1].replace("jpeg", "jpg")
        images.append(["包装图", f"产品图片/{product.spu_code}/尺寸图表/包装图{packaging.slot}.{extension}", "否"])
    _style_sheet(images, [28, 52, 12])
    instructions = workbook.create_sheet("使用说明")
    instructions.append(["步骤", "说明"])
    instructions.append([1, "使用速卖通商品草稿/导入功能导入此模板。"])
    instructions.append([2, "根据类目与属性工作表核对妙手中文类目属性。"])
    instructions.append([3, "保存草稿前核对每个 SKU 的价格、库存、尺寸和图片。"])
    instructions.append([4, "此模板只创建草稿，不执行自动上架。"])
    _style_sheet(instructions, [10, 100])
    # Keep the downloadable/importable workbook aligned with the standalone
    # template: basic information and category attributes are one visible page.
    basic.title = "商品参数与属性"
    attr_start = basic.max_row + 3
    for row in attrs.iter_rows():
        for cell in row:
            target = basic.cell(attr_start + cell.row - 1, cell.column, cell.value)
            if cell.has_style:
                target._style = cell._style
    if attrs.title in workbook.sheetnames:
        del workbook[attrs.title]
    stream = io.BytesIO(); workbook.save(stream); return stream.getvalue()


def listing_package(db: Session, product: ProductMaster, store: Store) -> tuple[bytes, str]:
    stream = io.BytesIO()
    sku_assets = _latest_sku_assets(db, product)
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        workbook = build_aliexpress_workbook(db, product, store) if platform_key(store) == "ALIEXPRESS" else build_listing_workbook(db, product, store)
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

        key = f"{publishing_key(db, product, store, state, auto_publish=False)}:manual-import"
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
                package_length = _parameter(parameters, "包装最长边(cm)", "包装最长边（cm）", default="")
                package_width = _parameter(parameters, "包装次长边(cm)", "包装次长边（cm）", default="")
                package_height = _parameter(parameters, "包装最短边(cm)", "包装最短边（cm）", default="")
                package_weight = _parameter(parameters, "包装重量(g)", "包装重量（g）", default="")
                net_weight = _parameter(parameters, "商品净重(g)", "商品净重（g）", default="")
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
                excel_title = str(_parameter(parameters, "商品名称", default=product.title) or product.title).strip()
                draft_payload = {"spu": product.spu_code, "title": excel_title, "description": copy.description, "price": round((product.price or 0) * multiplier, 2), "stock": product.stock, "store": store.name, "external_shop_id": store.external_shop_id, "category": product.category, "category_parameters": parameters, "packaging_img_urls": packaging_urls, "img_urls": image_urls, "description_img_urls": image_urls, "sku_map": sku_map, "dimensions": {"length": package_length, "width": package_width, "height": package_height}, "weight": package_weight}
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
