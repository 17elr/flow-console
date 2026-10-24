package com.flowconsole.product;

import static com.flowconsole.mapper.CatalogMapper.Table.*;

import com.flowconsole.*;
import com.flowconsole.auth.*;
import com.flowconsole.mapper.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

@RestController
public class CatalogController {
  private final CatalogService catalog;
  private final CatalogMapper db;
  private final AuthService auth;
  private final JdbcTemplate jdbc;

  public CatalogController(
      CatalogService catalog, CatalogMapper db, AuthService auth, JdbcTemplate jdbc) {
    this.catalog = catalog;
    this.db = db;
    this.auth = auth;
    this.jdbc = jdbc;
  }

  @GetMapping("/health")
  Object health() {
    return Map.of("status", "UP", "version", "2.0.0", "externalCalls", false);
  }

  @GetMapping("/api/readiness")
  Object readiness() {
    jdbc.queryForObject("SELECT 1", Integer.class);
    return Map.of("database", "UP", "externalPlatforms", "NOT_PROBED");
  }

  @GetMapping("/api/overview")
  Object overview() {
    return Map.of(
        "products",
        db.products().size(),
        "skus",
        jdbc.queryForObject("SELECT COUNT(*) FROM sku", Long.class),
        "stores",
        db.all(store).size(),
        "task_counts",
        jdbc.queryForList(
            "SELECT status,target_action,COUNT(*) AS count FROM publish_task GROUP BY"
                + " status,target_action"));
  }

  @GetMapping("/api/products")
  Object products(
      @RequestParam(required = false) String q, @RequestParam(required = false) String status) {
    return catalog.products(q, status);
  }

  @GetMapping("/api/products/{id}")
  Object detail(@PathVariable long id) {
    return catalog.detail(id);
  }

  @PostMapping({"/api/products", "/api/simple-products"})
  Object create(@RequestBody Map<String, Object> p, HttpServletRequest r) {
    edit(r);
    return catalog.save(null, p, AuthFilter.userId(r));
  }

  @PatchMapping("/api/products/{id}")
  Object update(@PathVariable long id, @RequestBody Map<String, Object> p, HttpServletRequest r) {
    edit(r);
    return catalog.save(id, p, AuthFilter.userId(r));
  }

  @DeleteMapping("/api/products/{id}")
  @ResponseStatus(org.springframework.http.HttpStatus.NO_CONTENT)
  void remove(@PathVariable long id, HttpServletRequest r) {
    edit(r);
    catalog.remove(id, AuthFilter.userId(r));
  }

  @PatchMapping("/api/skus/{id}")
  Object sku(@PathVariable long id, @RequestBody Map<String, Object> p, HttpServletRequest r) {
    edit(r);
    return catalog.saveSku(id, p, AuthFilter.userId(r));
  }

  @PostMapping("/api/skus/{id}/components")
  Object addComponent(
      @PathVariable long id, @RequestBody Map<String, Object> p, HttpServletRequest r) {
    edit(r);
    return catalog.component(id, p, AuthFilter.userId(r));
  }

  @DeleteMapping("/api/components/{id}")
  @ResponseStatus(org.springframework.http.HttpStatus.NO_CONTENT)
  void deleteComponent(@PathVariable long id, HttpServletRequest r) {
    edit(r);
    catalog.deleteComponent(id, AuthFilter.userId(r));
  }

  @GetMapping("/api/products/{id}/workflow")
  Object workflow(@PathVariable long id) {
    return Map.of(
        "product",
        catalog.detail(id),
        "review",
        catalog.reviewState(id),
        "blockers",
        catalog.blockers(id));
  }

  @GetMapping("/api/products/{id}/image-readiness")
  Object readiness(@PathVariable long id) {
    return Map.of("missing", catalog.blockers(id));
  }

  @PutMapping("/api/products/{id}/review")
  Object review(@PathVariable long id, @RequestBody Map<String, Object> p, HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "REVIEWER", "ADMIN");
    return catalog.decide(id, p, AuthFilter.userId(r));
  }

  @PostMapping("/api/products/{id}/listing-copies")
  Object copy(@PathVariable long id, @RequestBody Map<String, Object> p, HttpServletRequest r) {
    edit(r);
    return catalog.copy(id, p, AuthFilter.userId(r));
  }

  @PutMapping("/api/listing-copies/{id}")
  Object updateCopy(
      @PathVariable long id, @RequestBody Map<String, Object> p, HttpServletRequest r) {
    edit(r);
    var old = catalog.require(listing_copy, id);
    var merged = new LinkedHashMap<>(p);
    merged.put("platform", old.get("platform"));
    return catalog.copy(Json.id(old.get("product_id")), merged, AuthFilter.userId(r));
  }

  @GetMapping("/api/stores")
  Object stores() {
    return db.all(store).stream().map(catalog::decode).toList();
  }

  @PostMapping("/api/stores")
  Object createStore(@RequestBody Map<String, Object> p, HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN");
    return catalog.saveStore(null, p, AuthFilter.userId(r));
  }

  @PutMapping({"/api/stores/{id}", "/api/automation/stores/{id}"})
  Object updateStore(
      @PathVariable long id, @RequestBody Map<String, Object> p, HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN");
    return catalog.saveStore(id, p, AuthFilter.userId(r));
  }

  @DeleteMapping("/api/stores/{id}")
  Object disableStore(@PathVariable long id, HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN");
    return catalog.saveStore(id, Map.of("active", false), AuthFilter.userId(r));
  }

  @GetMapping("/api/audit")
  Object audit(HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN", "REVIEWER");
    return db.all(audit);
  }

  private void edit(HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN", "OPERATOR");
  }
}
