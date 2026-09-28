from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from .models import ListingCopy, ProductMaster, utcnow


RULES_VERSION = "platform-rules-v1"
PLATFORM_RULES = {
    "TEMU": {"title_max": 250, "description_max": 5000, "bullets_max": 5},
    "ALIEXPRESS": {"title_max": 128, "description_max": 6000, "bullets_max": 5},
}
BANNED_CLAIMS = {
    "authentic", "genuine", "certified", "hypoallergenic", "nickel-free",
    "nickel free", "lead-free", "lead free", "medical grade", "waterproof",
    "tarnish free", "lifetime warranty", "official",
}

CATEGORY_MAP = {
    "项链": "Necklace", "耳环": "Earrings", "耳扣": "Hoop Earrings",
    "耳钉": "Stud Earrings", "手链": "Bracelet", "戒指": "Ring",
    "吊坠": "Pendant", "女士饰品": "Jewelry", "珠宝首饰": "Jewelry",
}
COLOR_MAP = {
    "银色": "Silver", "金色": "Gold", "玫瑰金": "Rose Gold", "白色": "White",
    "黑色": "Black", "红色": "Red", "蓝色": "Blue", "绿色": "Green",
    "粉色": "Pink", "紫色": "Purple", "透明": "Clear",
}
MATERIAL_MAP = {
    "925银": "925 Silver", "s925银": "S925 Silver", "纯银": "Sterling Silver",
    "不锈钢": "Stainless Steel", "合金": "Alloy", "铜": "Copper",
    "钛钢": "Titanium Steel", "树脂": "Resin", "亚克力": "Acrylic",
}


def _english(value: str | None, mapping: dict[str, str], fallback: str = "") -> str:
    if not value:
        return fallback
    cleaned = value.strip()
    lower = cleaned.lower()
    for source, target in mapping.items():
        if source.lower() == lower:
            return target
    return cleaned if re.fullmatch(r"[\x20-\x7e]+", cleaned) else fallback


def _category(product: ProductMaster) -> str:
    for source, target in CATEGORY_MAP.items():
        if source in (product.title or ""):
            return target
    direct = _english(product.category, CATEGORY_MAP)
    if direct:
        return direct
    return "Jewelry"


def _facts(product: ProductMaster) -> dict:
    skus = []
    for sku in product.skus:
        if not sku.is_sellable:
            continue
        skus.append({
            "id": sku.id,
            "code": sku.sku_code,
            "color": _english(sku.color, COLOR_MAP),
            "size": sku.size or "",
            "material": _english(sku.material, MATERIAL_MAP),
            "quantity": sku.quantity,
            "components": [{"name": component.component_name, "color": _english(component.color, COLOR_MAP), "quantity": component.quantity} for component in sku.components],
        })
    return {
        "spu": product.spu_code,
        "category": _category(product),
        "material": _english(product.material, MATERIAL_MAP),
        "color": _english(product.color, COLOR_MAP),
        "dimensions": product.dimensions or "",
        "weight_g": product.weight_g,
        "skus": skus,
    }


