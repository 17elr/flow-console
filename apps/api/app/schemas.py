from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class StoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    platform: str
    mode: str
    currency: str
    active: bool
    external_shop_id: Optional[str] = None


class ComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    component_code: Optional[str]
    component_name: str
    color: Optional[str]
    quantity: int
    source_image_url: Optional[str]


class SkuOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku_code: str
    name: Optional[str]
    color: Optional[str]
    size: Optional[str]
    material: Optional[str]
    quantity: int
    price: Optional[float]
    stock: int
    source_image_url: Optional[str]
    is_sellable: bool
    status: str
    components: List[ComponentOut] = []


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku_id: Optional[int]
    asset_type: str
    url: str
    rights_status: str
    role: str
    storage_key: Optional[str]
    sha256: Optional[str]
    mime_type: Optional[str]
    width: Optional[int]
    height: Optional[int]
    mirror_status: str


class ListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    store_id: int
    listing_title: Optional[str]
    price: Optional[float]
    status: str
    store: StoreOut


class ProductSummary(BaseModel):
    id: int
    spu_code: str
    title: str
    category: str
    material: Optional[str]
    price: Optional[float]
    currency: str
    stock: int
    source_image_url: Optional[str]
    image_rights: str
    status: str
    image_readiness: str
    scene_readiness: str = "NOT_CONFIGURED"
    sku_count: int
    ready_sku_count: int
    listing_count: int
    blocker_count: int
    warning_count: int
    updated_at: datetime


class ProductDetail(ProductSummary):
    dimensions: Optional[str]
    weight_g: Optional[float]
    cost: Optional[float]
    color: Optional[str]
    skus: List[SkuOut]
    assets: List[AssetOut]
    listings: List[ListingOut]


class IssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sheet: str
    row_number: int
    identifier: Optional[str]
    field: Optional[str]
    severity: str
    code: str
    message: str


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    status: str
    total_rows: int
    valid_rows: int
    issue_rows: int
    created_at: datetime
    issues: List[IssueOut] = []


class OverviewOut(BaseModel):
    products: int
    skus: int
    waiting_data: int
    waiting_generation: int
    ready: int
    issues: int
    stores: int
    latest_batch: Optional[BatchOut]


class ProductPatch(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    material: Optional[str] = None
    color: Optional[str] = None
    dimensions: Optional[str] = None
    weight_g: Optional[float] = None
    cost: Optional[float] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    stock: Optional[int] = None
    source_image_url: Optional[str] = None
    image_rights: Optional[str] = None


class SkuPatch(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    material: Optional[str] = None
    quantity: Optional[int] = None
    price: Optional[float] = None
    stock: Optional[int] = None
    source_image_url: Optional[str] = None
    is_sellable: Optional[bool] = None


class ComponentCreate(BaseModel):
    component_code: Optional[str] = None
    component_name: str
    color: Optional[str] = None
    quantity: int = 1
    source_image_url: Optional[str] = None


class ListingCreate(BaseModel):
    store_id: int
    listing_title: Optional[str] = None
    price: Optional[float] = None


class ReadinessIssue(BaseModel):
    code: str
    message: str
    target: str


class ImageReadinessOut(BaseModel):
    product_id: int
    status: str
    missing: List[ReadinessIssue]
    warnings: List[ReadinessIssue]


class ImageBatchCreate(BaseModel):
    force: bool = False


class AssetVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    version: int
    storage_key: str
    sha256: str
    width: int
    height: int
    byte_size: int
    qc_json: Optional[str]
    created_at: datetime


class ImageJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku_id: Optional[int]
    job_type: str
    stage: str
    status: str
    retry_count: int
    max_retries: int
    error_code: Optional[str]
    error_message: Optional[str]
    qc_json: Optional[str]
    manifest_json: Optional[str]
    result_asset: Optional[AssetVersionOut]


class ImageBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    input_fingerprint: str
    pipeline_version: str
    pipeline_kind: str = "DETERMINISTIC"
    provider: Optional[str] = None
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    reference_sku_id: Optional[int] = None
    version: int
    status: str
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    waiting_jobs: int
    created_at: datetime
    completed_at: Optional[datetime]
    jobs: List[ImageJobOut] = []


class SceneProfilePatch(BaseModel):
    reference_sku_id: Optional[int] = None
    model_age: Optional[str] = None
    clothing_color: Optional[str] = None
    framing: Optional[str] = None
    model_background: Optional[str] = None
    lifestyle_scene: Optional[str] = None
    surface_material: Optional[str] = None
    light_direction: Optional[str] = None
    depth_of_field: Optional[str] = None
    model_prompt_override: Optional[str] = None
    lifestyle_prompt_override: Optional[str] = None


class SceneBatchCreate(SceneProfilePatch):
    force: bool = False


class SceneProfileOut(SceneProfilePatch):
    model_config = ConfigDict(from_attributes=True)
    product_id: int
    template_version: str
    status: str
    missing: List[ReadinessIssue] = []


class ProviderStatusOut(BaseModel):
    provider: str
    model: str
    configured: bool
    network_call: bool
    capabilities: dict = {}
    available: bool = False
    model_visible: bool = False
    model_count: int = 0
    error: Optional[str] = None


class SimpleSkuCreate(BaseModel):
    sku_code: str
    color: str
    size: Optional[str] = None
    quantity: int = 1
    price: Optional[float] = None
    stock: int = 0


class SimpleProductCreate(BaseModel):
    spu_code: str
    title: str
    category: str
    price: float
    stock: int
    dimensions: str
    skus: List[SimpleSkuCreate]


class GenerateAllCreate(BaseModel):
    force: bool = False
    reference_sku_id: Optional[int] = None


class MiaoshouDraftCreate(BaseModel):
    store_ids: List[int]
    confirmed_review: bool = False
    force: bool = False
    auto_publish: bool = False


class AliExpressImportPackageCreate(BaseModel):
    store_ids: List[int]
    confirmed_review: bool = False
    force: bool = False


class PackagingSelectionPatch(BaseModel):
    preset_id: int


class PackagingBulkPatch(BaseModel):
    product_ids: List[int]
    preset_id: int


class FinishedDraftRetryCreate(BaseModel):
    product_ids: List[int]


class ListingCopyUpdate(BaseModel):
    title: str
    bullet_points: List[str]
    description: str
    sku_names: dict[str, str]
    confirmed_review: bool = False


class ReviewDecisionCreate(BaseModel):
    decision: str
    note: Optional[str] = None


class AutomationScheduleCreate(BaseModel):
    name: str
    active: bool = True
    run_time: str = "02:00"
    timezone: str = "Asia/Shanghai"
    store_ids: List[int]
    max_products: int = 20


class AutomationSchedulePatch(BaseModel):
    name: Optional[str] = None
    active: Optional[bool] = None
    run_time: Optional[str] = None
    timezone: Optional[str] = None
    store_ids: Optional[List[int]] = None
    max_products: Optional[int] = None


class StoreAutomationPatch(BaseModel):
    active: bool = True
    auto_publish: bool = False
    price_multiplier: float = 1.0
    visual_profile: str = "neutral-commerce"
    max_daily: int = 20


class AutomationRunCreate(BaseModel):
    store_ids: List[int]
    max_products: int = 20
