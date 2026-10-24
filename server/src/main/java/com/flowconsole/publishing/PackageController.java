package com.flowconsole.publishing;

import com.flowconsole.*;
import com.flowconsole.asset.AssetService;
import com.flowconsole.auth.*;
import com.flowconsole.mapper.*;
import com.flowconsole.product.CatalogService;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
public class PackageController {
  private final PackageService service;
  private final CatalogMapper db;
  private final CatalogService catalog;
  private final AssetService assets;
  private final AuthService auth;

  public PackageController(
      PackageService service,
      CatalogMapper db,
      CatalogService catalog,
      AssetService assets,
      AuthService auth) {
    this.service = service;
    this.db = db;
    this.catalog = catalog;
    this.assets = assets;
    this.auth = auth;
  }

  @PostMapping("/api/products/{id}/aliexpress-import-package")
  Object create(@PathVariable long id, @RequestBody Map<String, Object> p, HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN", "OPERATOR");
    if (p.get("store_id") == null) throw ApiException.invalid("store_id", "请先选择AliExpress店铺");
    return service.create(id, Json.id(p.get("store_id")), AuthFilter.userId(r));
  }

  @GetMapping("/api/local-packages")
  Object list() {
    return db.all(CatalogMapper.Table.local_package);
  }

  @GetMapping("/api/local-packages/{id}/content")
  ResponseEntity<byte[]> download(@PathVariable long id) {
    var p = catalog.require(CatalogMapper.Table.local_package, id);
    return ResponseEntity.ok()
        .contentType(MediaType.parseMediaType("application/zip"))
        .header("Content-Disposition", "attachment; filename=aliexpress-package-" + id + ".zip")
        .body(assets.read(p));
  }
}
