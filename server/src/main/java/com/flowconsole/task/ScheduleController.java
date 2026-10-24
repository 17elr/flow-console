package com.flowconsole.task;

import com.flowconsole.auth.*;
import com.flowconsole.mapper.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.web.bind.annotation.*;

@RestController
public class ScheduleController {
  private final ScheduleService schedules;
  private final CatalogMapper db;
  private final AuthService auth;

  public ScheduleController(ScheduleService schedules, CatalogMapper db, AuthService auth) {
    this.schedules = schedules;
    this.db = db;
    this.auth = auth;
  }

  @GetMapping("/api/automation/schedules")
  Object list() {
    return db.all(CatalogMapper.Table.automation_schedule);
  }

  @PostMapping("/api/automation/schedules")
  Object create(@RequestBody Map<String, Object> p, HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN");
    return schedules.save(null, p, AuthFilter.userId(r));
  }

  @PatchMapping("/api/automation/schedules/{id}")
  Object update(@PathVariable long id, @RequestBody Map<String, Object> p, HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN");
    return schedules.save(id, p, AuthFilter.userId(r));
  }
}
