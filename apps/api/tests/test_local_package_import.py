from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.importer import template_workbook
from app.main import app
from app.models import Asset, ProductMaster, SkuVariant


class MemoryStorage:
    def __init__(self) -> None:
        self.items: dict[str, bytes] = {}

    def put(self, key: str, content: bytes, _content_type: str) -> None:
        self.items[key] = content


def test_folder_package_import_binds_spu_and_sku_images(monkeypatch) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    storage = MemoryStorage()
    monkeypatch.setattr("app.main.configured_storage", lambda: storage)

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    workbook_stream = BytesIO(); template_workbook().save(workbook_stream)
    image_stream = BytesIO(); Image.new("RGB", (640, 640), "white").save(image_stream, "PNG")
    files = [
        ("files", ("products.xlsx", workbook_stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
        ("files", ("SPU-DEMO-001.png", image_stream.getvalue(), "image/png")),
        ("files", ("SPU-DEMO-001-SILVER.png", image_stream.getvalue(), "image/png")),
    ]
    try:
        response = TestClient(app).post(
            "/api/imports/package",
            files=files,
            data={"relative_paths": ["package/products.xlsx", "package/SPU-DEMO-001.png", "package/SPU-DEMO-001-SILVER.png"]},
        )
        assert response.status_code == 200, response.text
        with Session(engine) as session:
            product = session.scalar(select(ProductMaster).where(ProductMaster.spu_code == "SPU-DEMO-001"))
            roles = set(session.scalars(select(Asset.role).where(Asset.product_id == product.id)).all())
            assert {"SPU_MAIN_SOURCE", "SKU_SOURCE"}.issubset(roles)
            assert product.image_rights == "AUTHORIZED"
    finally:
        app.dependency_overrides.clear()


def test_image_only_folder_updates_existing_product(monkeypatch) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    storage = MemoryStorage(); monkeypatch.setattr("app.main.configured_storage", lambda: storage)
    with Session(engine) as session:
        product = ProductMaster(spu_code="LOCAL-001", title="Local item", category="Jewelry", material="silver", color="silver", dimensions="10mm", image_rights="UNKNOWN")
        session.add(product); session.flush()
        session.add(SkuVariant(product_id=product.id, sku_code="LOCAL-001-SILVER", color="silver", size="10mm", material="silver", quantity=1, stock=10, is_sellable=True))
        session.commit()

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    image_stream = BytesIO(); Image.new("RGB", (640, 640), "white").save(image_stream, "PNG")
    files = [
        ("files", ("LOCAL-001.png", image_stream.getvalue(), "image/png")),
        ("files", ("LOCAL-001-SILVER.png", image_stream.getvalue(), "image/png")),
    ]
    try:
        response = TestClient(app).post("/api/imports/package", files=files, data={"relative_paths": ["LOCAL-001.png", "LOCAL-001-SILVER.png"]})
        assert response.status_code == 200, response.text
        with Session(engine) as session:
            product = session.scalar(select(ProductMaster).where(ProductMaster.spu_code == "LOCAL-001"))
            roles = set(session.scalars(select(Asset.role).where(Asset.product_id == product.id)).all())
            assert roles == {"SPU_MAIN_SOURCE", "SKU_SOURCE"}
            assert product.image_rights == "AUTHORIZED"
            assert session.scalars(select(ProductMaster)).all() == [product]
    finally:
        app.dependency_overrides.clear()
