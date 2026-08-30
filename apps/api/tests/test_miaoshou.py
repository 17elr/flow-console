from __future__ import annotations

import hashlib
import hmac
import json

import httpx

from app.miaoshou import MiaoshouError, MiaoshouProvider, normalize_sku_classification


def test_miaoshou_signature_and_shop_request(monkeypatch) -> None:
    monkeypatch.setenv("MIAOSHOU_APP_KEY", "app-key")
    monkeypatch.setenv("MIAOSHOU_APP_SECRET", "app-secret")
    monkeypatch.setattr("app.miaoshou.time.time", lambda: 1700000000)

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        path = MiaoshouProvider.SHOP_LIST_PATH
        expected = hmac.new(
            b"app-secret",
            f"app-secret{path}1700000000app-key{body}app-secret".encode(),
            hashlib.sha256,
        ).hexdigest()
        assert request.headers["x-app-key"] == "app-key"
        assert request.headers["x-timestamp"] == "1700000000"
        assert request.headers["x-sign"] == expected
        assert json.loads(body)["platform"] == "pddkjChoice"
        return httpx.Response(200, json={"result": "success", "code": "success", "message": "success", "data": {"list": []}})

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test") as client:
        result = MiaoshouProvider(client).list_shops("SEMI")
    assert result["data"] == {"list": []}


def test_miaoshou_status_requires_public_assets(monkeypatch) -> None:
    monkeypatch.setenv("MIAOSHOU_APP_KEY", "key")
    monkeypatch.setenv("MIAOSHOU_APP_SECRET", "secret")
    monkeypatch.delenv("PUBLIC_ASSET_BASE_URL", raising=False)
    status = MiaoshouProvider().status()
    assert status["shop_sync_ready"] is True
    assert status["temu_api_ready"] is False
    assert status["missing"] == ["PUBLIC_ASSET_BASE_URL"]


def test_miaoshou_origin_country_derives_province(monkeypatch) -> None:
    monkeypatch.setenv("MIAOSHOU_APP_KEY", "key")
    monkeypatch.setenv("MIAOSHOU_APP_SECRET", "secret")
    monkeypatch.setenv("PUBLIC_ASSET_BASE_URL", "https://assets.example.test")

    captured: dict = {}
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        if "siteCollectItemInfo" not in body:
            return httpx.Response(200, json={"result": "success", "code": "success", "data": {"productAttributeRules": []}})
        captured.update(body["siteCollectItemInfo"])
        return httpx.Response(200, json={"result": "success", "code": "success", "data": {"id": "draft-1"}})

    payload = {
        "spu": "PUB-001",
        "title": "Pendant",
        "external_shop_id": "123",
        "category_parameters": {"cid": "29542", "商品产地": "中国广东"},
        "img_urls": ["https://assets.example.test/main.png"],
        "sku_map": {},
    }
    with httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test") as client:
        MiaoshouProvider(client).create_draft(payload, "key")
    assert captured["productOriginCountry"] == "CN"
    assert captured["productOriginProvince"] == "43000000000006"
    assert captured["itemNum"] == "PUB-001"


def test_miaoshou_adds_six_main_images_to_product_description(monkeypatch) -> None:
    monkeypatch.setenv("MIAOSHOU_APP_KEY", "key")
    monkeypatch.setenv("MIAOSHOU_APP_SECRET", "secret")
    monkeypatch.setenv("PUBLIC_ASSET_BASE_URL", "https://assets.example.test")
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        if "siteCollectItemInfo" not in body:
            return httpx.Response(200, json={"result": "success", "code": "success", "data": {"productAttributeRules": []}})
        captured.update(body["siteCollectItemInfo"])
        return httpx.Response(200, json={"result": "success", "code": "success", "data": {"id": "draft-1"}})

    images = [f"https://assets.example.test/{index:02d}.jpg" for index in range(1, 7)]
    payload = {
        "spu": "PUB-002",
        "title": "Pendant",
        "external_shop_id": "123",
        "category_parameters": {"cid": "29542"},
        "img_urls": images,
        "description_img_urls": images,
        "sku_map": {},
    }
    with httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test") as client:
        MiaoshouProvider(client).create_draft(payload, "key")

    modules = captured["goodsLayerDecorationReqs"]
    assert len(modules) == 6
    assert [item["priority"] for item in modules] == [1, 2, 3, 4, 5, 6]
    assert [item["contentList"][0]["imgUrl"] for item in modules] == images
    assert [item["content"]["imgUrl"] for item in modules] == images
    assert all(item["type"] == "image" and item["key"] == "DecImage" for item in modules)


def test_ensure_shop_item_number_saves_only_when_missing(monkeypatch) -> None:
    provider = MiaoshouProvider()
    monkeypatch.setattr(provider, "get_shop_collect_item_info", lambda *_args: {
        "data": {"shopCollectItemInfo": {"title": "Pendant", "itemNum": None}},
        "response": {"result": "success"},
    })
    captured = {}

    def save(path, payload):
        captured.update({"path": path, "payload": payload})
        return {"response": {"result": "success"}}

    monkeypatch.setattr(provider, "_retry_transition", save)
    result = provider.ensure_shop_item_number("123", "456", "29542", "PUB-001")
    assert result["updated"] is True
    assert captured["path"].endswith("/save_shop_collect_item_info")
    assert captured["payload"]["shopCollectItemInfo"]["itemNum"] == "PUB-001"
    assert captured["payload"]["detailId"] == 456


