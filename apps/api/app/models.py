from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="COMPLETED")
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    issue_rows: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    products: Mapped[List["ProductMaster"]] = relationship(back_populates="import_batch")
    issues: Mapped[List["ImportIssue"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class ProductMaster(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    spu_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(120), default="女士饰品")
    material: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    dimensions: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    weight_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    stock: Mapped[int] = mapped_column(Integer, default=0)
    source_image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_rights: Mapped[str] = mapped_column(String(30), default="UNKNOWN")
    status: Mapped[str] = mapped_column(String(30), default="WAITING_DATA", index=True)
    image_readiness: Mapped[str] = mapped_column(String(30), default="NOT_CHECKED", index=True)
    scene_readiness: Mapped[str] = mapped_column(String(30), default="NOT_CONFIGURED", index=True)
    import_parameters_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    imported_batch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("import_batches.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    import_batch: Mapped[Optional[ImportBatch]] = relationship(back_populates="products")
    skus: Mapped[List["SkuVariant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    assets: Mapped[List["Asset"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    listings: Mapped[List["StoreListing"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    image_batches: Mapped[List["ImageBatch"]] = relationship(back_populates="product")
    scene_profile: Mapped[Optional["SceneProfile"]] = relationship(back_populates="product", uselist=False, cascade="all, delete-orphan")
    listing_copies: Mapped[List["ListingCopy"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    review_decisions: Mapped[List["ReviewDecision"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class SkuVariant(Base):
    __tablename__ = "sku_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    size: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    material: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    source_image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_sellable: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(30), default="WAITING_DATA")

    product: Mapped[ProductMaster] = relationship(back_populates="skus")
    components: Mapped[List["SkuComponent"]] = relationship(
        back_populates="sku", cascade="all, delete-orphan"
    )
    assets: Mapped[List["Asset"]] = relationship(
        back_populates="sku", cascade="all, delete-orphan"
    )


class SkuComponent(Base):
    __tablename__ = "sku_components"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("sku_variants.id"), index=True)
    component_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    component_name: Mapped[str] = mapped_column(String(255))
    color: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    source_image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    sku: Mapped[SkuVariant] = relationship(back_populates="components")


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    sku_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sku_variants.id"), nullable=True, index=True
    )
    component_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sku_components.id"), nullable=True, index=True
    )
    asset_type: Mapped[str] = mapped_column(String(30), default="SOURCE")
    role: Mapped[str] = mapped_column(String(40), default="SPU_MAIN_SOURCE", index=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    storage_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    byte_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mirror_status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    rights_status: Mapped[str] = mapped_column(String(30), default="UNKNOWN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    product: Mapped[ProductMaster] = relationship(back_populates="assets")
    sku: Mapped[Optional[SkuVariant]] = relationship(back_populates="assets")


class ImageBatch(Base):
    __tablename__ = "image_batches"
    __table_args__ = (UniqueConstraint("product_id", "input_fingerprint", "version", name="uq_image_batch_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    pipeline_version: Mapped[str] = mapped_column(String(30), default="deterministic-v1")
    pipeline_kind: Mapped[str] = mapped_column(String(30), default="DETERMINISTIC", index=True)
    provider: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    reference_sku_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sku_variants.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    total_jobs: Mapped[int] = mapped_column(Integer, default=0)
    completed_jobs: Mapped[int] = mapped_column(Integer, default=0)
    failed_jobs: Mapped[int] = mapped_column(Integer, default=0)
    waiting_jobs: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    product: Mapped[ProductMaster] = relationship(back_populates="image_batches")
    jobs: Mapped[List["ImageJob"]] = relationship(back_populates="batch", cascade="all, delete-orphan")
    asset_versions: Mapped[List["AssetVersion"]] = relationship(back_populates="batch")


class ImageJob(Base):
    __tablename__ = "image_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("image_batches.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    sku_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sku_variants.id"), nullable=True, index=True)
    job_type: Mapped[str] = mapped_column(String(40), index=True)
    stage: Mapped[str] = mapped_column(String(30), default="QUEUED")
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    error_code: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_asset_id: Mapped[Optional[int]] = mapped_column(ForeignKey("asset_versions.id"), nullable=True)
    qc_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manifest_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    batch: Mapped[ImageBatch] = relationship(back_populates="jobs")
    result_asset: Mapped[Optional["AssetVersion"]] = relationship(foreign_keys=[result_asset_id])


class AssetVersion(Base):
    __tablename__ = "asset_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("image_batches.id"), index=True)
    role: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    mime_type: Mapped[str] = mapped_column(String(80), default="image/png")
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    byte_size: Mapped[int] = mapped_column(Integer)
    pipeline_version: Mapped[str] = mapped_column(String(30))
    source_asset_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reference_asset_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider_request_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    provider_metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qc_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    batch: Mapped[ImageBatch] = relationship(back_populates="asset_versions")


class SkuAsset(Base):
    __tablename__ = "sku_assets"
    __table_args__ = (UniqueConstraint("sku_id", "asset_version_id", name="uq_sku_asset_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("sku_variants.id"), index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("image_batches.id"), index=True)
    asset_version_id: Mapped[int] = mapped_column(ForeignKey("asset_versions.id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(100), index=True)
    component_manifest: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PackagingPreset(Base):
    __tablename__ = "packaging_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slot: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    mime_type: Mapped[str] = mapped_column(String(80))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    byte_size: Mapped[int] = mapped_column(Integer)
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ProductPackagingSelection(Base):
    __tablename__ = "product_packaging_selections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), unique=True, index=True)
    preset_id: Mapped[int] = mapped_column(ForeignKey("packaging_presets.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SceneProfile(Base):
    __tablename__ = "scene_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), unique=True, index=True)
    reference_sku_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sku_variants.id"), nullable=True)
    model_age: Mapped[str] = mapped_column(String(40), default="adult")
    clothing_color: Mapped[str] = mapped_column(String(80), default="light gray or white")
    framing: Mapped[str] = mapped_column(String(120), default="category-appropriate close crop")
    model_background: Mapped[str] = mapped_column(String(120), default="clean light neutral studio")
    lifestyle_scene: Mapped[str] = mapped_column(String(120), default="bright daytime interior")
    surface_material: Mapped[str] = mapped_column(String(120), default="light neutral tabletop")
    light_direction: Mapped[str] = mapped_column(String(80), default="soft window light")
    depth_of_field: Mapped[str] = mapped_column(String(40), default="subtle")
    model_prompt_override: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lifestyle_prompt_override: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    template_version: Mapped[str] = mapped_column(String(40), default="neutral-commerce-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    product: Mapped[ProductMaster] = relationship(back_populates="scene_profile")


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    platform: Mapped[str] = mapped_column(String(30))
    mode: Mapped[str] = mapped_column(String(30))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    external_shop_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True, index=True)

    listings: Mapped[List["StoreListing"]] = relationship(
        back_populates="store", cascade="all, delete-orphan"
    )


class StoreListing(Base):
    __tablename__ = "store_listings"
    __table_args__ = (UniqueConstraint("product_id", "store_id", name="uq_product_store"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    listing_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="NOT_READY")
    external_product_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    response_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    product: Mapped[ProductMaster] = relationship(back_populates="listings")
    store: Mapped[Store] = relationship(back_populates="listings")


class MiaoshouDraft(Base):
    __tablename__ = "miaoshou_drafts"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_miaoshou_draft_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), index=True)
    channel: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    external_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    package_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    response_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ListingCopy(Base):
    __tablename__ = "listing_copies"
    __table_args__ = (UniqueConstraint("product_id", "platform", name="uq_product_listing_copy_platform"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    platform: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(500))
    bullet_points_json: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    sku_names_json: Mapped[str] = mapped_column(Text)
    input_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    generator: Mapped[str] = mapped_column(String(40), default="deterministic-template")
    rules_version: Mapped[str] = mapped_column(String(30), default="platform-rules-v1")
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    issues_json: Mapped[str] = mapped_column(Text, default="[]")
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    product: Mapped[ProductMaster] = relationship(back_populates="listing_copies")


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    __table_args__ = (UniqueConstraint("product_id", "subject_type", "subject_id", name="uq_review_subject"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    subject_type: Mapped[str] = mapped_column(String(30), index=True)
    subject_id: Mapped[int] = mapped_column(Integer, default=0)
    subject_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    decision: Mapped[str] = mapped_column(String(20), index=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewer: Mapped[str] = mapped_column(String(80), default="operator")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    product: Mapped[ProductMaster] = relationship(back_populates="review_decisions")


class StoreAutomationConfig(Base):
    __tablename__ = "store_automation_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), unique=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_publish: Mapped[bool] = mapped_column(Boolean, default=False)
    price_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    visual_profile: Mapped[str] = mapped_column(String(80), default="neutral-commerce")
    max_daily: Mapped[int] = mapped_column(Integer, default=20)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AutomationSchedule(Base):
    __tablename__ = "automation_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    run_time: Mapped[str] = mapped_column(String(5), default="02:00")
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Shanghai")
    store_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    max_products: Mapped[int] = mapped_column(Integer, default=20)
    last_run_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AutomationRun(Base):
    __tablename__ = "automation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    schedule_id: Mapped[Optional[int]] = mapped_column(ForeignKey("automation_schedules.id"), nullable=True, index=True)
    trigger: Mapped[str] = mapped_column(String(30), default="MANUAL")
    status: Mapped[str] = mapped_column(String(30), default="RUNNING", index=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    succeeded: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    details_json: Mapped[str] = mapped_column(Text, default="[]")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ImportIssue(Base):
    __tablename__ = "import_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), index=True)
    sheet: Mapped[str] = mapped_column(String(80))
    row_number: Mapped[int] = mapped_column(Integer)
    identifier: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    field: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="ERROR")
    code: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)

    batch: Mapped[ImportBatch] = relationship(back_populates="issues")
