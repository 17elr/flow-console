from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import AssetVersion, ImageBatch, ListingCopy, ProductMaster
from app.reviews import review_payload, save_image_decision, save_product_decision


def setup_review_product(session: Session) -> tuple[ProductMaster, list[AssetVersion], list[dict]]:
    product = ProductMaster(spu_code="REVIEW-001", title="Review item", category="Necklace", dimensions="45cm")
    session.add(product); session.flush()
    batch = ImageBatch(product_id=product.id, input_fingerprint="a" * 64, pipeline_kind="DETERMINISTIC", version=1, status="COMPLETED", total_jobs=2)
    session.add(batch); session.flush()
    assets = [
        AssetVersion(product_id=product.id, batch_id=batch.id, role="SPU_WHITE_MAIN", version=1, storage_key="review/main.png", sha256="1" * 64, mime_type="image/png", width=1024, height=1024, byte_size=100, pipeline_version="test"),
        AssetVersion(product_id=product.id, batch_id=batch.id, role="SKU_WHITE", version=1, storage_key="review/sku.png", sha256="2" * 64, mime_type="image/png", width=1024, height=1024, byte_size=100, pipeline_version="test"),
    ]
    session.add_all(assets)
    session.add_all([
        ListingCopy(product_id=product.id, platform="TEMU", title="Title", bullet_points_json="[]", description="Description", sku_names_json="{}", input_fingerprint="t" * 64, status="REVIEWED", issues_json="[]"),
        ListingCopy(product_id=product.id, platform="ALIEXPRESS", title="Title", bullet_points_json="[]", description="Description", sku_names_json="{}", input_fingerprint="x" * 64, status="REVIEWED", issues_json="[]"),
    ])
    session.commit(); session.refresh(product)
    outputs = [{"asset": {"id": asset.id, "sha256": asset.sha256}, "review": None} for asset in assets]
    return product, assets, outputs


def test_product_approval_requires_every_current_image() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        product, assets, outputs = setup_review_product(session)
        save_image_decision(session, assets[0], "APPROVED", None); session.commit(); session.refresh(product)
        summary = review_payload(product, outputs, 2)
        assert summary["approved_images"] == 1
        assert summary["can_approve"] is False
        with pytest.raises(ValueError):
            save_product_decision(session, product, summary, "APPROVED", None)


def test_image_change_invalidates_review_and_product_approval() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        product, assets, outputs = setup_review_product(session)
        for asset in assets:
            save_image_decision(session, asset, "APPROVED", "checked")
        session.commit(); session.refresh(product)
        summary = review_payload(product, outputs, 2)
        assert summary["can_approve"] is True
        save_product_decision(session, product, summary, "APPROVED", None); session.commit(); session.refresh(product)
        assert review_payload(product, outputs, 2)["approved"] is True

        outputs[1]["asset"]["sha256"] = "9" * 64
        changed = review_payload(product, outputs, 2)
        assert changed["approved_images"] == 1
        assert changed["approved"] is False


def test_rejected_sku_image_blocks_product() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        product, assets, outputs = setup_review_product(session)
        save_image_decision(session, assets[0], "APPROVED", None)
        save_image_decision(session, assets[1], "REJECTED", "Wrong SKU color")
        session.commit(); session.refresh(product)
        summary = review_payload(product, outputs, 2)
        assert summary["rejected_images"] == 1
        assert summary["status"] == "REJECTED"
        assert summary["can_approve"] is False
