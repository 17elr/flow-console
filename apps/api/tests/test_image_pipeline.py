from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image, ImageDraw
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.image_pipeline import input_fingerprint, process_job, readiness
from app.main import create_image_batch
from app.models import Asset, AssetVersion, ImageBatch, ImageJob, ProductMaster, SkuAsset, SkuComponent, SkuVariant
from app.schemas import ImageBatchCreate
from app.storage import LocalStorage, validate_image


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def add_product(db: Session, code: str, sku_count: int = 1) -> ProductMaster:
    product = ProductMaster(
        spu_code=code,
        title=f"测试饰品 {code}",
        material="925 silver",
        color="silver",
        dimensions="45 cm",
        source_image_url="https://example.com/spu.png",
        image_rights="AUTHORIZED",
        status="WAITING_GENERATION",
    )
    db.add(product)
    db.flush()
    for index in range(sku_count):
        db.add(
            SkuVariant(
                product_id=product.id,
                sku_code=f"{code}-SKU-{index + 1}",
                color="silver" if index % 2 == 0 else "gold",
                size="45 cm",
                source_image_url=f"https://example.com/{code}-{index}.png",
                is_sellable=True,
                status="WAITING_GENERATION",
            )
        )
    db.commit()
    return product


def test_bundle_is_ready_with_complete_components_and_not_with_missing_component(db: Session) -> None:
    product = add_product(db, "SPU-BUNDLE", 0)
    bundle = SkuVariant(product_id=product.id, sku_code="SKU-BUNDLE", color="mixed", is_sellable=True)
    bundle.components = [
        SkuComponent(component_code="A", component_name="necklace", quantity=2, source_image_url="https://example.com/a.png"),
        SkuComponent(component_code="B", component_name="earring", quantity=1, source_image_url="https://example.com/b.png"),
    ]
    db.add(bundle)
    db.commit()
    db.refresh(product)
    assert readiness(product)["status"] == "READY"

    bundle.components[1].source_image_url = None
    db.commit()
    result = readiness(product)
    assert result["status"] == "BLOCKED"
    assert any(item["target"] == "SKU-BUNDLE" for item in result["missing"])


def test_ten_products_and_thirty_five_skus_create_exact_job_contract(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import main

    monkeypatch.setattr(main.dispatcher, "dispatch", lambda _job_ids: None)
    products = [add_product(db, f"SPU-{index:02d}", 4 if index < 5 else 3) for index in range(10)]
    batches = [create_image_batch(product.id, ImageBatchCreate(force=False), db) for product in products]

    assert sum(batch.total_jobs for batch in batches) == 75
    assert db.scalar(select(func.count(ImageJob.id)).where(ImageJob.job_type != "SKU_WHITE")) == 40
    assert db.scalar(select(func.count(ImageJob.id)).where(ImageJob.job_type == "SKU_WHITE")) == 35
    repeated = create_image_batch(products[0].id, ImageBatchCreate(force=False), db)
    assert repeated.id == batches[0].id
    forced = create_image_batch(products[0].id, ImageBatchCreate(force=True), db)
    assert forced.id != batches[0].id and forced.version == 2


def test_fingerprint_changes_with_component_quantity(db: Session) -> None:
    product = add_product(db, "SPU-FINGERPRINT", 0)
    sku = SkuVariant(product_id=product.id, sku_code="SET-1", color="silver", is_sellable=True)
    sku.components = [SkuComponent(component_code="A", component_name="item A", quantity=1, source_image_url="https://example.com/a.png")]
    db.add(sku)
    db.commit()
    before = input_fingerprint(product)
    sku.components[0].quantity = 2
    db.commit()
    assert input_fingerprint(product) != before


def transparent_fixture() -> bytes:
    image = Image.new("RGBA", (1200, 1200), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((170, 300, 1030, 900), fill=(184, 42, 54, 255), outline=(115, 16, 25, 255), width=16)
    stream = BytesIO()
    image.save(stream, "PNG")
    return stream.getvalue()


def test_local_pipeline_outputs_four_spu_and_bound_sku_asset(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import image_pipeline

    database_path = tmp_path / "pipeline.db"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    local_sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(image_pipeline, "SessionLocal", local_sessions)
    monkeypatch.setenv("LOCAL_ASSET_ROOT", str(tmp_path / "assets"))
    monkeypatch.setenv("OCR_ENABLED", "false")
    content = transparent_fixture()
    meta = validate_image(content)
    storage = LocalStorage()
    storage.put("sources/fixture.png", content, "image/png")

    with local_sessions() as db:
        product = ProductMaster(spu_code="SPU-LOCAL", title="Local fixture", material="metal", color="red", dimensions="45 cm", source_image_url="https://example.com/source.png", image_rights="AUTHORIZED")
        db.add(product)
        db.flush()
        sku = SkuVariant(product_id=product.id, sku_code="SKU-LOCAL-RED", color="red", size="45 cm", source_image_url="https://example.com/sku.png", is_sellable=True)
        db.add(sku)
        db.flush()
        common = dict(url="storage://sources/fixture.png", source_url=None, storage_key="sources/fixture.png", sha256=meta["sha256"], mime_type="image/png", width=1200, height=1200, byte_size=len(content), mirror_status="MIRRORED", rights_status="AUTHORIZED")
        db.add(Asset(product_id=product.id, role="SPU_MAIN_SOURCE", asset_type="SOURCE", **common))
        db.add(Asset(product_id=product.id, sku_id=sku.id, role="SKU_SOURCE", asset_type="SOURCE", **common))
        batch = ImageBatch(product_id=product.id, input_fingerprint="a" * 64, version=1, total_jobs=5)
        db.add(batch)
        db.flush()
        jobs = [ImageJob(batch_id=batch.id, product_id=product.id, job_type=role) for role in ("SPU_WHITE_MAIN", "SPU_DETAIL_1", "SPU_DETAIL_2", "SPU_SIZE_INFO")]
        jobs.append(ImageJob(batch_id=batch.id, product_id=product.id, sku_id=sku.id, job_type="SKU_WHITE"))
        db.add_all(jobs)
        db.commit()
        job_ids = [job.id for job in jobs]
        batch_id = batch.id

    for job_id in job_ids:
        process_job(job_id)

    with local_sessions() as db:
        batch = db.get(ImageBatch, batch_id)
        assert (batch.status, batch.completed_jobs, batch.total_jobs) == ("COMPLETED", 5, 5)
        versions = db.scalars(select(AssetVersion).where(AssetVersion.batch_id == batch_id)).all()
        assert len(versions) == 5
        assert {(item.width, item.height, item.mime_type) for item in versions} == {(1024, 1024, "image/png")}
        assert db.scalar(select(func.count(SkuAsset.id)).where(SkuAsset.sku_code == "SKU-LOCAL-RED")) == 1
        for item in versions:
            output = Image.open(BytesIO(storage.get(item.storage_key))).convert("RGB")
            assert output.size == (1024, 1024)
            if item.role not in {"SPU_DETAIL_1", "SPU_DETAIL_2"}:
                assert output.getpixel((0, 0)) == (255, 255, 255)
