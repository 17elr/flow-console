from __future__ import annotations

import hashlib

import pytest

from app.models import ProductMaster, SceneProfile, SkuComponent, SkuVariant
from app.providers import HensunImageProvider, ProviderConfig
from app.scene_pipeline import build_prompt, choose_sku, scene_fingerprint, scene_readiness
from app.storage import AssetValidationError


def product_with_skus() -> ProductMaster:
    product = ProductMaster(id=1, spu_code="SPU-1", title="Silver necklace", category="necklace", material="silver", color="silver", source_image_url="https://example.com/main.png", image_rights="AUTHORIZED")
    product.assets = []
    product.skus = [
        SkuVariant(id=11, sku_code="SKU-S", color="silver", size="45cm", material="silver", quantity=1, source_image_url="https://example.com/s.png", is_sellable=True, components=[], assets=[]),
        SkuVariant(id=12, sku_code="SKU-G", color="gold", size="45cm", material="steel", quantity=1, source_image_url="https://example.com/g.png", is_sellable=True, components=[], assets=[]),
    ]
    return product


def test_multiple_skus_require_explicit_primary() -> None:
    product = product_with_skus()
    with pytest.raises(AssetValidationError, match="主推 SKU"):
        choose_sku(product, None)
    assert choose_sku(product, 12).sku_code == "SKU-G"


def test_profile_and_prompt_are_part_of_fingerprint() -> None:
    product = product_with_skus(); sku = product.skus[0]
    provider = HensunImageProvider(ProviderConfig("hensun", "https://hensunai.com/v1", "gpt-image-2", "HENSUN_API_KEY"))
    first = SceneProfile(product_id=1, reference_sku_id=sku.id)
    second = SceneProfile(product_id=1, reference_sku_id=sku.id, clothing_color="black")
    assert scene_fingerprint(product, sku, first, provider) != scene_fingerprint(product, sku, second, provider)
    prompt = build_prompt(product, sku, first, "SCENE_MODEL_WEAR")
    assert "One complete single-frame image only" in prompt
    assert "Do not add, remove, replace" in prompt
    assert sku.sku_code in prompt


def test_scene_readiness_requires_primary_sku() -> None:
    product = product_with_skus()
    result = scene_readiness(product, None)
    assert result["status"] == "BLOCKED"
    assert any(item["code"] == "REFERENCE_SKU_REQUIRED" for item in result["missing"])
    profile = SceneProfile(product_id=1, reference_sku_id=11)
    assert scene_readiness(product, profile)["status"] == "READY"
