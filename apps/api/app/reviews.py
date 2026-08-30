from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AssetVersion, ProductMaster, ReviewDecision


def product_review_fingerprint(product: ProductMaster, outputs: list[dict]) -> str:
    payload = {
        "images": sorted(
            (item["asset"]["id"], item["asset"]["sha256"])
            for item in outputs
            if item.get("asset")
        ),
        "copies": sorted(
            (copy.id, copy.platform, copy.input_fingerprint, copy.updated_at.isoformat())
            for copy in product.listing_copies
        ),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def review_payload(product: ProductMaster, outputs: list[dict], expected_count: int) -> dict:
    decisions = {(item.subject_type, item.subject_id): item for item in product.review_decisions}
    approved_images = 0
    rejected_images = 0
    for output in outputs:
        asset = output.get("asset")
        if not asset:
            output["review"] = None
            continue
        decision = decisions.get(("IMAGE", asset["id"]))
        valid = bool(decision and decision.subject_fingerprint == asset["sha256"])
        output["review"] = ({
            "decision": decision.decision,
            "note": decision.note,
            "reviewer": decision.reviewer,
            "updated_at": decision.updated_at.isoformat(),
        } if valid else None)
        if valid and decision.decision == "APPROVED":
            approved_images += 1
        elif valid and decision.decision == "REJECTED":
            rejected_images += 1
    copies_reviewed = sum(copy.status == "REVIEWED" for copy in product.listing_copies)
    all_images_present = len([item for item in outputs if item.get("asset")]) >= expected_count
    can_approve = all_images_present and approved_images >= expected_count and rejected_images == 0 and copies_reviewed >= 2
    fingerprint = product_review_fingerprint(product, outputs)
    product_decision = decisions.get(("PRODUCT", 0))
    product_valid = bool(product_decision and product_decision.subject_fingerprint == fingerprint)
    approved = bool(product_valid and product_decision.decision == "APPROVED" and can_approve)
    rejected = rejected_images > 0 or bool(product_valid and product_decision.decision == "REJECTED")
    status = "APPROVED" if approved else "REJECTED" if rejected else "READY_TO_APPROVE" if can_approve else "IN_REVIEW"
    return {
        "status": status,
        "approved": approved,
        "can_approve": can_approve,
        "approved_images": approved_images,
        "rejected_images": rejected_images,
        "expected_images": expected_count,
        "copies_reviewed": copies_reviewed,
        "expected_copies": 2,
        "product_note": product_decision.note if product_valid and product_decision else None,
        "fingerprint": fingerprint,
    }


def save_image_decision(db: Session, asset: AssetVersion, decision: str, note: str | None) -> ReviewDecision:
    record = db.scalar(select(ReviewDecision).where(
        ReviewDecision.product_id == asset.product_id,
        ReviewDecision.subject_type == "IMAGE",
        ReviewDecision.subject_id == asset.id,
    ))
    if not record:
        record = ReviewDecision(product_id=asset.product_id, subject_type="IMAGE", subject_id=asset.id, subject_fingerprint=asset.sha256, decision=decision)
        db.add(record)
    record.subject_fingerprint = asset.sha256
    record.decision = decision
    record.note = note.strip() if note else None
    return record


def save_product_decision(db: Session, product: ProductMaster, summary: dict, decision: str, note: str | None) -> ReviewDecision:
    if decision == "APPROVED" and not summary["can_approve"]:
        raise ValueError("请先通过全部图片并确认两套平台文案")
    record = db.scalar(select(ReviewDecision).where(
        ReviewDecision.product_id == product.id,
        ReviewDecision.subject_type == "PRODUCT",
        ReviewDecision.subject_id == 0,
    ))
    if not record:
        record = ReviewDecision(product_id=product.id, subject_type="PRODUCT", subject_id=0, subject_fingerprint=summary["fingerprint"], decision=decision)
        db.add(record)
    record.subject_fingerprint = summary["fingerprint"]
    record.decision = decision
    record.note = note.strip() if note else None
    return record
