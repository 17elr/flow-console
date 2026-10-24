package com.flowconsole.asset;

import static com.flowconsole.mapper.CatalogMapper.Table.*;

import com.flowconsole.*;
import com.flowconsole.auth.*;
import com.flowconsole.mapper.*;
import com.flowconsole.product.CatalogService;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.http.*;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
public class AssetController {
  private final AssetService files;
  private final CatalogService catalog;
  private final CatalogMapper db;
  private final AuthService auth;

  public AssetController(
      AssetService files, CatalogService catalog, CatalogMapper db, AuthService auth) {
    this.files = files;
    this.catalog = catalog;
    this.db = db;
    this.auth = auth;
  }

  @PostMapping("/api/source-assets")
  Object upload(
      @RequestParam long product_id,
      @RequestParam(required = false) Long sku_id,
      @RequestParam String role,
      @RequestParam(defaultValue = "SOURCE") String source,
      @RequestParam MultipartFile file,
      HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN", "OPERATOR");
    return files.upload(product_id, sku_id, role, source, file, AuthFilter.userId(r));
  }

  @PutMapping("/api/generated-assets/{id}")
  Object replace(@PathVariable long id, @RequestParam MultipartFile file, HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN", "OPERATOR");
    var old = catalog.require(asset, id);
    return files.upload(
        Json.id(old.get("product_id")),
        old.get("sku_id") == null ? null : Json.id(old.get("sku_id")),
        old.get("role").toString(),
        "FINISHED",
        file,
        AuthFilter.userId(r));
  }

  @GetMapping({"/api/assets/{id}/content", "/api/compliance-files/{id}/content"})
  ResponseEntity<byte[]> content(@PathVariable long id) {
    var a = catalog.require(asset, id);
    catalog.require(product, Json.id(a.get("product_id")));
    return ResponseEntity.ok()
        .contentType(MediaType.parseMediaType(a.get("mime_type").toString()))
        .header("Content-Security-Policy", "sandbox")
        .header(
            "Content-Disposition",
            ContentDisposition.attachment()
                .filename("asset-" + id + (a.get("mime_type").equals("image/png") ? ".png" : ""))
                .build()
                .toString())
        .body(files.read(a));
  }

  @PostMapping("/api/assets/{id}/transform")
  Object transform(
      @PathVariable long id, @RequestBody Map<String, Object> p, HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN", "OPERATOR");
    return files.transform(id, p, AuthFilter.userId(r));
  }

  @GetMapping("/api/assets/{id}/original")
  ResponseEntity<byte[]> original(@PathVariable long id) {
    var row = catalog.require(asset, id);
    catalog.require(product, Json.id(row.get("product_id")));
    var metadata = Json.map(row.get("metadata_json"));
    if (!metadata.containsKey("original_storage_key"))
      throw new ApiException(409, "NO_SEPARATE_ORIGINAL", "历史素材没有独立原始字节副本，请下载保留的素材文件");
    var original =
        Map.<String, Object>of(
            "storage_key",
            metadata.get("original_storage_key"),
            "sha256",
            metadata.get("original_sha256"));
    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .header(
            "Content-Disposition",
            ContentDisposition.attachment()
                .filename(
                    Objects.toString(row.get("original_filename"), "original.bin"),
                    java.nio.charset.StandardCharsets.UTF_8)
                .build()
                .toString())
        .body(files.read(original));
  }

  @PutMapping("/api/reviews/images/{id}")
  @Transactional
  Object review(@PathVariable long id, @RequestBody Map<String, Object> p, HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN", "REVIEWER");
    var a = catalog.require(asset, id);
    catalog.lock(Json.id(a.get("product_id")));
    String decision = Json.text(p, "decision");
    if (!Set.of("APPROVED", "REJECTED").contains(decision))
      throw ApiException.invalid("decision", "审核状态无效");
    var metadata = Json.map(a.get("metadata_json"));
    metadata.put(
        "review",
        Map.of(
            "decision",
            decision,
            "reviewer_id",
            AuthFilter.userId(r),
            "note",
            Json.text(p, "note"),
            "at",
            java.time.Instant.now().toString()));
    db.update(asset, new LinkedHashMap<>(Map.of("id", id, "metadata_json", Json.write(metadata))));
    long productId = Json.id(a.get("product_id"));
    var product = catalog.require(CatalogMapper.Table.product, productId);
    var version =
        new LinkedHashMap<String, Object>(
            Map.of(
                "id", productId, "content_version", Json.id(product.get("content_version")) + 1));
    db.update(CatalogMapper.Table.product, version);
    db.invalidate(productId);
    db.audit(AuthFilter.userId(r), "IMAGE_REVIEW", id, decision);
    return metadata;
  }