def test_ensure_shop_item_number_still_saves_missing_stock(monkeypatch) -> None:
    provider = MiaoshouProvider()
    monkeypatch.setattr(provider, "get_shop_collect_item_info", lambda *_args: {
        "data": {"shopCollectItemInfo": {
            "itemNum": "PUB-001",
            "saleAttributes": [{"values": [{"name": "PUB-001-S", "itemNum": "PUB-001-S"}]}],
            "skuMap": {";;PUB-001-S;;": {"itemNum": "PUB-001-S", "stock": None}},
        }},
    })
    captured = {}
    monkeypatch.setattr(provider, "_retry_transition", lambda path, payload: captured.update(payload) or {"response": {"result": "success"}})
    result = provider.ensure_shop_item_number("123", "456", "29542", "PUB-001", "FULL", {"PUB-001-S": 12})
    assert result["updated"] is True
    assert captured["shopCollectItemInfo"]["skuMap"][";;PUB-001-S;;"]["stock"] == 12


def test_miaoshou_omits_empty_generic_required_rules(monkeypatch) -> None:
    """Generic rules such as plug specs must not block a necklace draft."""
    provider = MiaoshouProvider()
    provider._category_rules_cache["29542"] = {
        "productAttributeRules": [
            {"name": "镀层", "required": True, "values": [{"vid": 1, "name": "镀玫瑰金"}]},
            {"name": "插头规格", "required": True, "values": [{"vid": 2, "name": "美规"}]},
        ]
    }
    attrs = provider._build_attributes("29542", {"镀层": "镀玫瑰金色"})
    assert [item["name"] for item in attrs] == ["镀层"]


def test_miaoshou_maps_supply_and_multi_select_attributes_without_inventing_brand_vid() -> None:
    provider = MiaoshouProvider()
    provider._category_rules_cache["29542"] = {
        "productAttributeRules": [
            {"name": "品牌名", "required": False, "values": []},
            {"name": "供电方式", "required": False, "values": [{"vid": 1, "name": "无需供电使用"}]},
            {"name": "营销节日", "required": True, "values": [{"vid": 2, "name": "情人节"}, {"vid": 3, "name": "母亲节"}]},
        ]
    }
    attrs = provider._build_attributes(
        "29542",
        {"品牌名 Brand": "youCons", "供电方式 Power Supply": "无需供电", "营销节日 Holiday": "情人节、母亲节"},
    )
    by_name = {item["name"]: item for item in attrs}
    # Miaoshou exposes no brand choices for this category while its create API
    # still requires a numeric vid. Preserve the Excel value upstream, but do
    # not fabricate an invalid attribute value here.
    assert "品牌名" not in by_name
    assert by_name["供电方式"]["value"] == "无需供电使用"
    assert [item["name"] for item in by_name["营销节日"]["values"]] == ["情人节", "母亲节"]


def test_miaoshou_sku_classification_matches_ui_labels() -> None:
    assert normalize_sku_classification("单品") == (1, "单品")
    assert normalize_sku_classification("同款多件装") == (2, "同款多件装")
    assert normalize_sku_classification("多件混装") == (3, "混合套装")


def test_search_collect_box_scans_status_without_misusing_detail_id(monkeypatch) -> None:
    monkeypatch.setenv("MIAOSHOU_APP_KEY", "key")
    monkeypatch.setenv("MIAOSHOU_APP_SECRET", "secret")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert body["filter"] == {"status": "published"}
        assert "sourceItemIdKeyword" not in body["filter"]
        return httpx.Response(200, json={
            "result": "success",
            "code": "success",
            "data": {"detailList": [{"collectBoxDetailId": 9876}]},
        })

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test") as client:
        result = MiaoshouProvider(client).search_collect_box("9876", status="published")
    assert result["matched"]["collectBoxDetailId"] == 9876


def test_wait_for_publish_checks_authoritative_buckets(monkeypatch) -> None:
    provider = MiaoshouProvider()
    calls: list[str] = []

    def search(_detail_id, _mode="FULL", status=None):
        calls.append(status)
        return {"matched": {"detailId": 12}} if status == "timingPublish" else {"matched": None}

    monkeypatch.setattr(provider, "search_collect_box", search)
    result = provider.wait_for_publish(12, attempts=1, interval=0)
    assert result["verified"] is False
    assert result["state"] == "timingPublish"
    assert result["checked_at"]
    assert calls == ["published", "notPublished", "timingPublish"]


def test_wait_for_publish_retries_temporary_gateway_error(monkeypatch) -> None:
    provider = MiaoshouProvider()
    calls = 0

    def search(_detail_id, _mode="FULL", status=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise MiaoshouError("妙手接口错误 httpGatewayTimeout")
        return {"matched": {"detailId": 12}} if status == "published" else {"matched": None}

    monkeypatch.setattr(provider, "search_collect_box", search)
    result = provider.wait_for_publish(12, attempts=2, interval=0)
    assert result["verified"] is True
    assert result["state"] == "published"
