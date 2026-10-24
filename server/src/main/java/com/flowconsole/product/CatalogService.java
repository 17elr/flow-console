package com.flowconsole.product;

import static com.flowconsole.mapper.CatalogMapper.Table.*;

import com.flowconsole.*;
import com.flowconsole.mapper.CatalogMapper;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CatalogService {
  public static final List<String> MAIN_ROLES =
      List.of(
          "SPU_WHITE_MAIN",
          "SPU_DETAIL_1",
          "SPU_DETAIL_2",
          "SPU_SIZE_INFO",
          "SCENE_MODEL_WEAR",
          "SCENE_LIFESTYLE");
  private static final Set<String> PRODUCT_FIELDS =
      Set.of(
          "spu_code",
          "title",
          "category",
          "material",
          "color",
          "dimensions",
          "weight_g",
          "cost",
          "price",
          "currency",
          "stock",
          "image_rights",
          "source_image_url",
          "import_parameters_json",
          "platform",
          "platform_payload",
          "packaging_asset_id",
          "packaging_preset_id",
          "target_store_ids",
          "scene_profile");
  private static final Set<String> SKU_FIELDS =
      Set.of(
          "sku_code",
          "name",
          "color",
          "size",
          "material",
          "quantity",
          "price",
          "stock",
          "is_sellable",
          "source_image_url");
  private final CatalogMapper db;

  public CatalogService(CatalogMapper db) {
    this.db = db;
  }

  public Map<String, Object> require(CatalogMapper.Table table, long id) {
    var row = db.one(table, id);
    if (row == null || Boolean.TRUE.equals(row.get("deleted")))
      throw new ApiException(404, "NOT_FOUND", "记录不存在");
    return row;
  }

  public Map<String, Object> decode(Map<String, Object> row) {
    var result = Json.map(row.get("content_json"));
    result.putAll(row);
    result.remove("content_json");
    return result;
  }

  public List<Map<String, Object>> products(String q, String state) {
    return db.products().stream()
        .map(this::summary)
        .filter(
            p ->
                q == null
                    || (p.get("spu_code") + " " + p.get("title"))
                        .toLowerCase(Locale.ROOT)
                        .contains(q.toLowerCase(Locale.ROOT)))
        .filter(p -> state == null || state.isBlank() || state.equals(p.get("status")))
        .toList();
  }

  public Map<String, Object> summary(Map<String, Object> row) {
    var p = decode(row);
    long id = Json.id(p.get("id"));
    var skus = db.children(sku, "product_id", id);
    p.put("sku_count", skus.size());
    p.put("review", reviewState(id));
    p.put("status", ((Map<?, ?>) p.get("review")).get("status"));
    return p;
  }

  public Map<String, Object> detail(long id) {
    var p = summary(require(product, id));
    p.put(
        "skus",
        db.children(sku, "product_id", id).stream()
            .map(
                s -> {
                  var v = decode(s);
                  v.put(
                      "components",
                      db.children(component, "sku_id", Json.id(s.get("id"))).stream()
                          .map(this::decode)
                          .toList());
                  return v;
                })
            .toList());
    p.put("assets", db.children(asset, "product_id", id));
    p.put("listing_copies", db.children(listing_copy, "product_id", id));
    p.put("reviews", db.children(review, "product_id", id));
    p.put("legacy_results", db.children(legacy_external, "product_id", id));
    return p;
  }

  public Map<String, Object> reviewState(long id) {
    var p = require(product, id);
    var r = db.lastReview(id);
    String status = "NEEDS_REVIEW";
    if (r != null
        && Json.id(r.get("approved_version")) == Json.id(p.get("content_version"))
        && Objects.equals(r.get("fingerprint"), fingerprint(id)))
      status = r.get("decision").toString();
    var state = new LinkedHashMap<String, Object>();
    state.put("status", status);
    state.put("content_version", p.get("content_version"));
    state.put("latest", r);
    return state;
  }

  public Map<String, Object> snapshot(long id) {
    var p = decode(require(product, id));
    for (String k : List.of("updated_at", "created_at", "updated_by", "deleted")) p.remove(k);
    p.put(
        "skus",
        db.children(sku, "product_id", id).stream()
            .map(
                s -> {
                  var v = decode(s);
                  v.put(
                      "components",
                      db.children(component, "sku_id", Json.id(s.get("id"))).stream()
                          .map(this::decode)
                          .toList());
                  return v;
                })
            .toList());
    p.put(
        "assets",
        db.children(asset, "product_id", id).stream()
            .map(
                a ->
                    Map.of(
                        "id",
                        a.get("id"),
                        "role",
                        a.get("role"),
                        "sha256",
                        a.get("sha256"),
                        "storage_key",
                        a.get("storage_key"),
                        "version",
                        a.get("version"),
                        "sku_id",
                        a.get("sku_id") == null ? 0 : a.get("sku_id")))
            .toList());
    p.put("copies", db.children(listing_copy, "product_id", id));
    p.put("stores", db.all(store).stream().map(this::decode).toList());
    return p;
  }

  public String fingerprint(long id) {
    return Json.hash(snapshot(id));
  }

  public static BigDecimal money(Object raw, String field, boolean required) {
    if (raw == null || raw.toString().isBlank()) {
      if (required) throw ApiException.invalid(field, "价格不能为空");
      return null;
    }
    try {
      BigDecimal v = new BigDecimal(raw.toString());
      if (v.signum() < 0 || v.scale() > 8 || v.precision() - v.scale() > 16)
        throw new NumberFormatException();
      return v;
    } catch (NumberFormatException e) {
      throw ApiException.invalid(field, "金额需非负数，最多8位小数和16位整数，不自动取整");
    }
  }

  public static int integer(Object raw, String field, int min) {
    try {
      int n = new BigDecimal(Objects.toString(raw, "")).intValueExact();
      if (n < min) throw new ArithmeticException();
      return n;
    } catch (Exception e) {
      throw ApiException.invalid(field, "必须是大于等于" + min + "的整数");
    }
  }

  private static void required(Map<String, Object> p, String field, int max) {
    String value = Json.text(p, field);
    if (value.isBlank() || value.length() > max)
      throw ApiException.invalid(field, "此项必填，最多" + max + "字符");
  }

  private Map<String, Object> selected(Map<String, Object> p, Set<String> fields) {
    var out = new LinkedHashMap<String, Object>();
    for (String k : fields) if (p.containsKey(k)) out.put(k, p.get(k));
    return out;
  }

  @Transactional
  public Map<String, Object> save(Long id, Map<String, Object> input, long user) {
    Json.rejectCredentials(input);
    var content = id == null ? new LinkedHashMap<String, Object>() : decode(lock(id));
    PRODUCT_FIELDS.forEach(
        k -> {
          if (input.containsKey(k)) content.put(k, input.get(k));
        });
    required(content, "spu_code", 80);
    required(content, "title", 255);
    if (!Json.text(content, "weight_g").isBlank()) {
      var weight = money(content.get("weight_g"), "weight_g", true);
      if (weight.signum() <= 0) throw ApiException.invalid("weight_g", "真实重量需大于0");
      content.put("weight_g", weight);
    }
    content.putIfAbsent("currency", "USD");
    if (!Json.text(content, "currency").matches("[A-Z]{3}"))
      throw ApiException.invalid("currency", "请输入三位大写币种代码");
    var row = new LinkedHashMap<String, Object>();
    for (String k : List.of("spu_code", "title", "category", "currency"))
      row.put(k, Objects.toString(content.get(k), ""));
    row.put("price", money(content.get("price"), "price", false));
    row.put("cost", money(content.get("cost"), "cost", false));
    row.put("stock", integer(content.getOrDefault("stock", 0), "stock", 0));
    row.put("content_json", Json.write(selected(content, PRODUCT_FIELDS)));
    row.put("updated_by", user);
    if (id == null) {
      db.insert(product, row);
      id = Json.id(row.get("id"));
    } else {
      row.put("id", id);
      row.put("content_version", Json.id(content.get("content_version")) + 1);
      db.update(product, row);
      db.invalidate(id);
    }
    if (input.get("skus") instanceof List<?> values)
      for (Object value : values) {
        if (!(value instanceof Map<?, ?>)) throw ApiException.invalid("skus", "SKU格式无效");
        @SuppressWarnings("unchecked")
        Map<String, Object> s = (Map<String, Object>) value;
        saveSkuInternal(id, s);
      }
    db.audit(user, "SAVE_PRODUCT", id, "");
    return detail(id);
  }

  public Map<String, Object> lock(long id) {
    var row = db.lockProduct(id);
    if (row == null || Boolean.TRUE.equals(row.get("deleted")))
      throw new ApiException(404, "NOT_FOUND", "商品不存在");
    return row;
  }

  public void bump(long id, long user) {
    var p = lock(id);
    db.update(
        product,
        new LinkedHashMap<>(
            Map.of(
                "id",
                id,
                "content_version",
                Json.id(p.get("content_version")) + 1,
                "updated_by",
                user)));
    db.invalidate(id);
  }

  @Transactional
  public Map<String, Object> saveSku(long id, Map<String, Object> input, long user) {
    var s = require(sku, id);
    long productId = Json.id(s.get("product_id"));
    lock(productId);
    var merged = decode(s);
    merged.putAll(selected(input, SKU_FIELDS));
    saveSkuInternal(productId, merged);
    bump(productId, user);
    return decode(require(sku, id));
  }

  private void saveSkuInternal(long productId, Map<String, Object> input) {
    required(input, "sku_code", 100);
    var previous = db.bySku(Json.text(input, "sku_code"));
    if (previous != null && Json.id(previous.get("product_id")) != productId)
      throw ApiException.invalid("sku_code", "SKU已属于其他SPU，不能变更归属");
    var row = new LinkedHashMap<String, Object>();
    row.put("product_id", productId);
    row.put("sku_code", Json.text(input, "sku_code"));
    row.put("price", money(input.get("price"), "price", true));
    row.put("stock", integer(input.get("stock"), "stock", 0));
    row.put("quantity", integer(input.get("quantity"), "quantity", 1));
    row.put("content_json", Json.write(selected(input, SKU_FIELDS)));
    if (previous == null) db.insert(sku, row);
    else {
      row.put("id", previous.get("id"));
      db.update(sku, row);
    }
  }

  @Transactional
  public Object component(long skuId, Map<String, Object> input, long user) {
    var s = require(sku, skuId);
    long productId = Json.id(s.get("product_id"));
    lock(productId);
    required(input, "component_code", 100);
    required(input, "component_name", 255);
    var row =
        new LinkedHashMap<String, Object>(
            Map.of(
                "sku_id",
                skuId,
                "component_code",
                Json.text(input, "component_code"),
                "component_name",
                Json.text(input, "component_name"),
                "quantity",
                integer(input.get("quantity"), "quantity", 1),
                "content_json",
                Json.write(input)));
    db.insert(component, row);
    bump(productId, user);
    return decode(row);
  }

  @Transactional
  public void deleteComponent(long id, long user) {
    var c = require(component, id);
    var s = require(sku, Json.id(c.get("sku_id")));
    long pid = Json.id(s.get("product_id"));
    lock(pid);
    db.deleteComponent(id);
    bump(pid, user);
  }

  @Transactional
  public void remove(long id, long user) {
    bump(id, user);
    db.update(product, new LinkedHashMap<>(Map.of("id", id, "deleted", true)));
    db.audit(user, "ARCHIVE_PRODUCT", id, "");
  }

  public List<String> blockers(long id) {
    var p = decode(require(product, id));
    var errors = new ArrayList<String>();
    for (String k : List.of("material", "dimensions", "weight_g"))
      if (Json.text(p, k).isBlank()) errors.add("缺少真实资料：" + k);
    if (!Set.of("OWNED", "AUTHORIZED").contains(Json.text(p, "image_rights")))
      errors.add("未确认图片使用权");
    var latest = new LinkedHashMap<String, Map<String, Object>>();
    for (var item : db.children(asset, "product_id", id))
      if (Set.of("FINISHED", "GENERATED").contains(item.get("source")))
        latest.put(item.get("role") + ":" + Objects.toString(item.get("sku_id"), ""), item);
    var all = new ArrayList<>(latest.values());
    for (var item : all) {
      var imageReview = Json.map(item.get("metadata_json")).get("review");
      if (imageReview instanceof Map<?, ?> state && "REJECTED".equals(state.get("decision")))
        errors.add("图片审核拒绝：" + item.get("role") + " #" + item.get("id"));
    }
    for (String role : MAIN_ROLES)
      if (all.stream().noneMatch(a -> role.equals(a.get("role")))) errors.add("缺少成品图：" + role);
    var variants = db.children(sku, "product_id", id);
    if (variants.isEmpty()) errors.add("缺少SKU");
    for (var s : variants) {
      var facts = decode(s);
      if (Json.text(facts, "size").isBlank() && Json.text(p, "dimensions").isBlank())
        errors.add("SKU缺少规格：" + s.get("sku_code"));
      if (all.stream()
          .noneMatch(
              a ->
                  "SKU_IMAGE".equals(a.get("role"))
                      && Objects.equals(a.get("sku_id"), s.get("id"))))
        errors.add("SKU缺少独立成品图：" + s.get("sku_code"));
      if (s.get("price") == null || new BigDecimal(s.get("price").toString()).signum() <= 0)
        errors.add("SKU价格需大于0：" + s.get("sku_code"));
    }
    var copies = db.children(listing_copy, "product_id", id);
    if (copies.isEmpty()) errors.add("缺少平台文案");
    for (var c : copies)
      if ((c.get("title") + " " + c.get("description")).matches("(?s).*[\\p{IsHan}].*"))
        errors.add(c.get("platform") + "文案包含中文，请人工编辑英文");
    return errors;
  }

  @Transactional
  public Object decide(long id, Map<String, Object> payload, long user) {
    var p = lock(id);
    String decision = Json.text(payload, "decision");
    if (!Set.of("APPROVED", "REJECTED").contains(decision))
      throw ApiException.invalid("decision", "选择批准或拒绝");
    if (payload.get("content_version") == null
        || Json.id(payload.get("content_version")) != Json.id(p.get("content_version")))
      throw new ApiException(409, "STALE_VERSION", "商品已修改，请重新打开审核");
    if (decision.equals("APPROVED")) {
      if (Objects.equals(p.get("updated_by"), user))
        throw new ApiException(403, "SELF_REVIEW", "请由另一名审核人员审核");
      var blockers = blockers(id);
      if (!blockers.isEmpty())
        throw new ApiException(
            422,
            "NOT_READY",
            String.join("；", blockers),
            Map.of("readiness", String.join("；", blockers)));
    }
    var row =
        new LinkedHashMap<String, Object>(
            Map.of(
                "product_id",
                id,
                "approved_version",
                p.get("content_version"),
                "fingerprint",
                fingerprint(id),
                "reviewer_id",
                user,
                "decision",
                decision,
                "note",
                Json.text(payload, "note")));
    db.insert(review, row);
    db.audit(user, "REVIEW_" + decision, id, Json.text(payload, "note"));
    if (decision.equals("REJECTED")) db.invalidate(id);
    return reviewState(id);
  }

  @Transactional
  public Object copy(long productId, Map<String, Object> input, long user) {
    var p = decode(lock(productId));
    String platform = Json.text(input, "platform");
    if (!Set.of("TEMU", "ALIEXPRESS").contains(platform))
      throw ApiException.invalid("platform", "平台无效");
    var existing =
        db.children(listing_copy, "product_id", productId).stream()
            .filter(c -> c.get("platform").equals(platform))
            .findFirst()
            .orElse(null);
    var row = new LinkedHashMap<String, Object>();
    row.put("product_id", productId);
    row.put("platform", platform);
    row.put("title", input.getOrDefault("title", p.get("title")));
    row.put(
        "description",
        input.getOrDefault(
            "description",
            "Material: "
                + Json.text(p, "material")
                + ". Dimensions: "
                + Json.text(p, "dimensions")
                + ". Item: "
                + p.get("spu_code")
                + "."));
    row.put(
        "bullet_points_json",
        input.get("bullet_points") instanceof List<?> list ? Json.write(list) : "[]");
    if (Json.text(row, "title").isBlank()) throw ApiException.invalid("title", "文案标题不能为空");
    if (existing == null) db.insert(listing_copy, row);
    else {
      row.put("id", existing.get("id"));
      db.update(listing_copy, row);
    }
    bump(productId, user);
    db.audit(user, "SAVE_COPY", productId, platform);
    return row;
  }

  @Transactional
  public Object saveStore(Long id, Map<String, Object> input, long user) {
    Json.rejectCredentials(input);
    var content = id == null ? new LinkedHashMap<String, Object>() : decode(require(store, id));
    content.putAll(input);
    required(content, "name", 120);
    required(content, "account_key", 160);
    if (!Set.of("TEMU", "ALIEXPRESS").contains(Json.text(content, "platform")))
      throw ApiException.invalid("platform", "平台无效");
    if (!Set.of("SEMI", "FULL", "ALIEXPRESS").contains(Json.text(content, "mode")))
      throw ApiException.invalid("mode", "店铺模式无效");
    if (Json.text(content, "platform").equals("ALIEXPRESS")
        != Json.text(content, "mode").equals("ALIEXPRESS"))
      throw ApiException.invalid("mode", "店铺模式与平台不匹配");
    var row = new LinkedHashMap<String, Object>();
    for (String k :
        List.of("name", "platform", "mode", "currency", "external_shop_id", "account_key"))
      row.put(k, content.getOrDefault(k, k.equals("currency") ? "USD" : ""));
    row.put("active", content.getOrDefault("active", true));
    row.put("content_json", Json.write(content));
    if (id == null) db.insert(store, row);
    else {
      row.put("id", id);
      row.put("config_version", Json.id(content.get("config_version")) + 1);
      db.update(store, row);
    }
    for (var p : db.products()) bump(Json.id(p.get("id")), user);
    db.audit(user, "SAVE_STORE", Json.id(row.get("id")), Json.text(content, "name"));
    return row;
  }
}
