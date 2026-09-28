from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


def test_aliexpress_upload_persists_and_can_be_reused(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr("app.compliance.ROOT", tmp_path)
    monkeypatch.setattr("app.compliance.read_image", lambda content: "Manufacturer and product label")

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    image = BytesIO()
    Image.new("RGB", (64, 64), "white").save(image, "PNG")
    try:
        for code in ("AE-FIRST", "AE-SECOND"):
            result = client.post("/api/simple-products", json={
                "platform": "ALIEXPRESS", "spu_code": code, "title": code,
                "category": "Necklace", "price": 10, "stock": 1,
                "dimensions": "45cm", "skus": [{"sku_code": code + "-S", "color": "silver"}],
            })
            assert result.status_code == 200, result.text
            if code == "AE-FIRST":
                first_id = result.json()["product"]["id"]
            else:
                second_id = result.json()["product"]["id"]

        uploaded = client.put(f"/api/products/{first_id}/compliance/label", files={
            "file": ("label.png", image.getvalue(), "image/png")
        })
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()["text"] == "Manufacturer and product label"
        assert client.get(f"/api/products/{first_id}/compliance").json()[0]["filename"] == "label.png"
        source_id = uploaded.json()["id"]
        assert any(item["id"] == source_id for item in client.get("/api/compliance-library").json())

        reused = client.post(f"/api/products/{second_id}/compliance/label/reuse/{source_id}")
        assert reused.status_code == 200, reused.text
        assert reused.json()["filename"] == "label.png"
        assert client.get(f"/api/products/{second_id}/compliance/files/{reused.json()['id']}").content == image.getvalue()

        presentation = BytesIO()
        with ZipFile(presentation, 'w') as archive:
            archive.writestr('ppt/slides/slide1.xml', '<p:sld xmlns:p="p" xmlns:a="a"><a:t>Test report</a:t></p:sld>')
        report = client.put(f"/api/products/{first_id}/compliance/reach", files={
            "file": ("report.pptx", presentation.getvalue(), "application/vnd.openxmlformats-officedocument.presentationml.presentation")
        })
        assert report.status_code == 200, report.text
        assert report.json()["text"] == "Test report"

        temu = client.post("/api/simple-products", json={
            "spu_code": "TEMU-ONLY", "title": "temu", "category": "Necklace",
            "price": 10, "stock": 1, "dimensions": "45cm",
            "skus": [{"sku_code": "TEMU-ONLY-S", "color": "silver"}],
        }).json()["product"]["id"]
        assert client.put(f"/api/products/{temu}/compliance/label", files={
            "file": ("label.png", image.getvalue(), "image/png")
        }).status_code == 409
    finally:
        app.dependency_overrides.clear()
