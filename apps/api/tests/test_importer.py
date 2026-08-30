from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import Base
from app.importer import import_workbook, template_workbook
from app.main import recalculate_product_status
from app.models import Asset, ProductMaster, SkuComponent, SkuVariant, Store, StoreListing


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def workbook_bytes(workbook: Workbook) -> bytes:
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def minimal_workbook(*, chinese_headers: bool = False, sku_image: str | None = "https://example.com/sku.png") -> Workbook:
    wb = Workbook()
    products = wb.active
    products.title = "商品" if chinese_headers else "Products"
    products.append(
        ["SPU编码", "商品标题", "类目", "材质", "颜色", "商品尺寸", "售价", "库存", "原图", "图片授权"]
        if chinese_headers
        else ["spu_code", "title", "category", "material", "color", "dimensions", "price", "stock", "source_image_url", "image_rights"]
    )
    products.append(["SPU-TEST-001", "测试项链", "女士饰品/项链", "925银", "银色", "45cm", 9.9, 20, "https://example.com/product.png", "AUTHORIZED"])

    skus = wb.create_sheet("规格" if chinese_headers else "SKUs")
    skus.append(
        ["SPU编码", "SKU编码", "SKU名称", "颜色", "尺寸", "材质", "数量", "售价", "库存", "原图", "是否可售"]
        if chinese_headers
        else ["spu_code", "sku_code", "title", "color", "size", "material", "quantity", "price", "stock", "source_image_url", "is_sellable"]
    )
    skus.append(["SPU-TEST-001", "SKU-TEST-001", "银色 / 45cm", "银色", "45cm", "925银", 1, 9.9, 20, sku_image, True])
    return wb


def test_valid_template_round_trip_has_no_issues_and_complete_mapping(db: Session) -> None:
    batch = import_workbook(db, workbook_bytes(template_workbook()), "template.xlsx")

    assert batch.status == "COMPLETED"
    assert batch.issue_rows == 0
    assert db.scalar(select(func.count(ProductMaster.id))) == 1
    assert db.scalar(select(func.count(SkuVariant.id))) == 2
    assert db.scalar(select(func.count(SkuComponent.id))) == 2
    assert db.scalar(select(func.count(StoreListing.id))) == 1
    assert db.scalar(select(func.count(Asset.id))) == 3

    bundle = db.scalar(select(SkuVariant).where(SkuVariant.sku_code == "SKU-DEMO-SET"))
    assert bundle is not None
    assert [(item.component_code, item.quantity) for item in bundle.components] == [
        ("SKU-DEMO-001-SILVER", 1),
        ("SKU-DEMO-EARRING", 1),
    ]


def test_chinese_aliases_import_product_and_sku_images(db: Session) -> None:
    batch = import_workbook(db, workbook_bytes(minimal_workbook(chinese_headers=True)), "中文别名.xlsx")

    assert batch.status == "COMPLETED"
    product = db.scalar(select(ProductMaster).where(ProductMaster.spu_code == "SPU-TEST-001"))
    sku = db.scalar(select(SkuVariant).where(SkuVariant.sku_code == "SKU-TEST-001"))
    assert product is not None and product.source_image_url == "https://example.com/product.png"
    assert product.image_rights == "AUTHORIZED"
    assert product.status == "WAITING_GENERATION"
    assert sku is not None and sku.source_image_url == "https://example.com/sku.png"


def test_missing_sellable_sku_image_is_blocked(db: Session) -> None:
    batch = import_workbook(db, workbook_bytes(minimal_workbook(sku_image=None)), "missing-sku-image.xlsx")

    assert batch.status == "COMPLETED_WITH_ISSUES"
    assert [issue.code for issue in batch.issues] == ["MISSING_SKU_IMAGE"]
    product = db.scalar(select(ProductMaster).where(ProductMaster.spu_code == "SPU-TEST-001"))
    sku = db.scalar(select(SkuVariant).where(SkuVariant.sku_code == "SKU-TEST-001"))
    assert product is not None and product.status == "WAITING_DATA"
    assert sku is not None and sku.status == "WAITING_DATA"


def test_reimport_updates_without_duplicate_products_skus_or_listings(db: Session) -> None:
    content = workbook_bytes(template_workbook())
    import_workbook(db, content, "first.xlsx")
    import_workbook(db, content, "second.xlsx")

    assert db.scalar(select(func.count(ProductMaster.id))) == 1
    assert db.scalar(select(func.count(SkuVariant.id))) == 2
    assert db.scalar(select(func.count(SkuComponent.id))) == 2
    assert db.scalar(select(func.count(Store.id))) == 1
    assert db.scalar(select(func.count(StoreListing.id))) == 1


def test_store_mapping_preserves_platform_mode_and_price(db: Session) -> None:
    import_workbook(db, workbook_bytes(template_workbook()), "stores.xlsx")

    store = db.scalar(select(Store))
    listing = db.scalar(select(StoreListing))
    assert store is not None
    assert (store.platform, store.mode, store.currency) == ("TEMU", "全托管", "USD")
    assert listing is not None and listing.price == 16.8


def test_product_status_recalculation_blocks_and_recovers() -> None:
    product = ProductMaster(
        spu_code="SPU-STATUS",
        title="状态测试",
        material="925银",
        source_image_url="https://example.com/product.png",
        image_rights="AUTHORIZED",
    )
    sku = SkuVariant(
        sku_code="SKU-STATUS",
        color="银色",
        source_image_url=None,
        is_sellable=True,
    )
    product.skus.append(sku)

    recalculate_product_status(product)
    assert product.status == "WAITING_DATA"

    sku.source_image_url = "https://example.com/sku.png"
    recalculate_product_status(product)
    assert product.status == "WAITING_GENERATION"

    product.image_rights = "UNKNOWN"
    recalculate_product_status(product)
    assert product.status == "WAITING_DATA"