  @GetMapping("/api/products/{id}/compliance")
  Object compliance(@PathVariable long id) {
    catalog.require(product, id);
    return db.children(asset, "product_id", id).stream()
        .filter(a -> a.get("source").equals("COMPLIANCE"))
        .toList();
  }

  @GetMapping("/api/compliance-library")
  Object library() {
    return db.all(asset).stream().filter(a -> a.get("source").equals("COMPLIANCE")).toList();
  }

  @GetMapping("/api/packaging-presets")
  Object packaging() {
    return files.presets();
  }

  @PutMapping("/api/packaging-presets/{slot}")
  Object preset(@PathVariable int slot, @RequestParam MultipartFile file, HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN", "OPERATOR");
    return files.savePreset(slot, file, AuthFilter.userId(r));
  }

  @GetMapping("/api/packaging-presets/{slot}/content")
  ResponseEntity<byte[]> presetContent(@PathVariable int slot) {
    var preset = files.preset(slot);
    return ResponseEntity.ok()
        .contentType(MediaType.parseMediaType(preset.get("mime_type").toString()))
        .body(files.read(preset));
  }

  @DeleteMapping("/api/packaging-presets/{slot}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  void deactivatePreset(@PathVariable int slot, HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN", "OPERATOR");
    var row = files.preset(slot);
    db.update(packaging_preset, new LinkedHashMap<>(Map.of("id", row.get("id"), "active", false)));
    db.audit(AuthFilter.userId(r), "DEACTIVATE_PACKAGING_PRESET", Json.id(row.get("id")), "");
  }

  @PutMapping("/api/products/{id}/packaging-selection")
  Object selectPackaging(
      @PathVariable long id, @RequestBody Map<String, Object> p, HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN", "OPERATOR");
    if (p.get("preset_id") == null) throw ApiException.invalid("preset_id", "请选择已有包装素材");
    var original = catalog.require(packaging_preset, Json.id(p.get("preset_id")));
    if (!Boolean.TRUE.equals(original.get("active")))
      throw ApiException.invalid("preset_id", "预设已停用");
    var saved =
        files.save(
            id,
            null,
            "PACKAGING",
            "PACKAGING",
            "packaging.png",
            files.read(original),
            Map.of("reused_from", original.get("id")),
            AuthFilter.userId(r));
    return catalog.save(
        id,
        Map.of("packaging_asset_id", saved.get("id"), "packaging_preset_id", original.get("id")),
        AuthFilter.userId(r));
  }

  @PostMapping("/api/products/{id}/compliance")
  Object uploadDocument(
      @PathVariable long id,
      @RequestParam String kind,
      @RequestParam MultipartFile file,
      HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN", "OPERATOR");
    return files.upload(id, null, kind, "COMPLIANCE", file, AuthFilter.userId(r));
  }

  @PostMapping("/api/products/{id}/compliance/{assetId}/reuse")
  Object reuse(@PathVariable long id, @PathVariable long assetId, HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN", "OPERATOR");
    var a = catalog.require(asset, assetId);
    if (!a.get("source").equals("COMPLIANCE")) throw ApiException.invalid("assetId", "请选择合规文件");
    return files.save(
        id,
        null,
        a.get("role").toString(),
        "COMPLIANCE",
        a.get("original_filename").toString(),
        files.read(a),
        Map.of("reused_from", assetId),
        AuthFilter.userId(r));
  }
}
