package com.flowconsole.task;

import static com.flowconsole.mapper.CatalogMapper.Table.*;

import com.flowconsole.*;
import com.flowconsole.mapper.*;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ScheduleService {
  private final CatalogMapper db;
  private final TaskService tasks;
  private final TransactionTemplate tx;

  public ScheduleService(CatalogMapper db, TaskService tasks, TransactionTemplate tx) {
    this.db = db;
    this.tasks = tasks;
    this.tx = tx;
  }

  public Object save(Long id, Map<String, Object> p, long user) {
    var row =
        id == null
            ? new LinkedHashMap<String, Object>()
            : new LinkedHashMap<>(db.one(automation_schedule, id));
    if (id != null && row.isEmpty()) throw new ApiException(404, "NOT_FOUND", "计划不存在");
    for (String k : List.of("name", "run_time", "timezone", "target_action", "active"))
      if (p.containsKey(k)) row.put(k, p.get(k));
    if (Json.text(row, "name").isBlank() || Json.text(row, "name").length() > 120)
      throw ApiException.invalid("name", "计划名称必填且最多120字");
    try {
      LocalTime.parse(Json.text(row, "run_time"), DateTimeFormatter.ofPattern("HH:mm"));
      ZoneId.of(Json.text(row, "timezone"));
    } catch (Exception e) {
      throw ApiException.invalid("run_time", "请输入有效时间和IANA时区");
    }
    if (!Set.of("CREATE_DRAFT", "PUBLISH").contains(row.get("target_action")))
      throw ApiException.invalid("target_action", "操作无效");
    for (String field : List.of("product_ids", "store_ids"))
      if (p.containsKey(field)) row.put(field + "_json", Json.write(TaskService.ids(p, field)));
    if (id == null) {
      row.put("created_by", user);
      row.put("active", false);
      db.insert(automation_schedule, row);
    } else db.update(automation_schedule, row);
    db.audit(user, "SAVE_SCHEDULE", Json.id(row.get("id")), Json.text(row, "name"));
    return row;
  }

  public void scan() {
    for (var row : db.all(automation_schedule)) {
      if (!Boolean.TRUE.equals(row.get("active"))) continue;
      var owner = db.one(app_user, Json.id(row.get("created_by")));
      if (owner == null
          || !Boolean.TRUE.equals(owner.get("active"))
          || !Set.of("ADMIN", "OPERATOR").contains(owner.get("role"))) continue;
      var now = ZonedDateTime.now(ZoneId.of(row.get("timezone").toString()));
      String day = now.toLocalDate().toString();
      if (Objects.equals(row.get("last_run_date"), day)
          || now.toLocalTime().isBefore(LocalTime.parse(row.get("run_time").toString()))) continue;
      try {
        tx.executeWithoutResult(
            s -> {
              // Claim a date in the same transaction that creates its durable batch.
              var claim =
                  new LinkedHashMap<String, Object>(
                      Map.of("id", row.get("id"), "last_run_date", day));
              if (db.claimSchedule(Json.id(row.get("id")), day) != 1) return;
              tasks.create(
                  Map.of(
                      "productIds",
                      Json.list(row.get("product_ids_json")),
                      "storeIds",
                      Json.list(row.get("store_ids_json")),
                      "targetAction",
                      row.get("target_action"),
                      "requestKey",
                      "schedule:" + row.get("id") + ":" + day),
                  Json.id(row.get("created_by")));
            });
      } catch (ApiException e) {
        db.audit(
            Json.id(row.get("created_by")), "SCHEDULE_BLOCKED", Json.id(row.get("id")), e.code);
      }
    }
  }
}
