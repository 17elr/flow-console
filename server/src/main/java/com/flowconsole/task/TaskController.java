package com.flowconsole.task;

import com.flowconsole.*;
import com.flowconsole.auth.*;
import com.flowconsole.mapper.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
public class TaskController {
  private final TaskService service;
  private final TaskMapper tasks;
  private final CatalogMapper db;
  private final AuthService auth;

  public TaskController(TaskService service, TaskMapper tasks, CatalogMapper db, AuthService auth) {
    this.service = service;
    this.tasks = tasks;
    this.db = db;
    this.auth = auth;
  }

  @PostMapping("/api/publish-batches")
  ResponseEntity<?> create(@RequestBody Map<String, Object> p, HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN", "OPERATOR");
    return ResponseEntity.accepted().body(service.create(p, AuthFilter.userId(r)));
  }

  @GetMapping("/api/publish-batches")
  Object batches() {
    return db.all(CatalogMapper.Table.publish_batch);
  }

  @GetMapping("/api/publish-batches/{id}")
  Object batch(@PathVariable long id) {
    return service.batch(id);
  }

  @GetMapping({"/api/publish-tasks", "/api/automation/runs"})
  Object tasks() {
    return tasks.recent();
  }

  @GetMapping("/api/publish-tasks/{id}/attempts")
  Object attempts(@PathVariable long id) {
    return db.children(CatalogMapper.Table.publish_attempt, "task_id", id);
  }

  @PostMapping("/api/publish-tasks/{id}/resolve")
  Object resolve(@PathVariable long id, @RequestBody Map<String, Object> p, HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN", "REVIEWER");
    return service.attachExternalId(
        id, Json.text(p, "externalId"), Json.text(p, "reason"), AuthFilter.userId(r));
  }

  @PostMapping("/api/publish-tasks/{id}/{operation:verify|retry|cancel}")
  Object manual(
      @PathVariable long id,
      @PathVariable String operation,
      @RequestBody Map<String, Object> p,
      HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN", "REVIEWER");
    return service.manual(id, operation, Json.text(p, "reason"), AuthFilter.userId(r));
  }
}
