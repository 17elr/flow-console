from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


class MemoryStorage:
    def __init__(self) -> None:
        self.items: dict[str, bytes] = {}

    def put(self, key: str, content: bytes, _content_type: str) -> None:
        self.items[key] = content

    def get(self, key: str) -> bytes:
        return self.items[key]


def test_simple_product_lists_upload_replace_and_delete_slots(monkeypatch) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    storage = MemoryStorage()
    monkeypatch.setattr("app.main.configured_storage", lambda: storage)

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    payload = {"spu_code": "SIMPLE-001", "title": "Silver necklace", "category": "Necklace", "price": 9.9, "stock": 20, "dimensions": "45 cm", "skus": [{"sku_code": "SIMPLE-001-S", "color": "silver", "size": "45 cm", "quantity": 1, "stock": 20}]}
    try:
        created = client.post("/api/simple-products", json=payload)
        assert created.status_code == 200, created.text
        workflow = created.json()
        assert workflow["status"] == "WAITING_SOURCE"
        required = [slot for slot in workflow["slots"] if slot["required"]]
        assert [slot["slot"] for slot in required] == ["spu-main", f"sku-{workflow['product']['skus'][0]['id']}"]

        image = BytesIO(); Image.new("RGB", (640, 640), "white").save(image, "PNG")
        uploaded = client.put(f"/api/source-assets/{required[0]['slot']}", data={"product_id": workflow["product"]["id"]}, files={"file": ("source.png", image.getvalue(), "image/png")})
        assert uploaded.status_code == 200, uploaded.text
        slot = uploaded.json()["slots"][0]
        assert slot["status"] == "UPLOADED"
        asset_id = slot["asset"]["id"]

        replaced = client.put(f"/api/source-assets/{required[0]['slot']}", data={"product_id": workflow["product"]["id"]}, files={"file": ("replacement.png", image.getvalue(), "image/png")})
        assert replaced.status_code == 200
        assert replaced.json()["slots"][0]["asset"]["id"] != asset_id
        assert client.delete(f"/api/source-assets/{replaced.json()['slots'][0]['asset']['id']}").status_code == 204
        refreshed = client.get(f"/api/products/{workflow['product']['id']}/workflow").json()
        assert refreshed["slots"][0]["status"] == "MISSING"
    finally:
        app.dependency_overrides.clear()


def test_miaoshou_status_never_returns_secrets(monkeypatch) -> None:
    monkeypatch.setenv("MIAOSHOU_APP_KEY", "secret-key")
    monkeypatch.setenv("MIAOSHOU_APP_SECRET", "secret-value")
    monkeypatch.delenv("MIAOSHOU_DRAFT_PATH", raising=False)
    response = TestClient(app).get("/api/miaoshou/status")
    assert response.status_code == 200
    assert "secret-key" not in response.text
    assert "secret-value" not in response.text
    assert response.json()["temu_api_ready"] is False
