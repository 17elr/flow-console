from __future__ import annotations

import json
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .db import SessionLocal
from .models import AutomationRun, AutomationSchedule, ProductMaster, SkuVariant, StoreAutomationConfig, StoreListing, utcnow
from .publishing import create_store_drafts
from .simple_workflow import workflow_payload


def load_automation_products(db: Session) -> list[ProductMaster]:
    return db.scalars(
        select(ProductMaster)
        .options(
            selectinload(ProductMaster.skus).selectinload(SkuVariant.components),
            selectinload(ProductMaster.assets),
            selectinload(ProductMaster.listing_copies),
            selectinload(ProductMaster.review_decisions),
            selectinload(ProductMaster.listings).selectinload(StoreListing.store),
        )
        .order_by(ProductMaster.updated_at.asc())
    ).unique().all()


def recover_interrupted_runs(db: Session) -> int:
    """Close runs left behind when the single local worker was restarted."""
    runs = db.scalars(select(AutomationRun).where(AutomationRun.status == "RUNNING")).all()
    for run in runs:
        details = json.loads(run.details_json or "[]")
        details.append({
            "status": "INTERRUPTED",
            "reason": "API 进程重启，运行已中断；可重新点击立即运行",
        })
        run.status = "INTERRUPTED"
        run.failed += 1
        run.total = max(run.total, len(details))
        run.details_json = json.dumps(details, ensure_ascii=False)
        run.completed_at = utcnow()
    if runs:
        db.commit()
    return len(runs)


def run_automation(db: Session, store_ids: list[int], max_products: int, trigger: str = "MANUAL", schedule_id: int | None = None) -> AutomationRun:
    run = AutomationRun(schedule_id=schedule_id, trigger=trigger, status="RUNNING")
    db.add(run); db.commit(); db.refresh(run)
    details: list[dict] = []
    processed_products = 0
    for product in load_automation_products(db):
        if processed_products >= max_products:
            break
        try:
            state = workflow_payload(db, product)
            if not state["review"]["approved"]:
                run.skipped += 1
                details.append({"product_id": product.id, "spu": product.spu_code, "status": "SKIPPED", "reason": "等待人工审核"})
                continue
            configs = {
                item.store_id: item
                for item in db.scalars(select(StoreAutomationConfig).where(StoreAutomationConfig.store_id.in_(store_ids))).all()
            }
            results = []
            for store_id in store_ids:
                config = configs.get(store_id)
                results.extend(
                    create_store_drafts(
                        db,
                        product,
                        state,
                        [store_id],
                        respect_automation_limits=True,
                        auto_publish=bool(config and config.auto_publish),
                    )
                )
            processed_products += 1
            run.processed += 1
            for result in results:
                if result["status"] == "SKIPPED":
                    run.skipped += 1
                    details.append({"product_id": product.id, "spu": product.spu_code, **result})
                    continue
                if result["status"] == "PUBLISHING":
                    details.append({"product_id": product.id, "spu": product.spu_code, **result})
                    continue
                # PUBLISHING means Miaoshou accepted an asynchronous task but the
                # item is not yet present in its published bucket. Never count it
                # as success or show the run as completed publication.
                success = result["status"] in {"DRAFT_CREATED", "PUBLISHED", "PACKAGE_READY"}
                run.succeeded += int(success)
                run.failed += int(not success)
                details.append({"product_id": product.id, "spu": product.spu_code, **result})
        except Exception as exc:
            processed_products += 1
            run.processed += 1
            run.failed += 1
            details.append({"product_id": product.id, "spu": product.spu_code, "status": "FAILED", "error": str(exc)[:500]})
            db.rollback()
    run.total = len(details)
    run.details_json = json.dumps(details, ensure_ascii=False)
    waiting_external = any(item.get("status") == "PUBLISHING" for item in details)
    run.status = "COMPLETED_WITH_ERRORS" if run.failed else "WAITING_EXTERNAL" if waiting_external else "COMPLETED"
    run.completed_at = utcnow()
    db.commit(); db.refresh(run)
    return run


def run_payload(run: AutomationRun) -> dict:
    return {"id": run.id, "schedule_id": run.schedule_id, "trigger": run.trigger, "status": run.status, "total": run.total, "processed": run.processed, "succeeded": run.succeeded, "failed": run.failed, "skipped": run.skipped, "details": json.loads(run.details_json or "[]"), "started_at": run.started_at.isoformat(), "completed_at": run.completed_at.isoformat() if run.completed_at else None}


def schedule_payload(schedule: AutomationSchedule) -> dict:
    return {"id": schedule.id, "name": schedule.name, "active": schedule.active, "run_time": schedule.run_time, "timezone": schedule.timezone, "store_ids": json.loads(schedule.store_ids_json or "[]"), "max_products": schedule.max_products, "last_run_date": schedule.last_run_date, "created_at": schedule.created_at.isoformat(), "updated_at": schedule.updated_at.isoformat()}


def scheduler_tick() -> None:
    with SessionLocal() as db:
        schedules = db.scalars(select(AutomationSchedule).where(AutomationSchedule.active.is_(True))).all()
        for schedule in schedules:
            now = datetime.now(ZoneInfo(schedule.timezone))
            today = now.date().isoformat()
            if now.strftime("%H:%M") >= schedule.run_time and schedule.last_run_date != today:
                store_ids = json.loads(schedule.store_ids_json or "[]")
                run_automation(db, store_ids, schedule.max_products, "SCHEDULED", schedule.id)
                schedule.last_run_date = today
                db.commit()


class AutomationScheduler:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="automation-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(30):
            try:
                scheduler_tick()
            except Exception:
                continue


automation_scheduler = AutomationScheduler()
