package com.flowconsole.asset;

import com.flowconsole.auth.*;
import com.flowconsole.mapper.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.web.bind.annotation.*;

@RestController
public class ImageOperationController {
  private final ImageOperations operations;
  private final AuthService auth;
  private final CatalogMapper db;

  public ImageOperationController(ImageOperations operations, AuthService auth, CatalogMapper db) {
    this.operations = operations;
    this.auth = auth;
    this.db = db;
  }

  @GetMapping("/api/image-provider/status")
  Object status() {
    return operations.status();
  }

  @PostMapping("/api/assets/{id}/operations/{jobId}")
  Object execute(
      @PathVariable long id,
      @PathVariable String jobId,
      @RequestBody Map<String, Object> p,
      HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN", "OPERATOR");
    return operations.execute(id, jobId, p, AuthFilter.userId(r));
  }

  @GetMapping("/api/image-operations")
  Object history() {
    return db.all(CatalogMapper.Table.image_operation);
  }
}
