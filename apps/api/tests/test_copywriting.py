from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.copywriting import build_copy, clean_generated_description, update_copy, upsert_generated_copy
from app.db import Base, get_db
from app.main import app
from app.models import ProductMaster, SkuVariant


def product_fixture(session: Session) -> ProductMaster:
    product = ProductMaster(
        spu_code="COPY-001",
        title="简约圆环耳扣",
        category="耳扣",
        material="不锈钢",
        dimensions="12mm",
        price=5.4,
        stock=20,
    )
    session.add(product)
    session.flush()
    session.add_all([
        SkuVariant(product_id=product.id, sku_code="COPY-001-S", color="银色", size="12mm", quantity=1, stock=10, is_sellable=True),
        SkuVariant(product_id=product.id, sku_code="COPY-001-G2", color="金色", size="12mm", quantity=2, stock=10, is_sellable=True),
    ])
    session.commit()
    session.refresh(product)
    return product


def test_platform_copy_uses_only_recorded_facts() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        product = product_fixture(session)
        result = build_copy(product, "ALIEXPRESS")
        assert result["title"] == "Stainless Steel Silver Gold Hoop Earrings 12mm 2-Piece Set"
        assert result["sku_names"]
        assert result["description"] == ""
        assert "hypoallergenic" not in str(result).lower()
        assert result["issues"] == []


def test_old_generated_description_is_removed_but_manual_copy_is_kept() -> None:
    old = "This jewelry is offered in the SKU options listed on this page. Recorded dimensions: 12 x 12 x 12. Package contents, color, size and quantity follow the selected SKU."
    assert clean_generated_description(old) == ""
    assert clean_generated_description("A manually written description.") == "A manually written description."


def test_copy_requires_clean_content_before_review() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        product = product_fixture(session)
        record = upsert_generated_copy(session, product, "TEMU")
        session.flush()
        update_copy(record, {
            "title": "Certified Hoop Earrings",
            "bullet_points": ["Hypoallergenic jewelry."],
            "description": "Official product.",
            "sku_names": {},
            "confirmed_review": True,
        })
        assert record.status == "NEEDS_ATTENTION"
        assert record.reviewed_at is None
        assert "UNSUPPORTED_CLAIM" in record.issues_json


def test_generate_copy_api_returns_both_platforms() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        product = product_fixture(session)
        product_id = product.id

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).post(f"/api/products/{product_id}/listing-copies")
        assert response.status_code == 200, response.text
        copies = response.json()["listing_copies"]
        assert {item["platform"] for item in copies} == {"TEMU", "ALIEXPRESS"}
    finally:
        app.dependency_overrides.clear()
