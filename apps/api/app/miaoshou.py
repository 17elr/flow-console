from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx


class MiaoshouError(RuntimeError):
    pass


def normalize_sku_classification(value: Any) -> tuple[int, str]:
    """Return the Miaoshou enum and label for the Excel SKU classification."""
    text = str(value or "").strip()
    normalized = re.sub(r"[\s_/（）()]+", "", text)
    if normalized in {"混合套装", "多件混装", "组合装套装"}:
        return 3, "混合套装"
    if normalized in {"同款多件装", "同款多件", "多件装"}:
        return 2, "同款多件装"
    return 1, "单品"


class MiaoshouProvider:
    _request_lock = threading.Lock()
    _last_request_at = 0.0
    # TEMU category used by this workspace's finished-upload workflow.
    # Older imports predate the cid column, so they need a backwards-compatible default.
    DEFAULT_TEMU_NECKLACE_CID = "29542"
    CHINA_PROVINCE_CODES = {
        "广东": "43000000000006",
        "广东省": "43000000000006",
    }
    SHOP_LIST_PATH = "/open/v1/product/shop/shop/get_shop_list"
    TEMU_PATHS = {
        "FULL": {
            "create": "/open/v1/product/collect_box/pddkj/collect_box/create_collect_box_item",
            "claim": "/open/v1/product/collect_box/pddkj/collect_box/claim_to_shop",
            "publish": "/open/v1/product/collect_box/pddkj/move_collect/save_move_collect_task",
            "search": "/open/v1/product/collect_box/pddkj/collect_box/search_collect_box_detail_list",
            "shop_info": "/open/v1/product/collect_box/pddkj/collect_box/get_shop_collect_item_info",
        },
        "SEMI": {
            "create": "/open/v1/product/collect_box/pddkj_choice/collect_box/create_collect_box_item",
            "claim": "/open/v1/product/collect_box/pddkj_choice/collect_box/claim_to_shop",
            "publish": "/open/v1/product/collect_box/pddkj_choice/move_collect/save_move_collect_task",
            "search": "/open/v1/product/collect_box/pddkj_choice/collect_box/search_collect_box_detail_list",
            "shop_info": "/open/v1/product/collect_box/pddkj_choice/collect_box/get_shop_collect_item_info",
        },
    }

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.base_url = os.getenv("MIAOSHOU_BASE_URL", "https://openapi-erp.91miaoshou.com").rstrip("/")
        self.app_key = os.getenv("MIAOSHOU_APP_KEY", "")
        self.app_secret = os.getenv("MIAOSHOU_APP_SECRET", "")
        self.public_asset_base_url = os.getenv("PUBLIC_ASSET_BASE_URL", "").rstrip("/")
        self._client = client
        self._category_rules_cache: dict[str, dict[str, Any]] = {}

    def status(self) -> dict[str, Any]:
        configured = bool(self.app_key and self.app_secret)
        return {
            "configured": configured,
            "signature_version": "HMAC-SHA256-v1",
            "shop_sync_ready": configured,
            "temu_api_ready": configured and bool(self.public_asset_base_url),
            "missing": (["MIAOSHOU_APP_KEY", "MIAOSHOU_APP_SECRET"] if not configured else [])
            + ([] if self.public_asset_base_url else ["PUBLIC_ASSET_BASE_URL"]),
            "public_assets_configured": bool(self.public_asset_base_url),
            "aliexpress_mode": "IMPORT_PACKAGE",
            "supported_api_platforms": ["TEMU_FULL", "TEMU_SEMI"],
            "aliexpress_draft_ready": bool(os.getenv("MIAOSHOU_ALIEXPRESS_DRAFT_PATH")),
        }

    def _body(self, payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def _headers(self, path: str, body: str) -> dict[str, str]:
        if not self.app_key or not self.app_secret:
            raise MiaoshouError("妙手 AppKey 或 AppSecret 未配置")
        timestamp = str(int(time.time()))
        content = f"{self.app_secret}{path}{timestamp}{self.app_key}{body}{self.app_secret}"
        signature = hmac.new(self.app_secret.encode(), content.encode(), hashlib.sha256).hexdigest()
        return {
            "Content-Type": "application/json",
            "x-app-key": self.app_key,
            "x-timestamp": timestamp,
            "x-sign": signature,
        }

    def request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = self._body(payload)
        request_id = f"flow-console-{uuid.uuid4().hex}"
        try:
            # Miaoshou applies the QPS limit to the whole account, not to one
            # endpoint. Serialize requests made by concurrent UI/automation jobs.
            min_interval = max(float(os.getenv("MIAOSHOU_MIN_REQUEST_INTERVAL", "1.2")), 0.0)
            with self._request_lock:
                elapsed = time.monotonic() - type(self)._last_request_at
                if elapsed < min_interval:
                    time.sleep(min_interval - elapsed)
                if self._client:
                    response = self._client.post(path, content=body.encode(), headers=self._headers(path, body))
                else:
                    response = httpx.post(
                        f"{self.base_url}{path}", content=body.encode(), headers=self._headers(path, body), timeout=60
                    )
                type(self)._last_request_at = time.monotonic()
        except httpx.HTTPError as exc:
            raise MiaoshouError(f"妙手网络请求失败：{type(exc).__name__}") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise MiaoshouError(f"妙手接口返回无法解析的响应（HTTP {response.status_code}）") from exc
        if not response.is_success or data.get("result") == "fail" or data.get("code") not in (None, "success", 0, "0"):
            code = data.get("code") or response.status_code
            message = data.get("message") or "未知错误"
            if "Product attributes up to 45" in str(message):
                item = payload.get("siteCollectItemInfo") or {}
                attrs = item.get("attributes") or []
                message = f"{message}（本次提交 {len(attrs)} 个属性：{','.join(str(a.get('name') or a.get('propName') or '') for a in attrs)}）"
            raise MiaoshouError(f"妙手接口错误 {code}：{message}")
        return {"request_id": request_id, "data": data.get("data"), "response": data}

    def list_shops(self, mode: str, page_no: int = 1, page_size: int = 100) -> dict[str, Any]:
        semi = mode.upper() in {"SEMI", "HALF", "PDDKJCHOICE", "半托管"}
        return self.request(
            self.SHOP_LIST_PATH,
            {"platform": "pddkjChoice" if semi else "pddkj", "site": "PDDKJCHOICE" if semi else "PDDKJ", "pageNo": page_no, "pageSize": page_size},
        )

    def _category_rules(self, cid: str) -> dict[str, Any]:
        if cid not in self._category_rules_cache:
            result = self.request(
                "/open/v1/product/collect_box/pddkj/collect_box/get_category_attribute_rules",
                {"cid": cid},
            )
            self._category_rules_cache[cid] = result.get("data") or {}
        return self._category_rules_cache[cid]

    @staticmethod
    def _norm(value: Any) -> str:
        return re.sub(r"[\\s\\-_/()（）:：]+", "", str(value or "")).lower()

    def _build_attributes(self, cid: str, raw: dict[str, Any]) -> list[dict[str, Any]]:
        """Translate the human-readable Excel fields into Miaoshou property objects.

        Rules are fetched from Miaoshou instead of hard-coding category value IDs. This
        keeps the integration valid when a category's option IDs are revised.
        """
        rules = self._category_rules(cid).get("productAttributeRules") or []
        by_name = {self._norm(rule.get("name")): rule for rule in rules if rule.get("name")}
        aliases = {
            "镀层": ["镀层", "plating"],
            "镶嵌材质": ["镶嵌材质", "inlaymaterial"],
            "主体材质": ["主体材质", "mainmaterial"],
            "风格": ["风格", "style"],
            "佩戴场合": ["佩戴场合", "occasion"],
            "适配季节": ["适配季节", "season"],
            "营销节日": ["营销节日", "holiday"],
            "主题": ["主题", "theme"],
            "供电方式": ["供电方式", "powersupply", "power_supply"],
            # TEMU's category UI exposes birthstone, but the collect-box create
            # endpoint rejects this field for category 29542. Keep the Excel
            # value in the product record without sending it as an attribute.
            "品牌名": ["品牌名", "brand"],
            "金属部件材质类型": ["金属部件材质类型", "materialtypesofmetalparts"],
            "是否含金属部件": ["是否含金属部件", "whetheritcontainsmetalcomponents"],
            "有无礼盒": ["有无礼盒", "withorwithoutgiftbox"],
        }
        value_by_rule: dict[str, Any] = {}
        for canonical, names in aliases.items():
            rule = next((by_name.get(self._norm(name)) for name in names if by_name.get(self._norm(name))), None)
            if rule:
                value_by_rule[canonical] = rule
        # The category endpoint also returns unrelated generic rules (plugs,
        # voltage, batteries, wood, etc.). Submit only fields represented by
        # this product template; sending the whole superset exceeds Miaoshou's
        # 45-attribute limit and creates invalid necklace drafts.

        def field_value(names: list[str]) -> str:
            wanted = [self._norm(name) for name in names]
            for key, value in raw.items():
                normalized_key = self._norm(key)
                if any(name in normalized_key or normalized_key in name for name in wanted) and value not in (None, ""):
                    return str(value).strip()
            return ""

        value_aliases = {
            "镀玫瑰金色": "镀玫瑰金", "镀银色": "镀银", "镀金色": "镀14K金",
            "人造锆石": "合成锆石（合成立方氧化锆）", "锆石": "合成锆石（合成立方氧化锆）",
            "浪漫": "其他", "聚会": "派对", "四季": "全年", "生日": "无",
            # Excel uses the common business label; Miaoshou's category enum
            # calls the same motif "心形".
            "爱心": "心形",
            "无需供电": "无需供电使用",
        }
        raw_names = {
            "镀层": ["镀层", "Plating"], "镶嵌材质": ["镶嵌材质", "Inlay Material"],
            "主体材质": ["主体材质", "Main Material"], "风格": ["风格", "Style"],
            "佩戴场合": ["佩戴场合", "Occasion"], "适配季节": ["适配季节", "Season"],
            "营销节日": ["营销节日", "节日", "Holiday"], "主题": ["主题", "Theme"],
            "品牌名": ["品牌名", "Brand"], "金属部件材质类型": ["金属部件材质类型", "Material Types of Metal Parts"],
            "是否含金属部件": ["是否含金属部件", "Whether it contains metal components"],
            "有无礼盒": ["有无礼盒", "With Or Without Gift Box"],
            "系列线": ["系列线", "系列", "Collection"],
        }
        for canonical in value_by_rule:
            raw_names.setdefault(canonical, [canonical])
        multi_select = {"风格", "佩戴场合", "营销节日", "金属部件材质类型", "主题", "系列线"}
        output: list[dict[str, Any]] = []
        invalid: list[str] = []
        for canonical, rule in value_by_rule.items():
            # Do not invent values that are absent from the user's Excel data.
            value = field_value(raw_names[canonical])
            # Miaoshou occasionally returns a superset of generic rules for a
            # category (for example plug, voltage and battery fields on a
            # necklace category).  Those fields are not present in the user's
            # Excel/template and must be omitted rather than submitted as an
            # empty value.  A genuinely supplied value is still validated below.
            if not value:
                continue
            values = [item.strip() for item in re.split(r"[、,，;；|]+", value) if item.strip()]
            if canonical not in multi_select and values:
                values = values[:1]
            if canonical == "有无礼盒":
                values = [{"有": "有礼盒", "无": "无礼盒", "是": "有礼盒", "否": "无礼盒"}.get(item, item) for item in values]
            else:
                values = [value_aliases.get(item, item) for item in values]
            if canonical in {"诞生石", "主题", "系列线", "供电方式"} and all(item in {"无", "无此项", "不适用"} for item in values):
                continue
            options = rule.get("values") or []
            # The rules endpoint may omit brand options, but the create endpoint still
            # requires values[].vid.  Never fabricate a brand ID from free text.
            if not options:
                continue
            if canonical in multi_select and len(values) == 1 and values[0] == "全选":
                values = [str(item.get("name")) for item in options if item.get("name")]
            selected = []
            for item_value in values:
                option = next((item for item in options if self._norm(item.get("name")) == self._norm(item_value)), None)
                if option:
                    selected.append(option)
                else:
                    invalid.append(f"【{rule.get('name')}】值“{item_value}”")
            if not selected:
                continue
            option = selected[0]
            output.append({
                "pid": rule.get("pid"), "templatePid": rule.get("templatePid"), "refPid": rule.get("refPid"),
                "vid": option.get("vid"), "name": rule.get("name"), "value": "、".join(item.get("name") for item in selected),
                "values": [{"vid": item.get("vid"), "name": item.get("name"), "value": item.get("name")} for item in selected],
                "propName": rule.get("name"), "propValue": "、".join(item.get("name") for item in selected),
            })
        if invalid:
            raise MiaoshouError("TEMU 类目属性与妙手选项不一致：" + "；".join(invalid))
        return output

    @staticmethod
    def _build_sale_attributes(sku_map: dict[str, Any], raw: dict[str, Any]) -> list[dict[str, Any]]:
        # This category uses a single free-text sale specification. The source folder
        # names are already the authoritative SKU/color labels, so preserve them exactly.
        names = [str(item.get("itemNum") or key).strip() for key, item in sku_map.items()]
        names = [name for name in names if name]
        if not names:
            return []
        return [{
            "name": "颜色", "specName": "颜色", "parentSpecId": 1001, "values": [
                {"name": name, "skuKey": f";{name};", "itemNum": name, "imgUrls": []} for name in dict.fromkeys(names)
            ],
        }]

    def create_draft(self, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        """Backward-compatible product draft entry point used by publishing.py.

        The public API creates a TEMU full-managed collection-box item. The
        caller's normalized payload is retained in the request so validation
        errors from Miaoshou are returned to the review UI instead of a 500.
        """
        if not self.status()["temu_api_ready"]:
            raise MiaoshouError("妙手 TEMU 草稿暂不可用：请先配置公网图片地址")
        category_parameters = payload.get("category_parameters") or {}
        cid = str(
            category_parameters.get("cid")
            or category_parameters.get("妙手类目ID")
            or category_parameters.get("妙手类目ID cid")
            or category_parameters.get("类目ID")
            or ""
        ).strip()
        if not cid:
            category_name = str(payload.get("category") or payload.get("category_name") or "")
            if "女士时尚吊坠项链" in category_name or "女士时尚吊坠项链" in str(category_parameters.get("商品类目") or ""):
                cid = self.DEFAULT_TEMU_NECKLACE_CID
        if not cid:
            raise MiaoshouError(
                "TEMU 类目 ID（cid）缺失。当前商品只有类目名称，妙手创建草稿必须使用该店铺站点返回的末级类目 ID。"
            )
        external_shop_id = str(payload.get("external_shop_id") or "").strip()
        if not external_shop_id.isdigit():
            raise MiaoshouError("妙手店铺授权 ID 缺失，请先重新同步店铺")
        image_urls = [url for url in (payload.get("img_urls") or []) if str(url).startswith("https://")]
        if not image_urls:
            raise MiaoshouError("没有可供妙手读取的 HTTPS 商品图片，请检查腾讯云 COS 公网地址")
        origin = str(category_parameters.get("商品产地") or category_parameters.get("productOrigin") or "").strip()
        province = str(category_parameters.get("productOriginProvince") or "").strip()
        if not province and origin.startswith("中国"):
            province = re.sub(r"^中国", "", origin).strip()
        province_name = province.removesuffix("省")
        province_code = self.CHINA_PROVINCE_CODES.get(province)
        sku_quantity = next((value for key, value in category_parameters.items() if "SKU" in str(key) and ("件数" in str(key) or "件數" in str(key))), None)
        sku_quantity = int(sku_quantity or category_parameters.get("skuQuantity") or 1)
        sku_classification = next((value for key, value in category_parameters.items() if "SKU" in str(key) and ("分类" in str(key) or "分類" in str(key))), "")
        sku_classification_code, sku_classification_name = normalize_sku_classification(sku_classification)
        description_images = [url for url in (payload.get("description_img_urls") or image_urls) if str(url).startswith("https://")]
        description_modules = [
            {
                "floorId": None,
                "goodsId": 0,
                "lang": "en",
                "type": "image",
                "priority": index,
                "key": "DecImage",
                "content": {"imgUrl": url, "width": 800, "height": 800},
                "contentList": [{"imgUrl": url, "width": 800, "height": 800, "text": ""}],
            }
            for index, url in enumerate(description_images[:6], 1)
        ]
        product = {
            "title": payload.get("title", ""),
            "itemNum": str(payload.get("spu") or "").strip(),
            # Brand is a free-text Excel field for this category.  The category
            # rules currently return no brand enum values, so it cannot be put
            # in attributes[]. Keep it in the product-level field for clients
            # that support free-text brands without fabricating a numeric vid.
            "brandName": category_parameters.get("品牌名") or category_parameters.get("品牌名 Brand") or category_parameters.get("brandName") or "",
            # The category UI exposes this field, but the create endpoint rejects
            # it inside attributes[]. Preserve the valid enum at product level.
            "powerSupply": "无需供电使用" if str(category_parameters.get("供电方式") or category_parameters.get("供电方式 Power Supply") or "").strip() in {"无需供电", "无需供电使用"} else str(category_parameters.get("供电方式") or category_parameters.get("供电方式 Power Supply") or "").strip(),
            "cid": cid,
            "productOriginCountry": category_parameters.get("productOriginCountry", "CN"),
            "productOriginProvince": province_code or province_name,
            "productOrigin": {
                "region1ShortName": category_parameters.get("productOriginCountry", "CN"),
                "region2Id": province_code or None,
            },
            "imgUrls": image_urls,
            "isBasePlate": 0,
            "outerPackageShape": (payload.get("category_parameters") or {}).get("outerPackageShape", 1),
            "outerPackageType": (payload.get("category_parameters") or {}).get("outerPackageType", 1),
            "outerPackageImgUrls": payload.get("packaging_img_urls") or [],
            "goodsLayerDecorationReqs": description_modules,
            "collectBoxDetailShopList": [{"shopId": int(external_shop_id), "publishSiteList": ["US"]}],
            "attributes": category_parameters.get("attributes") or self._build_attributes(cid, category_parameters),
            "saleAttributes": category_parameters.get("saleAttributes") or self._build_sale_attributes(payload.get("sku_map") or {}, category_parameters),
            "skuMap": payload.get("sku_map") or {},
            "skuCategory": sku_classification_code,
            "skuQuantity": int(category_parameters.get("SKU内单品件数") or category_parameters.get("skuQuantity") or 1),
            "skuType": sku_classification_code,
            "skuClassification": sku_classification_code,
            "skuClassificationQuantity": int(category_parameters.get("SKU内单品件数") or category_parameters.get("skuQuantity") or 1),
            "skuCount": int(category_parameters.get("SKU内单品件数") or category_parameters.get("skuQuantity") or 1),
            "skuNum": int(category_parameters.get("SKU内单品件数") or category_parameters.get("skuQuantity") or 1),
            "skuClassificationNum": int(category_parameters.get("SKU内单品件数") or category_parameters.get("skuQuantity") or 1),
            "skuClassificationCount": int(category_parameters.get("SKU内单品件数") or category_parameters.get("skuQuantity") or 1),
            "skuClassificationInfo": {
                "name": sku_classification_name,
                "quantity": int(category_parameters.get("SKU内单品件数") or category_parameters.get("skuQuantity") or 1),
            },
            "skuClassificationList": [{
                "name": sku_classification_name,
                "quantity": int(category_parameters.get("SKU内单品件数") or category_parameters.get("skuQuantity") or 1),
            }],
            "skuInfo": {
                "skuType": sku_classification_code,
                "skuQuantity": int(category_parameters.get("SKU内单品件数") or category_parameters.get("skuQuantity") or 1),
            },
        }
        for key in ("skuQuantity", "skuClassificationQuantity", "skuCount", "skuNum", "skuClassificationCount"):
            product[key] = sku_quantity
        product["skuClassificationNum"] = 1
        product["skuClassification"] = sku_classification_code
        result = self.request(self.TEMU_PATHS["FULL"]["create"], {"siteCollectItemInfo": product})
        data = result.get("data") or {}
        external_id = data.get("collectBoxDetailId") or data.get("id") or data.get("itemId") or data.get("collectBoxItemId")
        if not external_id:
            raise MiaoshouError("妙手创建草稿成功响应中没有商品 ID")
        return {"external_id": str(external_id), "request_id": result["request_id"], "response": result["response"]}

    def create_aliexpress_draft(self, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        """Create an AliExpress draft through the separately configured contract.

        The AliExpress endpoint and wire schema are intentionally independent from
        TEMU.  They must be supplied from the Miaoshou contract rather than guessed.
        """
        path = os.getenv("MIAOSHOU_PUBLIC_COLLECT_CREATE_PATH", "").strip()
        if not path:
            raise MiaoshouError("公共采集箱创建接口未配置：请设置 MIAOSHOU_PUBLIC_COLLECT_CREATE_PATH")
        shop_id = str(payload.get("external_shop_id") or "").strip()
        if not shop_id:
            raise MiaoshouError("速卖通店铺授权 ID 缺失，请先同步店铺")
        parameters = payload.get("category_parameters") or {}
        source_attrs = [{"name": str(k), "value": str(v)} for k, v in parameters.items() if v not in (None, "")]
        dimensions = payload.get("dimensions") or {}
        product = {
            "title": payload.get("title") or "",
            "itemNum": str(payload.get("spu") or "").strip(),
            "notesText": payload.get("description") or "",
            "notes": payload.get("description") or "",
            "sourceAttrs": source_attrs,
            "price": payload.get("price"),
            "stock": payload.get("stock"),
            "packageLength": dimensions.get("length"),
            "packageWidth": dimensions.get("width"),
            "packageHeight": dimensions.get("height"),
            "weight": payload.get("weight"),
            "imgUrls": payload.get("img_urls") or [],
            "skuMap": payload.get("sku_map") or {},
        }
        # Public collect-box creation accepts these fields at the request root.
        result = self.request(path, product)
        data = result.get("data") or {}
        external_id = data.get("collectBoxDetailId") or data.get("draftId") or data.get("productId") or data.get("id")
        if not external_id:
            raise MiaoshouError("公共采集箱创建响应中没有 collectBoxDetailId")
        claim_path = os.getenv("MIAOSHOU_PUBLIC_COLLECT_CLAIM_PATH", "").strip()
        claim_response = None
        if claim_path:
            claim_response = self.request(claim_path, {"detailSerialNumberPlatformList": [{"detailId": int(external_id), "platform": "ALIEXPRESS", "serialNumber": int(shop_id)}]})
            claim_data = claim_response.get("data") or {}
            if claim_response.get("result") not in (None, "success"):
                raise MiaoshouError(claim_response.get("message") or "公共采集箱认领速卖通店铺失败")
            mapping = claim_data.get("platformCollectBoxDetailIdMap") or {}
            external_id = mapping.get("ALIEXPRESS") or mapping.get("aliexpress") or claim_data.get("collectBoxDetailId") or external_id
        return {"external_id": str(external_id), "request_id": result.get("request_id"), "response": {"create": result.get("response", {}), "claim": claim_response.get("response", {}) if claim_response else None}}

    def publish_product(self, shop_id: str | int, detail_id: str | int, mode: str = "FULL") -> dict[str, Any]:
        """Submit a created collection-box item to the selected TEMU shop.

        The publish API accepts the shop and collection-box detail IDs as arrays,
        even when publishing one item. Keep this separate from create_draft so
        callers can persist the create response before submitting publication.
        """
        if not str(shop_id).strip():
            raise MiaoshouError("妙手发布失败：缺少店铺 ID")
        if not str(detail_id).strip():
            raise MiaoshouError("妙手发布失败：缺少采集箱详情 ID")
        try:
            shop_value = int(str(shop_id))
            detail_value = int(str(detail_id))
        except ValueError as exc:
            raise MiaoshouError("妙手发布失败：店铺 ID 或采集箱详情 ID 不是数字") from exc
        mode_key = "SEMI" if str(mode).upper() in {"SEMI", "HALF", "半托管", "PDDKJCHOICE"} else "FULL"
        return self._retry_transition(self.TEMU_PATHS[mode_key]["publish"], {"shopIds": [shop_value], "detailIds": [detail_value]})

    def claim_product(self, shop_id: str | int, detail_id: str | int, mode: str = "FULL") -> dict[str, Any]:
        try:
            shop_value, detail_value = int(str(shop_id)), int(str(detail_id))
        except ValueError as exc:
            raise MiaoshouError("妙手认领失败：店铺 ID 或采集箱详情 ID 不是数字") from exc
        mode_key = "SEMI" if str(mode).upper() in {"SEMI", "HALF", "半托管", "PDDKJCHOICE"} else "FULL"
        return self._retry_transition(self.TEMU_PATHS[mode_key]["claim"], {"shopIds": [shop_value], "detailIds": [detail_value]})

    def search_collect_box(
        self, detail_id: str | int, mode: str = "FULL", status: str | None = None
    ) -> dict[str, Any]:
        """Find a detail ID in Miaoshou's authoritative status buckets.

        ``sourceItemIdKeyword`` is a source-product ID, not a collection-box
        detail ID.  Filtering with it made every verification return an empty
        list and allowed accepted publish tasks to be mistaken for publication.
        """
        try:
            detail_value = int(str(detail_id))
        except ValueError as exc:
            raise MiaoshouError("妙手查询失败：采集箱详情 ID 不是数字") from exc
        mode_key = "SEMI" if str(mode).upper() in {"SEMI", "HALF", "半托管", "PDDKJCHOICE"} else "FULL"
        filters: dict[str, Any] = {}
        if status:
            filters["status"] = status
        result = self.request(self.TEMU_PATHS[mode_key]["search"], {
            "pageNo": 0,
            "pageSize": 500,
            "filter": filters,
        })
        data = result.get("data") or {}
        rows = data.get("detailList") or data.get("list") or data.get("records") or []
        result["matched"] = next(
            (
                row
                for row in rows
                if str(row.get("collectBoxDetailId") or row.get("detailId") or "") == str(detail_value)
            ),
            None,
        )
        return result

    def wait_for_claim(
        self, shop_id: str | int, detail_id: str | int, cid: str | int, mode: str = "FULL",
        *, attempts: int = 12, interval: float = 2.0,
    ) -> dict[str, Any]:
        """Wait until the selected shop copy can actually be read."""
        last: MiaoshouError | None = None
        for attempt in range(attempts):
            try:
                result = self.get_shop_collect_item_info(shop_id, detail_id, cid, mode)
                data = result.get("data") or {}
                info = data.get("shopCollectItemInfo") or data.get("item") or data
                if info and str(info.get("detailId") or info.get("collectBoxDetailId") or detail_id) == str(detail_id):
                    return result
            except MiaoshouError as exc:
                last = exc
            if attempt < attempts - 1:
                time.sleep(interval)
        raise MiaoshouError(f"妙手认领尚未完成，未提交发布任务：{last or '店铺商品数据暂不可读'}")

    def wait_for_publish(
        self, detail_id: str | int, mode: str = "FULL", *, attempts: int = 3, interval: float = 2.0
    ) -> dict[str, Any]:
        """Verify publication from the published collection-box bucket."""
        last_state = "unknown"
        last_response: dict[str, Any] = {}
        last_error: MiaoshouError | None = None
        for attempt in range(attempts):
            try:
                published = self.search_collect_box(detail_id, mode, "published")
                last_response = published
                if published.get("matched"):
                    return {
                        "state": "published",
                        "verified": True,
                        "checked_at": datetime.now(timezone.utc).isoformat(),
                        **published,
                    }
                if interval:
                    time.sleep(interval)
                not_published = self.search_collect_box(detail_id, mode, "notPublished")
                last_response = not_published
                if not_published.get("matched"):
                    last_state = "notPublished"
                else:
                    if interval:
                        time.sleep(interval)
                    timed = self.search_collect_box(detail_id, mode, "timingPublish")
                    last_response = timed
                    if timed.get("matched"):
                        last_state = "timingPublish"
            except MiaoshouError as exc:
                last_error = exc
                retryable = any(
                    marker in str(exc).casefold()
                    for marker in ("timeout", "超时", "qps", "ratelimit", "频率", "限流", "gateway")
                )
                if not retryable:
                    raise
            if attempt < attempts - 1:
                time.sleep(interval)
        result = {
            "state": last_state,
            "verified": False,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            **last_response,
        }
        if last_error:
            result["error"] = str(last_error)
        return result

    def get_shop_collect_item_info(self, shop_id: str | int, detail_id: str | int, cid: str | int = 0, mode: str = "FULL") -> dict[str, Any]:
        """Read the claimed shop copy; this is also used to verify claim completion."""
        try:
            shop_value, detail_value, cid_value = int(str(shop_id)), int(str(detail_id)), int(str(cid or 0))
        except ValueError as exc:
            raise MiaoshouError("妙手查询失败：店铺、采集箱详情或类目 ID 不是数字") from exc
        mode_key = "SEMI" if str(mode).upper() in {"SEMI", "HALF", "半托管", "PDDKJCHOICE"} else "FULL"
        return self.request(self.TEMU_PATHS[mode_key]["shop_info"], {"detailId": detail_value, "shopId": shop_value, "cid": cid_value})

    def ensure_shop_item_number(
        self, shop_id: str | int, detail_id: str | int, cid: str | int, item_number: str, mode: str = "FULL", sku_stocks: dict[str, int] | None = None
    ) -> dict[str, Any]:
        """Backfill the SPU on older claimed drafts before publishing them."""
        number = str(item_number or "").strip()
        if not number:
            raise MiaoshouError("妙手发布失败：商品货号为空")
        current = self.get_shop_collect_item_info(shop_id, detail_id, cid, mode)
        data = current.get("data") or {}
        info = data.get("shopCollectItemInfo") or {}
        if not info:
            raise MiaoshouError("妙手发布失败：无法读取已认领的店铺商品详情")
        if str(info.get("itemNum") or "").strip() == number:
            changed = False
            for attribute in info.get("saleAttributes") or []:
                for value in attribute.get("values") or []:
                    sku_number = str(value.get("name") or "").strip()
                    if sku_number and not value.get("itemNum"):
                        value["itemNum"] = sku_number
                        changed = True
            for sku_key, sku in (info.get("skuMap") or {}).items():
                item = str(sku.get("itemNum") or sku_key).strip(";")
                if sku_stocks and item in sku_stocks and sku.get("stock") != int(sku_stocks[item]):
                    sku["stock"] = int(sku_stocks[item])
                    changed = True
            if not changed:
                return {"updated": False, "response": current.get("response", {})}
        try:
            shop_value, detail_value = int(str(shop_id)), int(str(detail_id))
        except ValueError as exc:
            raise MiaoshouError("妙手发布失败：店铺 ID 或采集箱详情 ID 不是数字") from exc
        info.update({"detailId": detail_value, "cid": str(cid), "shopId": shop_value, "itemNum": number})
        for attribute in info.get("saleAttributes") or []:
            for value in attribute.get("values") or []:
                sku_number = str(value.get("name") or "").strip()
                if sku_number:
                    value["itemNum"] = sku_number
        for sku_key, sku in (info.get("skuMap") or {}).items():
            item = str(sku.get("itemNum") or sku_key).strip(";")
            if sku_stocks and item in sku_stocks:
                sku["stock"] = int(sku_stocks[item])
        mode_key = "SEMI" if str(mode).upper() in {"SEMI", "HALF", "半托管", "PDDKJCHOICE"} else "FULL"
        save_path = self.TEMU_PATHS[mode_key]["shop_info"].replace(
            "get_shop_collect_item_info", "save_shop_collect_item_info"
        )
        saved = self._retry_transition(
            save_path,
            {"shopCollectItemInfo": info, "detailId": detail_value, "shopId": shop_value},
        )
        return {"updated": True, **saved}

    def _retry_transition(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        last: MiaoshouError | None = None
        for attempt in range(3):
            try:
                return self.request(path, payload)
            except MiaoshouError as exc:
                last = exc
                retryable = any(
                    marker in str(exc).casefold()
                    for marker in ("timeout", "超时", "qps", "ratelimit", "频率", "限流", "gateway")
                )
                if not retryable:
                    raise
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        raise last or MiaoshouError("妙手状态变更失败")


def configured_miaoshou() -> MiaoshouProvider:
    return MiaoshouProvider()
