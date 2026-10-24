package com.flowconsole.task;

import static com.flowconsole.mapper.CatalogMapper.Table.*;

import com.flowconsole.*;
import com.flowconsole.mapper.*;
import com.flowconsole.platform.PlatformGateway;
import com.flowconsole.product.CatalogService;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class TaskExecutor {
  private final TaskMapper tasks;
  private final CatalogMapper db;
  private final CatalogService catalog;
  private final TaskService service;
  private final PlatformGateway platform;
  private final TransactionTemplate tx;

  public TaskExecutor(
      TaskMapper tasks,
      CatalogMapper db,
      CatalogService catalog,
      TaskService service,
      PlatformGateway platform,
      TransactionTemplate tx) {
    this.tasks = tasks;
    this.db = db;
    this.catalog = catalog;
    this.service = service;
    this.platform = platform;
    this.tx = tx;
  }

  public void execute(long id, long approvedVersion) {
    String owner = UUID.randomUUID().toString();
    var initial = db.one(publish_task, id);
    if (initial == null) return;
    Map<String, Object> task =
        tx.execute(
            s -> {
              var product = catalog.lock(Json.id(initial.get("product_id")));
              var current = tasks.lock(id);
              if (current == null || Json.id(current.get("approved_version")) != approvedVersion)
                return null;
              if (!Set.of("PENDING", "RETRY_WAIT", "VERIFYING").contains(current.get("status")))
                return null;
              boolean verification = current.get("status").equals("VERIFYING");
              if (!verification && !Boolean.TRUE.equals(current.get("external_started"))) {
                if (Json.id(product.get("content_version")) != approvedVersion
                    || !"APPROVED"
                        .equals(catalog.reviewState(Json.id(product.get("id"))).get("status"))) {
                  db.update(
                      publish_task,
                      new LinkedHashMap<>(
                          Map.of("id", id, "status", "NEEDS_REVIEW", "last_error", "批准版本已失效")));
                  return null;
                }
              }
              return tasks.claim(id, owner) == 1 ? current : null;
            });
    if (task == null) return;
    boolean verify = "VERIFYING".equals(task.get("status"));
    long started = System.currentTimeMillis();
    var attempt =
        new LinkedHashMap<String, Object>(
            Map.of("task_id", id, "stage", verify ? "VERIFY" : task.get("stage")));
    db.insert(publish_attempt, attempt);
    PlatformGateway.Result result;
    try {
      result =
          platform.execute(
              task,
              verify,
              () ->
                  tx.executeWithoutResult(
                      s -> {
                        var product = catalog.lock(Json.id(task.get("product_id")));
                        if (!Boolean.TRUE.equals(task.get("external_started"))
                            && (Json.id(product.get("content_version")) != approvedVersion
                                || !"APPROVED"
                                    .equals(
                                        catalog
                                            .reviewState(Json.id(product.get("id")))
                                            .get("status"))))
                          throw new ApiException(409, "STALE_VERSION", "批准版本已失效，未发送外部请求");
                        if (tasks.sent(id, owner) != 1)
                          throw new ApiException(409, "LEASE_LOST", "任务租约已失效");
                      }));
    } catch (Exception e) {
      finish(task, owner, null, verify, e, attempt, started);
      return;
    }
    finish(task, owner, result, verify, null, attempt, started);
  }

  private void finish(
      Map<String, Object> task,
      String owner,
      PlatformGateway.Result result,
      boolean verify,
      Exception failure,
      Map<String, Object> attempt,
      long started) {
    tx.executeWithoutResult(
        s -> {
          long id = Json.id(task.get("id"));
          String stage = task.get("stage").toString();
          String external = Objects.toString(task.get("external_id"), null),
              externalStatus = Objects.toString(task.get("external_status"), null);
          String status;
          boolean sent = false;
          int number = ((Number) task.get("attempt")).intValue(), delay = 0;
          String error = null;
          if (failure == null) {
            external = result.externalId();
            externalStatus = result.externalStatus();
            if (verify) {
              if (externalStatus.equals("PUBLISHED")) status = "SUCCEEDED";
              else if (externalStatus.equals("DRAFT")
                  && task.get("target_action").equals("CREATE_DRAFT")) status = "DRAFT_CREATED";
              else {
                number++;
                status = number <= 3 ? "VERIFYING" : "NEEDS_REVIEW";
                sent = true;
                delay = 30;
                error = "尚未找到权威目标状态，请核查外部ID";
              }
            } else if (stage.equals("CREATE")) {
              if (task.get("target_action").equals("CREATE_DRAFT")) status = "DRAFT_CREATED";
              else {
                status = "RETRY_WAIT";
                stage = "CLAIM";
              }
            } else if (stage.equals("CLAIM")) {
              status = "RETRY_WAIT";
              stage = "CLAIM_VERIFY";
              delay = 5;
            } else if (stage.equals("CLAIM_VERIFY")) {
              status = "RETRY_WAIT";
              stage = "SAVE_STOCK";
            } else if (stage.equals("SAVE_STOCK")) {
              status = "RETRY_WAIT";
              stage = "PUBLISH";
            } else {
              status = "VERIFYING";
              stage = "VERIFY";
              sent = true;
              delay = 5;
            }
          } else {
            number++;
            error =
                failure.getMessage() == null
                    ? failure.getClass().getSimpleName()
                    : failure.getMessage();
            error = error.substring(0, Math.min(900, error.length()));
            boolean unknown = failure instanceof PlatformGateway.Failure f && f.unknown;
            boolean temporary =
                failure instanceof PlatformGateway.Failure f && f.retryable
                    || failure instanceof ApiException a && a.status == 503;
            if (verify || unknown) {
              status = number <= 3 ? "VERIFYING" : "NEEDS_REVIEW";
              sent = true;
              delay = number <= 3 ? new int[] {5, 30, 120}[number - 1] : 0;
            } else if (temporary) {
              status = number <= 3 ? "RETRY_WAIT" : "FAILED";
              delay = number <= 3 ? new int[] {5, 30, 120}[number - 1] : 0;
            } else status = "NEEDS_REVIEW";
          }
          var evidence = new LinkedHashMap<String, Object>();
          evidence.put("id", attempt.get("id"));
          evidence.put("finished_at", new java.sql.Timestamp(System.currentTimeMillis()));
          evidence.put(
              "http_code",
              result != null
                  ? result.httpCode()
                  : failure instanceof PlatformGateway.Failure f ? f.httpCode : 0);
          evidence.put(
              "response_json",
              Json.write(
                  result != null
                      ? result.evidence()
                      : Map.of(
                          "error",
                          error == null ? "" : error,
                          "duration_ms",
                          System.currentTimeMillis() - started)));
          evidence.put("error", error);
          db.update(publish_attempt, evidence);
          if (tasks.finish(
                  id, owner, status, stage, external, externalStatus, number, delay, sent, error)
              == 1) {
            if (failure != null
                && task.get("stage").equals("CREATE")
                && failure instanceof PlatformGateway.Failure f
                && !f.unknown)
              db.update(
                  publish_task, new LinkedHashMap<>(Map.of("id", id, "external_started", false)));
            if (failure == null && task.get("stage").equals("CLAIM_VERIFY"))
              db.update(
                  publish_task,
                  new LinkedHashMap<>(
                      Map.of("id", id, "stage_context", Json.write(result.evidence()))));
            if (Set.of("RETRY_WAIT", "VERIFYING").contains(status))
              service.enqueue(id, Json.id(task.get("approved_version")));
          }
        });
  }
}
