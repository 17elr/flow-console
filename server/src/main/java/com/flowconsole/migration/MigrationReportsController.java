package com.flowconsole.migration;

import com.flowconsole.auth.*;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

@RestController
public class MigrationReportsController {
  private final JdbcTemplate jdbc;
  private final AuthService auth;

  public MigrationReportsController(JdbcTemplate jdbc, AuthService auth) {
    this.jdbc = jdbc;
    this.auth = auth;
  }

  @GetMapping("/api/migration/reports")
  Object reports(HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN");
    return jdbc.queryForList("SELECT * FROM migration_run ORDER BY imported_at DESC");
  }
}
