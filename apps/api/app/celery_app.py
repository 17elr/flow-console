from __future__ import annotations

import os

from celery import Celery

from .image_pipeline import process_job


celery_app = Celery(
    "commerce_images",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)


@celery_app.task(name="commerce.process_image_job")
def process_image_job(job_id: int) -> None:
    process_job(job_id)
