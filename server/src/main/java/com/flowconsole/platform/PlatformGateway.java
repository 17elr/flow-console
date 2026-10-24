package com.flowconsole.platform;

import com.flowconsole.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.util.*;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class PlatformGateway {
  public record Result(
      String externalId, String externalStatus, Map<String, Object> evidence, int httpCode) {}

  public static class Failure extends RuntimeException {
    public final boolean unknown, retryable;
    public final int httpCode;

    public Failure(String message, boolean unknown, boolean retryable, int code) {
      super(message);
      this.unknown = unknown;
      this.retryable = retryable;
      this.httpCode = code;
    }
  }

  private final Environment env;
  private final AccountLimiter limiter;
  private final HttpClient client =
      HttpClient.newBuilder()
          .connectTimeout(Duration.ofSeconds(10))
          .followRedirects(HttpClient.Redirect.NEVER)
          .build();

  public PlatformGateway(Environment env, AccountLimiter limiter) {
    this.env = env;
    this.limiter = limiter;
  }

  private String config(String name) {
    return env.getProperty("flow." + name, "");
  }

  public Map<String, Object> status() {
    return Map.of(
        "enabled",
        env.getProperty("flow.real-publishing", Boolean.class, false),
        "configured",
        !config("app-key").isBlank() && !config("app-secret").isBlank(),
        "aliexpress_draft_configured",
        !config("aliexpress-create-path").isBlank(),
        "aliexpress_publish_supported",
        false);
  }

  public void validate(Map<String, Object> store, String action) {
    if (!Boolean.TRUE.equals(store.get("active")) || Json.text(store, "external_shop_id").isBlank())
      throw new ApiException(409, "STORE_NOT_READY", "店铺未启用或缺少真实授权ID");
    if (!env.getProperty("flow.real-publishing", Boolean.class, false))
      throw new ApiException(409, "PUBLISHING_DISABLED", "外部平台操作默认关闭，请在获授权后配置服务端环境");
    if (config("app-key").isBlank() || config("app-secret").isBlank())
      throw new ApiException(409, "PLATFORM_NOT_CONFIGURED", "平台密钥未配置");
    if ("ALIEXPRESS".equals(store.get("platform"))) {
      if (action.equals("PUBLISH"))
        throw new ApiException(409, "UNSUPPORTED_ACTION", "速卖通支持本地包和独立在线草稿，不支持自动发布");
      if (config("aliexpress-create-path").isBlank())
        throw new ApiException(409, "CONTRACT_MISSING", "速卖通在线草稿契约未配置，可单独生成本地导入包");
    } else if (!"TEMU".equals(store.get("platform")))
      throw new ApiException(409, "UNSUPPORTED_PLATFORM", "平台不支持");
  }

  @SuppressWarnings("unchecked")
  public Map<String, Object> wire(Map<String, Object> snapshot) {
    var store = (Map<String, Object>) snapshot.get("target_store");
    var supplied =
        snapshot.get("platform_payload") instanceof Map<?, ?> m
            ? new LinkedHashMap<>((Map<String, Object>) m)
            : new LinkedHashMap<String, Object>();
    String platform = Json.text(store, "platform");
    if (supplied.isEmpty())
      throw new ApiException(
          409, "PAYLOAD_CONTRACT_REQUIRED", "请在商品平台参数中填写经核对的 platform_payload；系统不会猜测类目、属性ID和包装数据");
    supplied.put("itemNum", snapshot.get("spu_code"));
    var copies = (List<Map<String, Object>>) snapshot.get("copies");
    var copy =
        copies.stream()
            .filter(c -> platform.equals(c.get("platform")))
            .findFirst()
            .orElseThrow(() -> new ApiException(409, "COPY_REQUIRED", "缺少当前平台文案"));
    supplied.put("title", copy.get("title"));
    supplied.put("notesText", copy.get("description"));
    if (platform.equals("TEMU") && Json.text(supplied, "cid").isBlank())
      throw new ApiException(409, "CATEGORY_REQUIRED", "TEMU末级类目ID缺失");
    if (!(supplied.get("imgUrls") instanceof List<?> images)
        || images.size() != 6
        || images.stream().anyMatch(u -> !u.toString().startsWith("https://")))
      throw new ApiException(409, "PUBLIC_IMAGES_REQUIRED", "平台参数需包含按顺序排列的6张真实HTTPS成品图地址");
    if (!(supplied.get("skuMap") instanceof Map<?, ?> skuMap) || skuMap.isEmpty())
      throw new ApiException(409, "SKU_CONTRACT_REQUIRED", "平台参数缺少经核对的skuMap");
    return platform.equals("TEMU") ? Map.of("siteCollectItemInfo", supplied) : supplied;
  }

  @SuppressWarnings("unchecked")
  public Result execute(Map<String, Object> task, boolean verify, Runnable beforeSend) {
    var snapshot = Json.map(task.get("payload_snapshot"));
    var store = (Map<String, Object>) snapshot.get("target_store");
    validate(store, task.get("target_action").toString());
    String platform = Json.text(store, "platform"),
        mode = Json.text(store, "mode"),
        stage = Json.text(task, "stage"),
        external = Json.text(task, "external_id");
    String base =
        "/open/v1/product/collect_box/" + (mode.equals("SEMI") ? "pddkj" : "pddkj_choice");
    String path;
    Map<String, Object> payload;
    if (verify) {
      if (external.isBlank()) throw new Failure("外部创建结果未知且缺少可查询ID，请人工核查，禁止自动重建", false, false, 0);
      if (platform.equals("ALIEXPRESS")) {
        path = config("aliexpress-query-path");
        if (path.isBlank()) throw new Failure("速卖通查询契约未配置，请人工核查外部ID", false, false, 0);
        payload = Map.of("collectBoxDetailId", external, "shopId", store.get("external_shop_id"));
      } else {
        path = base + "/collect_box/search_collect_box_detail_list";
        payload =
            Map.of(
                "pageNo",
                0,
                "pageSize",
                500,
                "filter",
                Map.of(
                    "status",
                    task.get("target_action").equals("PUBLISH") ? "published" : "notPublished"));
      }
    } else if (stage.equals("CREATE")) {
      path =
          platform.equals("ALIEXPRESS")
              ? config("aliexpress-create-path")
              : base + "/collect_box/create_collect_box_item";
      payload = wire(snapshot);
    } else if (stage.equals("CLAIM_VERIFY")) {
      path = base + "/collect_box/get_shop_collect_item_info";
      var supplied = (Map<String, Object>) snapshot.get("platform_payload");
      payload =
          Map.of(
              "detailId",
              Json.id(external),
              "shopId",
              Json.id(store.get("external_shop_id")),
              "cid",
              supplied.get("cid"));
    } else if (stage.equals("SAVE_STOCK")) {
      path = base + "/collect_box/save_shop_collect_item_info";
      var context = Json.map(task.get("stage_context"));
      var previous =
          context.get("data") instanceof Map<?, ?> m
              ? (Map<String, Object>) m
              : Map.<String, Object>of();
      var info =
          previous.get("shopCollectItemInfo") instanceof Map<?, ?> m
              ? new LinkedHashMap<>((Map<String, Object>) m)
              : new LinkedHashMap<>(previous);
      if (info.isEmpty()) throw new Failure("缺少已核验的店铺商品数据，请人工核查", false, false, 0);
      info.put("itemNum", snapshot.get("spu_code"));
      info.put("detailId", Json.id(external));
      info.put("shopId", Json.id(store.get("external_shop_id")));
      var stocks = new HashMap<String, Object>();
      for (var v : (List<Map<String, Object>>) snapshot.get("skus"))
        stocks.put(v.get("sku_code").toString(), v.get("stock"));
      if (!(info.get("skuMap") instanceof Map<?, ?> m))
        throw new Failure("平台SKU数据不可核对，未提交发布", false, false, 0);
      for (var entry : m.entrySet())
        if (entry.getValue() instanceof Map<?, ?> raw) {
          var v = (Map<String, Object>) raw;
          String code =
              Objects.toString(v.get("itemNum"), entry.getKey().toString()).replace(";", "");
          if (!stocks.containsKey(code)) throw new Failure("平台SKU与批准快照不一致，未提交发布", false, false, 0);
          v.put("stock", stocks.get(code));
        }
      payload =
          Map.of(
              "shopCollectItemInfo",
              info,
              "detailId",
              Json.id(external),
              "shopId",
              Json.id(store.get("external_shop_id")));
    } else {
      if (!platform.equals("TEMU")) throw new Failure("跨平台状态错误，已阻止TEMU接口调用", false, false, 0);
      path =
          base
              + (stage.equals("CLAIM")
                  ? "/collect_box/claim_to_shop"
                  : "/move_collect/save_move_collect_task");
      payload =
          Map.of(
              "shopIds",
              List.of(Json.id(store.get("external_shop_id"))),
              "detailIds",
              List.of(Json.id(external)));
    }
    var response = request(path, payload, Json.text(store, "account_key"), beforeSend);
    var data =
        response.get("data") instanceof Map<?, ?> m
            ? (Map<String, Object>) m
            : Map.<String, Object>of();
    if (verify) {
      List<?> rows =
          data.get("detailList") instanceof List<?> a
              ? a
              : data.get("list") instanceof List<?> a
                  ? a
                  : data.get("records") instanceof List<?> a ? a : List.of();
      boolean matched =
          rows.stream()
              .filter(Map.class::isInstance)
              .map(Map.class::cast)
              .anyMatch(
                  r ->
                      external.equals(
                          Objects.toString(
                              r.get("collectBoxDetailId"),
                              Objects.toString(r.get("detailId"), ""))));
      String state =
          matched
              ? (task.get("target_action").equals("PUBLISH") ? "PUBLISHED" : "DRAFT")
              : "UNKNOWN";
      return new Result(external, state, redact(response), 200);
    }
    if (stage.equals("CLAIM_VERIFY") && data.isEmpty())
      throw new Failure("店铺认领尚未可读，稍后重试", false, true, 200);
    if (stage.equals("CREATE")) {
      String id =
          Objects.toString(
              data.get("collectBoxDetailId"),
              Objects.toString(data.get("id"), Objects.toString(data.get("itemId"), "")));
      if (id.isBlank()) throw new Failure("平台响应缺少外部ID，结果需要核验", true, false, 200);
      return new Result(id, "DRAFT_CREATED", redact(response), 200);
    }
    return new Result(external, "ACCEPTED", redact(response), 200);
  }

  public Map<String, Object> request(
      String path, Map<String, Object> payload, String account, Runnable beforeSend) {
    if (!path.startsWith("/open/")
        || path.contains("..")
        || path.contains("?")
        || path.contains("#")) throw new ApiException(409, "INVALID_PLATFORM_PATH", "平台契约路径无效");
    String body = Json.write(payload),
        timestamp = Long.toString(Instant.now().getEpochSecond()),
        key = config("app-key"),
        secret = config("app-secret");
    String signature;
    try {
      Mac mac = Mac.getInstance("HmacSHA256");
      mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
      signature =
          HexFormat.of()
              .formatHex(
                  mac.doFinal(
                      (secret + path + timestamp + key + body + secret)
                          .getBytes(StandardCharsets.UTF_8)));
    } catch (Exception e) {
      throw new ApiException(409, "SIGNING_NOT_CONFIGURED", "平台签名未配置");
    }
    boolean readOnly = path.contains("/get_") || path.contains("/search_");
    limiter.acquire(Json.sha(key.getBytes(StandardCharsets.UTF_8)));
    beforeSend.run();
    try {
      var request =
          HttpRequest.newBuilder(URI.create(config("platform-base") + path))
              .timeout(Duration.ofSeconds(30))
              .header("Content-Type", "application/json")
              .header("x-app-key", key)
              .header("x-timestamp", timestamp)
              .header("x-sign", signature)
              .POST(HttpRequest.BodyPublishers.ofString(body))
              .build();
      var response = BoundedHttp.send(client, request, 2 * 1024 * 1024, 30);
      byte[] bytes = response.body();
      int code = response.statusCode();
      if (code == 429) throw new Failure("平台限流，等待重试", false, true, code);
      if (code >= 500) throw new Failure("平台服务错误，外部结果未知", !readOnly, readOnly, code);
      if (code < 200 || code >= 300) throw new Failure("平台拒绝请求，HTTP " + code, false, false, code);
      if (bytes.length > 2 * 1024 * 1024) throw new Failure("响应超限，需要核验外部结果", true, false, code);
      var json = Json.map(new String(bytes, StandardCharsets.UTF_8));
      if ("fail".equals(json.get("result"))
          || (json.get("code") != null
              && !Set.of("success", "0").contains(json.get("code").toString())))
        throw new Failure(
            "平台业务拒绝，代码 "
                + Objects.toString(json.get("code"), "unknown")
                    .replaceAll("[^a-zA-Z0-9_-]", "")
                    .substring(
                        0,
                        Math.min(
                            40,
                            Objects.toString(json.get("code"), "unknown")
                                .replaceAll("[^a-zA-Z0-9_-]", "")
                                .length())),
            false,
            false,
            code);
      return json;
    } catch (Failure e) {
      throw e;
    } catch (Exception e) {
      if (e instanceof InterruptedException) Thread.currentThread().interrupt();
      throw new Failure("平台请求中断或响应不可读，外部结果需要核验", !readOnly, readOnly, 0);
    }
  }

  private Map<String, Object> redact(Map<String, Object> response) {
    var out = new LinkedHashMap<String, Object>();
    response.forEach(
        (k, v) -> {
          if (!k.toLowerCase(Locale.ROOT)
              .matches(
                  ".*(secret|token|password|signature|authorization).*|app_?key|api_?key|x-sign")) {
            if (v instanceof Map<?, ?> m) {
              @SuppressWarnings("unchecked")
              var safe = redact((Map<String, Object>) m);
              out.put(k, safe);
            } else if (v instanceof List<?> values)
              out.put(k, values.stream().map(this::redactValue).toList());
            else if (v instanceof String s) out.put(k, redactValue(s));
            else out.put(k, v);
          }
        });
    return out;
  }

  @SuppressWarnings("unchecked")
  private Object redactValue(Object value) {
    if (value instanceof Map<?, ?> map) return redact((Map<String, Object>) map);
    if (value instanceof List<?> list) return list.stream().map(this::redactValue).toList();
    if (value instanceof String text) {
      for (String secret : List.of(config("app-key"), config("app-secret")))
        if (!secret.isBlank()) text = text.replace(secret, "[redacted]");
      return text;
    }
    return value;
  }
}
