"""Run real API handlers against a fresh temporary SQLite DB; no external publishing."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="flow-console-evidence-") as directory:
        runtime = Path(directory)
        os.environ["DATABASE_URL"] = f"sqlite:///{(runtime / 'demo.db').as_posix()}"
        os.environ["LOCAL_ASSET_ROOT"] = str(runtime / "assets")
        os.environ["STORAGE_BACKEND"] = "local"

        from fastapi.testclient import TestClient
        from openpyxl import Workbook
        from PIL import Image
        from app.db import Base, engine
        from app.main import app

        Base.metadata.create_all(engine)
        checks = []
        # No lifespan: seed jobs and platform/model workers are outside this evidence scope.
        client = TestClient(app)

        try:
            def request(label, method, url, expected=200, **kwargs):
                started = perf_counter()
                response = client.request(method, url, **kwargs)
                assert response.status_code == expected, (label, response.status_code, response.text)
                checks.append({"check": label, "method": method, "path": url,
                               "http_status": response.status_code,
                               "duration_ms": round((perf_counter() - started) * 1000, 2)})
                return response.json()

            workbook = Workbook()
            products = workbook.active
            products.title = "Products"
            products.append(["spu_code", "title", "category", "material", "color", "dimensions",
                             "price", "stock", "source_image_url", "image_rights"])
            skus = workbook.create_sheet("SKUs")
            skus.append(["spu_code", "sku_code", "title", "color", "size", "material", "quantity",
                         "price", "stock", "source_image_url", "is_sellable"])
            for i in range(25):
                spu = f"EVIDENCE-{i:03}"
                products.append([spu, f"合成测试商品 {i}", "饰品", "合金", "银色", "45cm",
                                 9.9, 20, "https://example.com/synthetic.png", "AUTHORIZED"])
                for color in ("silver", "gold"):
                    skus.append([spu, f"{spu}-{color}", color, color, "45cm", "合金", 1,
                                 9.9, 10, "https://example.com/synthetic.png", True])
            stream = BytesIO()
            workbook.save(stream)
            content = stream.getvalue()
            started = perf_counter()
            batch = request("import 25 synthetic SPUs / 50 SKUs", "POST", "/api/imports/excel",
                            files={"file": ("synthetic.xlsx", content,
                                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
            assert batch["status"] == "COMPLETED" and batch["issue_rows"] == 0, batch
            before = request("count persisted products", "GET", "/api/overview")
            assert (before["products"], before["skus"]) == (25, 50), before
            request("reimport same workbook", "POST", "/api/imports/excel",
                    files={"file": ("synthetic.xlsx", content,
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
            after = request("verify no duplicate SPUs or SKUs", "GET", "/api/overview")
            assert (after["products"], after["skus"]) == (25, 50), after
            created = request("create isolated source-upload product", "POST", "/api/simple-products",
                              json={"spu_code": "EVIDENCE-UPLOAD", "title": "合成素材验证商品",
                                    "category": "饰品", "price": 9.9, "stock": 20, "dimensions": "45cm",
                                    "skus": [{"sku_code": "EVIDENCE-UPLOAD-S", "color": "silver",
                                              "size": "45cm", "quantity": 1, "stock": 20}]})
            product_id = created["product"]["id"]
            persisted = request("reload persisted workflow", "GET", f"/api/products/{product_id}/workflow")
            required = [slot for slot in persisted["slots"] if slot["required"]]
            assert len(required) == 2
            image_stream = BytesIO()
            Image.new("RGB", (640, 640), "white").save(image_stream, "PNG")
            png = image_stream.getvalue()
            for slot in required:
                uploaded = request(f"upload valid source: {slot['slot']}", "PUT",
                                   f"/api/source-assets/{slot['slot']}", data={"product_id": product_id},
                                   files={"file": ("synthetic.png", png, "image/png")})
                uploaded = request(f"reload source: {slot['slot']}", "GET", f"/api/products/{product_id}/workflow")
                assert next(s for s in uploaded["slots"] if s["slot"] == slot["slot"])["status"] == "UPLOADED"
            saved_id = next(s for s in uploaded["slots"] if s["slot"] == "spu-main")["asset"]["id"]
            request("reject fake image bytes", "PUT", "/api/source-assets/spu-main", expected=422,
                    data={"product_id": product_id}, files={"file": ("invalid.png", b"not an image", "image/png")})
            workflow = request("confirm invalid upload preserves previous asset", "GET",
                               f"/api/products/{product_id}/workflow")
            assert workflow["slots"][0]["asset"]["id"] == saved_id
            final = request("final persisted counts", "GET", "/api/overview")
            assert (final["products"], final["skus"]) == (26, 51)
            assert len(list((runtime / "assets").rglob("*.png"))) == 2
            report = {
                "recorded_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
                "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "environment": {"python": platform.python_version(), "os": platform.system(),
                                "transport": "FastAPI TestClient / real handlers", "database": "temporary SQLite file"},
                "data_scope": "synthetic fixtures, not merchant production data",
                "passed": True, "check_count": len(checks), "checks": checks,
                "input": {"spus": 25, "skus": 50, "workbook_sha256": hashlib.sha256(content).hexdigest()},
                "result": {"products_after_reimport": after["products"], "skus_after_reimport": after["skus"],
                           "final_products": final["products"], "final_skus": final["skus"],
                           "source_files": 2, "invalid_image_status": 422},
                "local_elapsed_ms": round((perf_counter() - started) * 1000, 2),
                "external_calls": 0,
                "limits": ["No application lifespan, background jobs or network server exercised",
                           "No paid model or store API called", "No production throughput or efficiency claim"],
            }
            output = ROOT / "docs/evidence/demo-run.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        finally:
            client.close()
            engine.dispose()
        print(f"PASS {len(checks)} API checks; 25 SPUs / 50 SKUs reimported without duplicates; evidence: {output}")


if __name__ == "__main__":
    main()
