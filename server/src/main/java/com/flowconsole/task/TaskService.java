package com.flowconsole.task;

import static com.flowconsole.mapper.CatalogMapper.Table.*;

import com.flowconsole.*;
import com.flowconsole.mapper.*;
import com.flowconsole.platform.PlatformGateway;
import com.flowconsole.product.CatalogService;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TaskService {
  private final CatalogMapper db;
  private final TaskMapper tasks;
  private final CatalogService catalog;
  private final PlatformGateway platform;

  public TaskService(
      CatalogMapper db, TaskMapper tasks, CatalogService catalog, PlatformGateway platform) {
    this.db = db;
    this.tasks = tasks;
    this.catalog = catalog;
    this.platform = platform;
  }

  public static List<Long> ids(Map<String, Object> p, String field) {
    if (!(p.get(field) instanceof List<?> values) || values.isEmpty() || values.size() > 200)
      throw ApiException.invalid(field, "选择1至200项");
    try {
      return values.stream().map(Json::id).distinct().sorted().toList();
    } catch (Exception e) {
      throw ApiException.invalid(field, "ID格式错误");
    }
  }

  @Transactional
  public Map<String, Object> create(Map<String, Object> p, long user) {
    String action = Json.text(p, "targetAction");
    if (!Set.of("CREATE_DRAFT", "PUBLISH").contains(action))
      throw ApiException.invalid("targetAction", "目标必须是创建草稿或发布");
    String requestKey = Json.text(p, "requestKey");
    if (!requestKey.matches("[a-zA-Z0-9_.:-]{8,100}"))
      throw ApiException.invalid("requestKey", "请求键需8至100个字母、数字或 ._:-");
    var products = ids(p, "productIds");
    var stores = ids(p, "storeIds");
    if (products.size() * stores.size() > 500)
      throw ApiException.invalid("productIds", "单批最多500个商品×店铺任务");
    var versions = new LinkedHashMap<String, Object>();
    for (long id : products)
      versions.put(Long.toString(id), catalog.lock(id).get("content_version"));
    String batchHash =
        Json.hash(
            Map.of("products", products, "stores", stores, "versions", versions, "action", action));
    var prior = tasks.batchRequest(requestKey);
    if (prior != null) {
      if (!batchHash.equals(prior.get("request_hash")))
        throw new ApiException(409, "REQUEST_KEY_CONFLICT", "同一请求键不能携带不同商品、店铺、版本或动作");
      var previous = tasks.batch(Json.id(prior.get("batch_id")));
      return Map.of(
          "id",
          prior.get("batch_id"),
          "taskIds",
          previous.stream().map(t -> t.get("id")).toList(),
          "total_tasks",
          previous.size());
    }
    var batch =
        new LinkedHashMap<String, Object>(
            Map.of(
                "created_by",
                user,
                "target_action",
                action,
                "total_tasks",
                products.size() * stores.size()));
    db.insert(publish_batch, batch);
    long batchId = Json.id(batch.get("id"));
    tasks.rememberBatch(requestKey, batchHash, batchId);
    var result = new ArrayList<Map<String, Object>>();
    for (long productId : products) {
      var product = catalog.lock(productId);
      long version = Json.id(product.get("content_version"));
      for (long storeId : stores) {
        var store = catalog.require(CatalogMapper.Table.store, storeId);
        var parameters =
            Map.of("product", productId, "store", storeId, "version", version, "action", action);
        String hash = Json.hash(parameters);
        String key =
            products.size() * stores.size() == 1
                ? requestKey
                : requestKey + ":" + productId + ":" + storeId;
        var known = tasks.request(key);
        if (known != null) {
          if (!hash.equals(known.get("request_hash")))
            throw new ApiException(409, "REQUEST_KEY_CONFLICT", "同一请求键不能携带不同参数");
          tasks.attach(batchId, Json.id(known.get("id")));
          result.add(known);
          continue;
        }
        var existing = tasks.target(productId, storeId, version, action);
        if (existing != null) {
          tasks.remember(key, hash, Json.id(existing.get("id")));
          tasks.attach(batchId, Json.id(existing.get("id")));
          result.add(existing);
          continue;
        }
        if (!"APPROVED".equals(catalog.reviewState(productId).get("status")))
          throw new ApiException(409, "REVIEW_REQUIRED", "请先由审核人员批准当前版本");
        if (tasks.uncertain(productId, storeId) > 0)
          throw new ApiException(409, "EXTERNAL_RESULT_UNKNOWN", "该商品在此店铺有待核验操作，核清后再创建新版本任务");
        if (tasks.legacyUnverified(productId, storeId) > 0)
          throw new ApiException(
              409, "HISTORICAL_RESULT_UNVERIFIED", "存在尚未核验的历史外部记录，请先核对历史ID，不能直接重复创建线上商品");
        platform.validate(store, action);
        var snapshot = catalog.snapshot(productId);
        snapshot.put("target_store", catalog.decode(store));
        snapshot.put("target_action", action);
        platform.wire(snapshot);
        var task =
            new LinkedHashMap<String, Object>(
                Map.of(
                    "batch_id",
                    batchId,
                    "product_id",
                    productId,
                    "store_id",
                    storeId,
                    "approved_version",
                    version,
                    "target_action",
                    action,
                    "request_key",
                    key,
                    "request_hash",
                    hash,
                    "payload_hash",
                    Json.hash(snapshot),
                    "payload_snapshot",
                    Json.write(snapshot)));
        var counterpart =
            tasks.target(
                productId, storeId, version, action.equals("PUBLISH") ? "CREATE_DRAFT" : "PUBLISH");
        if (counterpart != null
            && counterpart.get("external_id") != null
            && Set.of("DRAFT_CREATED", "SUCCEEDED").contains(counterpart.get("status"))) {
          task.put("external_id", counterpart.get("external_id"));
          task.put("external_status", counterpart.get("external_status"));
          task.put("stage", action.equals("PUBLISH") ? "CLAIM" : "VERIFY");
          if (action.equals("CREATE_DRAFT")) task.put("status", "DRAFT_CREATED");
        }
        db.insert(publish_task, task);
        long id = Json.id(task.get("id"));
        tasks.remember(key, hash, id);
        tasks.attach(batchId, id);
        if (!"DRAFT_CREATED".equals(task.get("status"))) enqueue(id, version);
        result.add(task);
      }
    }
    db.audit(user, "CREATE_PUBLISH_BATCH", batchId, action);
    return Map.of(
        "id",
        batchId,
        "taskIds",
        result.stream().map(t -> t.get("id")).toList(),
        "total_tasks",
        result.size());
  }

  public void enqueue(long id, long version) {
    db.insert(
        outbox_event,
        new LinkedHashMap<>(
            Map.of(
                "event_id",
                UUID.randomUUID().toString(),
                "task_id",
                id,
                "approved_version",
                version)));
  }

  public Map<String, Object> batch(long id) {
    var b = new LinkedHashMap<>(catalog.require(publish_batch, id));
    var rows = tasks.batch(id);
    var counts = new LinkedHashMap<String, Long>();
    for (String k :
        List.of(
            "package_ready",
            "draft_created",
            "published",
            "verifying",
            "failed",
            "skipped",
            "pending")) counts.put(k, 0L);
    for (var t : rows) {
      String s = t.get("status").toString();
      String bucket =
          s.equals("PACKAGE_READY")
              ? "package_ready"
              : s.equals("DRAFT_CREATED")
                  ? "draft_created"
                  : s.equals("SUCCEEDED") && t.get("target_action").equals("PUBLISH")
                      ? "published"
                      : s.equals("VERIFYING")
                          ? "verifying"
                          : Set.of("FAILED", "NEEDS_REVIEW").contains(s)
                              ? "failed"
                              : s.equals("CANCELLED") ? "skipped" : "pending";
      counts.compute(bucket, (k, v) -> v + 1);
    }
    b.put("tasks", rows);
    b.put("counts", counts);
    b.put("denominator", "商品 × 店铺任务数（包含复用任务）");
    return b;
  }

  @Transactional
  public Object manual(long id, String operation, String reason, long user) {
    if (reason == null || reason.isBlank() || reason.length() > 500)
      throw ApiException.invalid("reason", "请输入操作原因，最多500字");
    var t = tasks.lock(id);
    if (t == null) throw new ApiException(404, "NOT_FOUND", "任务不存在");
    String status = t.get("status").toString();
    boolean sent = Boolean.TRUE.equals(t.get("request_started"));
    if (status.equals("RUNNING")) throw new ApiException(409, "BUSY", "任务执行中，请稍后核验");
    var change = new LinkedHashMap<String, Object>(Map.of("id", id, "last_error", reason));
    switch (operation) {
      case "verify" -> {
        if (!sent && t.get("external_id") == null)
          throw new ApiException(409, "NOT_SENT", "任务尚未发送，无需外部核验");
        change.put("status", "VERIFYING");
      }
      case "retry" -> {
        if (sent || !status.equals("FAILED"))
          throw new ApiException(409, "VERIFY_FIRST", "只允许重试确定未发送的失败任务；不确定结果请核验");
        if (!Objects.equals(
                catalog.require(product, Json.id(t.get("product_id"))).get("content_version"),
                t.get("approved_version"))
            || !"APPROVED".equals(catalog.reviewState(Json.id(t.get("product_id"))).get("status")))
          throw new ApiException(409, "REVIEW_REQUIRED", "当前内容需要重新审核，旧版本只可核验");
        change.put("status", "RETRY_WAIT");
        change.put("attempt", 0);
      }
      case "cancel" -> {
        if (Boolean.TRUE.equals(t.get("external_started"))
            || !Set.of("PENDING", "RETRY_WAIT", "NEEDS_REVIEW", "FAILED").contains(status))
          throw new ApiException(409, "CANNOT_CANCEL", "外部操作已开始，先核验结果");
        change.put("status", "CANCELLED");
      }
      default -> throw new ApiException(400, "BAD_OPERATION", "操作无效");
    }
    change.put("next_run_at", new java.sql.Timestamp(System.currentTimeMillis()));
    db.update(publish_task, change);
    if (!operation.equals("cancel")) enqueue(id, Json.id(t.get("approved_version")));
    db.audit(user, "TASK_" + operation.toUpperCase(Locale.ROOT), id, reason);
    return db.one(publish_task, id);
  }

  @Transactional
  public Object attachExternalId(long id, String externalId, String reason, long user) {
    if (reason == null || reason.isBlank() || reason.length() > 500)
      throw ApiException.invalid("reason", "请填写人工核查来源与原因，最多500字");
    if (externalId == null || !externalId.matches("[a-zA-Z0-9_-]{1,160}"))
      throw ApiException.invalid("externalId", "外部ID格式无效");
    var task = tasks.lock(id);
    if (task == null) throw new ApiException(404, "NOT_FOUND", "任务不存在");
    if (!task.get("status").equals("NEEDS_REVIEW")
        || !Boolean.TRUE.equals(task.get("external_started"))
        || task.get("external_id") != null)
      throw new ApiException(409, "CANNOT_ATTACH_ID", "只可为已发送且缺少外部ID的待处理任务补充核查ID");
    db.update(
        publish_task,
        new LinkedHashMap<>(
            Map.of(
                "id",
                id,
                "external_id",
                externalId,
                "status",
                "VERIFYING",
                "attempt",
                0,
                "next_run_at",
                new java.sql.Timestamp(System.currentTimeMillis()),
                "last_error",
                reason)));
    enqueue(id, Json.id(task.get("approved_version")));
    db.audit(user, "ATTACH_EXTERNAL_ID", id, externalId + ": " + reason);
    return db.one(publish_task, id);
  }
}