def input_fingerprint(product: ProductMaster) -> str:
    return hashlib.sha256(json.dumps(_facts(product), sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def _sku_name(sku: dict) -> str:
    parts = [part for part in [sku["color"], sku["size"]] if part]
    if sku["quantity"] > 1:
        parts.append(f"{sku['quantity']} Pieces")
    return " / ".join(parts) or sku["code"]


def clean_generated_description(value: str | None) -> str:
    """Drop the old deterministic paragraph while keeping user-written copy."""
    text = str(value or "").strip()
    if (
        text.startswith("This ")
        and " is offered in the SKU options listed on this page." in text
        and text.endswith("Package contents, color, size and quantity follow the selected SKU.")
    ):
        return ""
    return text


def build_copy(product: ProductMaster, platform: str) -> dict:
    platform = platform.upper()
    if platform not in PLATFORM_RULES:
        raise ValueError("Unsupported platform")
    facts = _facts(product)
    colors = list(dict.fromkeys(sku["color"] for sku in facts["skus"] if sku["color"]))
    max_quantity = max((sku["quantity"] for sku in facts["skus"]), default=1)
    title_parts = [facts["material"], " ".join(colors[:3]), facts["category"], facts["dimensions"]]
    if max_quantity > 1:
        title_parts.append(f"{max_quantity}-Piece Set")
    title = " ".join(part for part in title_parts if part).strip()
    if not title:
        title = facts["category"]
    bullets = []
    if facts["material"]:
        bullets.append(f"Material: {facts['material']}.")
    if colors:
        bullets.append(f"Available colors: {', '.join(colors)}.")
    if facts["dimensions"]:
        bullets.append(f"Size: {facts['dimensions']}.")
    if max_quantity > 1:
        bullets.append(f"Set quantity: up to {max_quantity} pieces, depending on the selected SKU.")
    bullets.append("Please select the required color, size and set quantity from the SKU options.")
    sku_names = {str(sku["id"]): _sku_name(sku) for sku in facts["skus"]}
    result = {"title": title, "bullet_points": bullets[:5], "description": "", "sku_names": sku_names}
    result["issues"] = validate_copy(platform, result)
    return result


def validate_copy(platform: str, data: dict) -> list[dict]:
    rules = PLATFORM_RULES[platform.upper()]
    issues: list[dict] = []
    title = str(data.get("title", "")).strip()
    description = str(data.get("description", "")).strip()
    bullets = data.get("bullet_points", [])
    if not title:
        issues.append({"field": "title", "code": "REQUIRED", "message": "English title is required."})
    if len(title) > rules["title_max"]:
        issues.append({"field": "title", "code": "TOO_LONG", "message": f"Title exceeds {rules['title_max']} characters."})
    if len(description) > rules["description_max"]:
        issues.append({"field": "description", "code": "TOO_LONG", "message": f"Description exceeds {rules['description_max']} characters."})
    if len(bullets) > rules["bullets_max"]:
        issues.append({"field": "bullet_points", "code": "TOO_MANY", "message": f"Use no more than {rules['bullets_max']} bullet points."})
    searchable = " ".join([title, description, *map(str, bullets)]).lower()
    for phrase in sorted(BANNED_CLAIMS):
        if phrase in searchable:
            issues.append({"field": "content", "code": "UNSUPPORTED_CLAIM", "message": f"Unsupported claim: {phrase}."})
    return issues


def upsert_generated_copy(db: Session, product: ProductMaster, platform: str) -> ListingCopy:
    platform = platform.upper()
    generated = build_copy(product, platform)
    record = next((item for item in product.listing_copies if item.platform == platform), None)
    if not record:
        record = ListingCopy(product_id=product.id, platform=platform, title="", bullet_points_json="[]", description="", sku_names_json="{}", input_fingerprint="")
        db.add(record)
    record.title = generated["title"]
    record.bullet_points_json = json.dumps(generated["bullet_points"], ensure_ascii=False)
    record.description = generated["description"]
    record.sku_names_json = json.dumps(generated["sku_names"], ensure_ascii=False)
    record.input_fingerprint = input_fingerprint(product)
    record.generator = "deterministic-template"
    record.rules_version = RULES_VERSION
    record.issues_json = json.dumps(generated["issues"], ensure_ascii=False)
    record.status = "NEEDS_ATTENTION" if generated["issues"] else "DRAFT"
    record.reviewed_at = None
    return record


def update_copy(record: ListingCopy, payload: dict) -> ListingCopy:
    record.title = payload["title"].strip()
    record.bullet_points_json = json.dumps([item.strip() for item in payload["bullet_points"] if item.strip()], ensure_ascii=False)
    record.description = payload["description"].strip()
    record.sku_names_json = json.dumps(payload["sku_names"], ensure_ascii=False)
    issues = validate_copy(record.platform, payload)
    record.issues_json = json.dumps(issues, ensure_ascii=False)
    confirmed = bool(payload.get("confirmed_review"))
    record.status = "REVIEWED" if confirmed and not issues else ("NEEDS_ATTENTION" if issues else "DRAFT")
    record.reviewed_at = utcnow() if record.status == "REVIEWED" else None
    return record


def copy_payload(record: ListingCopy) -> dict:
    return {
        "id": record.id, "platform": record.platform, "title": record.title,
        "bullet_points": json.loads(record.bullet_points_json or "[]"),
        "description": record.description, "sku_names": json.loads(record.sku_names_json or "{}"),
        "status": record.status, "issues": json.loads(record.issues_json or "[]"),
        "title_length": len(record.title), "rules": PLATFORM_RULES[record.platform],
        "generator": record.generator, "input_fingerprint": record.input_fingerprint,
        "reviewed_at": record.reviewed_at.isoformat() if record.reviewed_at else None,
    }
