package com.flowconsole.migration;

import static com.flowconsole.mapper.CatalogMapper.Table.*;

import com.flowconsole.*;
import com.flowconsole.asset.AssetService;
import com.flowconsole.mapper.*;
import com.flowconsole.product.CatalogService;
import java.io.*;
import java.math.BigDecimal;
import java.nio.file.*;
import java.util.*;
import javax.sql.DataSource;
import org.flywaydb.core.Flyway;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

@Component
@Profile("migration")
@Order(Ordered.HIGHEST_PRECEDENCE)
public class LegacyImporter implements ApplicationRunner {
  private final JdbcTemplate jdbc;
  private final CatalogMapper db;
  private final AssetService assets;
  private final TransactionTemplate tx;
  private final DataSource source;
  private final String directory;

  public LegacyImporter(
      JdbcTemplate jdbc,
      CatalogMapper db,
      AssetService assets,
      TransactionTemplate tx,
      DataSource source,
      @Value("${flow.migration-path:}") String directory) {
    this.jdbc = jdbc;
    this.db = db;
    this.assets = assets;
    this.tx = tx;
    this.source = source;
    this.directory = directory;
  }

  @Override
  public void run(ApplicationArguments args) throws Exception {
    String database = jdbc.queryForObject("SELECT DATABASE()", String.class);
    if (database == null || !database.matches("flow_(migration|test)_[a-zA-Z0-9_]+"))
      throw new IllegalStateException(
          "Migration accepts only a separate flow_migration_* or flow_test_* database");
    if (directory.isBlank())
      throw new IllegalArgumentException("--flow.migration-path is required");
    var root = Path.of(directory).toAbsolutePath().normalize();
    byte[] manifestBytes = Files.readAllBytes(root.resolve("manifest.json"));
    String hash = Json.sha(manifestBytes);
    var manifest = Json.map(new String(manifestBytes, java.nio.charset.StandardCharsets.UTF_8));
    if (!manifest.get("format").equals("flow-legacy-v1"))
      throw new IllegalArgumentException("Unsupported export format");
    if (!((List<?>) manifest.get("foreign_key_issues")).isEmpty())
      throw new IllegalArgumentException(
          "Source contains foreign key errors; resolve them explicitly before import");
    var tables = new LinkedHashMap<String, List<Map<String, Object>>>();
    @SuppressWarnings("unchecked")
    var inventory = (Map<String, Map<String, Object>>) manifest.get("tables");
    for (var entry : inventory.entrySet()) {
      String name = entry.getKey();
      if (!name.matches("[a-zA-Z0-9_]+")) throw new IllegalArgumentException("Invalid table name");
      var path = root.resolve(name + ".jsonl");
      if (!fileHash(path).equals(entry.getValue().get("sha256")))
        throw new IllegalArgumentException("JSONL hash mismatch: " + name);
      var records = new ArrayList<Map<String, Object>>();
      try (var lines = Files.lines(path)) {
        lines.filter(l -> !l.isBlank()).forEach(l -> records.add(Json.map(l)));
      }
      if (records.size() != Json.id(entry.getValue().get("rows")))
        throw new IllegalArgumentException("Row count mismatch: " + name);
      tables.put(name, records);
    }
    @SuppressWarnings("unchecked")
    var files = (List<Map<String, Object>>) manifest.get("files");
    var copied = new HashMap<String, Map<String, Object>>();
    for (var item : files) {
      String relative = item.get("path").toString();
      Path original = root.resolve("files").resolve(relative).normalize();
      if (!original.startsWith(root.resolve("files"))
          || !original.toRealPath().startsWith(root.resolve("files").toRealPath()))
        throw new IllegalArgumentException("File escapes export root");
      if (!fileHash(original).equals(item.get("sha256")))
        throw new IllegalArgumentException("Asset hash mismatch: " + relative);
      Path target = assets.path("legacy/" + relative);
      Files.createDirectories(target.getParent());
      if (Files.exists(target)) {
        if (!fileHash(target).equals(item.get("sha256")))
          throw new IllegalArgumentException("Refuse to overwrite existing asset: " + relative);
      } else Files.copy(original, target);
      copied.put(relative, item);
    }
    Flyway.configure().dataSource(source).load().migrate();
    var existing =
        jdbc.queryForList("SELECT report_json FROM migration_run WHERE manifest_hash=?", hash);
    if (!existing.isEmpty()) {
      writeReport(root, database, Json.map(existing.get(0).get("report_json")));
      return;
    }
    if (jdbc.queryForObject("SELECT COUNT(*) FROM product", Long.class) > 0
        || jdbc.queryForObject("SELECT COUNT(*) FROM legacy_record", Long.class) > 0)
      throw new IllegalStateException(
          "Target must be a new empty database; original tables are never replaced");
    var unresolved = new ArrayList<String>();
    var recovered = new ArrayList<String>();
    Map<String, Object> finalReport =
        tx.execute(
            s -> {
              for (var table : tables.entrySet())
                for (var row : table.getValue())
                  jdbc.update(
                      "INSERT INTO legacy_record(table_name,original_id,record_json) VALUES(?,?,?)",
                      table.getKey(),
                      Objects.toString(row.get("id"), Json.hash(row)),
                      Json.write(row));
              for (var old : tables.getOrDefault("products", List.of())) {
                var p = new LinkedHashMap<String, Object>();
                for (String k : List.of("id", "spu_code", "title", "category", "currency", "stock"))
                  if (old.get(k) != null) p.put(k, old.get(k));
                p.put("price", CatalogService.money(old.get("price"), "price", false));
                p.put("cost", CatalogService.money(old.get("cost"), "cost", false));
                p.put("content_json", Json.write(old));
                db.insert(product, p);
                mapping("products", old, "product", Json.id(p.get("id")));
              }
              for (var old : tables.getOrDefault("sku_variants", List.of())) {
                var p = new LinkedHashMap<String, Object>();
                for (String k : List.of("id", "product_id", "sku_code", "stock", "quantity"))
                  p.put(k, old.get(k));
                p.put("price", CatalogService.money(old.get("price"), "price", false));
                p.put("content_json", Json.write(old));
                db.insert(sku, p);
                mapping("sku_variants", old, "sku", Json.id(p.get("id")));
              }
              for (var old : tables.getOrDefault("sku_components", List.of())) {
                var p = new LinkedHashMap<String, Object>();
                for (String k : List.of("id", "sku_id", "component_name", "quantity"))
                  p.put(k, old.get(k));
                p.put(
                    "component_code",
                    old.get("component_code") == null
                        ? "legacy-component-" + old.get("id")
                        : old.get("component_code"));
                p.put("content_json", Json.write(old));
                db.insert(component, p);
                mapping("sku_components", old, "component", Json.id(p.get("id")));
              }
              for (var old : tables.getOrDefault("stores", List.of())) {
                var p = new LinkedHashMap<String, Object>();
                for (String k :
                    List.of(
                        "id", "name", "platform", "mode", "currency", "external_shop_id", "active"))
                  p.put(k, old.get(k));
                p.put("account_key", "legacy-shared-account");
                p.put("content_json", Json.write(old));
                db.insert(store, p);
                mapping("stores", old, "store", Json.id(p.get("id")));
              }
              for (String table : List.of("assets", "asset_versions"))
                for (var old : tables.getOrDefault(table, List.of())) {
                  String key = Objects.toString(old.get("storage_key"), "");
                  String relative =
                      ("COMPLIANCE".equals(old.get("asset_type")) ? "compliance/" : "assets/")
                          + key;
                  var file = copied.get(relative);
                  boolean recovery = false;
                  if (file == null && old.get("sha256") != null) {
                    var identical =
                        copied.entrySet().stream()
                            .filter(f -> old.get("sha256").equals(f.getValue().get("sha256")))
                            .findFirst()
                            .orElse(null);
                    if (identical != null) {
                      relative = identical.getKey();
                      file = identical.getValue();
                      recovery = true;
                      recovered.add(table + ":" + old.get("id"));
                    }
                  }
                  if (file == null) {
                    unresolved.add(table + ":" + old.get("id") + ":file_not_available");
                    continue;
                  }
                  if (old.get("sha256") != null && !old.get("sha256").equals(file.get("sha256")))
                    throw new IllegalArgumentException(
                        "Database/file hash mismatch: " + table + ":" + old.get("id"));
                  var p = new LinkedHashMap<String, Object>();
                  for (String k :
                      List.of("product_id", "sku_id", "role", "width", "height", "mime_type"))
                    if (old.get(k) != null) p.put(k, old.get(k));
                  String storedKey = "legacy/" + relative;
                  if (recovery) {
                    storedKey =
                        "legacy-recovered/"
                            + table
                            + "-"
                            + old.get("id")
                            + "/"
                            + Path.of(key).getFileName();
                    try {
                      Path target = assets.path(storedKey);
                      Files.createDirectories(target.getParent());
                      if (!Files.exists(target))
                        Files.copy(assets.path("legacy/" + relative), target);
                      else if (!fileHash(target).equals(file.get("sha256")))
                        throw new IllegalStateException("Recovered copy hash mismatch");
                    } catch (IOException e) {
                      throw new IllegalStateException(e);
                    }
                  }
                  p.put(
                      "source",
                      table.equals("asset_versions")
                          ? "FINISHED"
                          : Objects.toString(old.get("asset_type"), "SOURCE"));
                  p.put("version", old.getOrDefault("version", 1));
                  p.put("storage_key", storedKey);
                  p.put("sha256", file.get("sha256"));
                  p.put("byte_size", file.get("size"));
                  p.put("metadata_json", Json.write(old));
                  p.put("original_filename", Path.of(key).getFileName().toString());
                  if (!p.containsKey("role")) p.put("role", "SOURCE_MAIN");
                  if (!p.containsKey("mime_type")) p.put("mime_type", "application/octet-stream");
                  db.insert(asset, p);
                  mapping(table, old, "asset", Json.id(p.get("id")));
                }
              for (var old : tables.getOrDefault("sku_assets", List.of())) {
                var mapped =
                    jdbc.queryForList(
                        "SELECT target_id FROM legacy_id_map WHERE table_name='asset_versions' AND"
                            + " original_id=?",
                        old.get("asset_version_id").toString());
                if (mapped.isEmpty()) {
                  unresolved.add("sku_assets:" + old.get("id") + ":asset_unavailable");
                  continue;
                }
                long assetId = Json.id(mapped.get(0).get("target_id"));
                var original = db.one(asset, assetId);
                if (original.get("sku_id") != null
                    && !Objects.equals(original.get("sku_id"), old.get("sku_id"))) {
                  var clone = new LinkedHashMap<>(original);
                  clone.remove("id");
                  clone.remove("created_at");
                  String cloneKey =
                      "legacy-bindings/"
                          + old.get("id")
                          + "/"
                          + Path.of(original.get("storage_key").toString()).getFileName();
                  try {
                    Path destination = assets.path(cloneKey);
                    Files.createDirectories(destination.getParent());
                    if (!Files.exists(destination))
                      Files.copy(assets.path(original.get("storage_key").toString()), destination);
                    else if (!fileHash(destination).equals(original.get("sha256")))
                      throw new IllegalStateException("Binding copy hash mismatch");
                  } catch (IOException e) {
                    throw new IllegalStateException(e);
                  }
                  clone.put("storage_key", cloneKey);
                  clone.put("sku_id", old.get("sku_id"));
                  clone.put("role", "SKU_IMAGE");
                  db.insert(asset, clone);
                  assetId = Json.id(clone.get("id"));
                } else
                  db.update(
                      asset,
                      new LinkedHashMap<>(
                          Map.of("id", assetId, "sku_id", old.get("sku_id"), "role", "SKU_IMAGE")));
                mapping("sku_assets", old, "asset", assetId);
              }
              for (var old : tables.getOrDefault("listing_copies", List.of())) {
                var p = new LinkedHashMap<String, Object>();
                for (String k :
                    List.of(
                        "id",
                        "product_id",
                        "platform",
                        "title",
                        "description",
                        "bullet_points_json",
                        "generator")) p.put(k, old.get(k));
                db.insert(listing_copy, p);
                mapping("listing_copies", old, "listing_copy", Json.id(p.get("id")));
              }
              for (var old : tables.getOrDefault("packaging_presets", List.of())) {
                String relative = "assets/" + old.get("storage_key");
                var file = copied.get(relative);
                if (file == null) {
                  unresolved.add("packaging_presets:" + old.get("id") + ":file_not_available");
                  continue;
                }
                var row = new LinkedHashMap<String, Object>();
                for (String key :
                    List.of(
                        "id",
                        "slot",
                        "sha256",
                        "mime_type",
                        "width",
                        "height",
                        "byte_size",
                        "original_filename")) if (old.get(key) != null) row.put(key, old.get(key));
                row.put("version", 1);
                row.put("storage_key", "legacy/" + relative);
                row.put("metadata_json", Json.write(old));
                db.insert(packaging_preset, row);
                mapping("packaging_presets", old, "packaging_preset", Json.id(row.get("id")));
              }
              for (var selection : tables.getOrDefault("product_packaging_selections", List.of())) {
                var preset =
                    tables.getOrDefault("packaging_presets", List.of()).stream()
                        .filter(v -> Json.id(v.get("id")) == Json.id(selection.get("preset_id")))
                        .findFirst()
                        .orElseThrow();
                String relative = "assets/" + preset.get("storage_key");
                var file = copied.get(relative);
                if (file == null) {
                  var same =
                      copied.entrySet().stream()
                          .filter(e -> e.getValue().get("sha256").equals(preset.get("sha256")))
                          .findFirst()
                          .orElse(null);
                  if (same != null) {
                    relative = same.getKey();
                    file = same.getValue();
                  }
                }
                if (file == null) {
                  unresolved.add("packaging_presets:" + preset.get("id") + ":file_not_available");
                  continue;
                }
                String stored =
                    "legacy-packaging/"
                        + selection.get("id")
                        + "/"
                        + Path.of(preset.get("storage_key").toString()).getFileName();
                try {
                  Path target = assets.path(stored);
                  Files.createDirectories(target.getParent());
                  if (!Files.exists(target)) Files.copy(assets.path("legacy/" + relative), target);
                  else if (!fileHash(target).equals(file.get("sha256")))
                    throw new IllegalStateException("Packaging copy hash mismatch");
                } catch (IOException e) {
                  throw new IllegalStateException(e);
                }
                var row =
                    new LinkedHashMap<String, Object>(
                        Map.of(
                            "product_id",
                            selection.get("product_id"),
                            "role",
                            "PACKAGING",
                            "source",
                            "PACKAGING",
                            "version",
                            1,
                            "storage_key",
                            stored,
                            "sha256",
                            file.get("sha256"),
                            "mime_type",
                            preset.get("mime_type"),
                            "byte_size",
                            file.get("size"),
                            "metadata_json",
                            Json.write(
                                Map.of("legacy_preset", preset, "legacy_selection", selection))));
                for (String key : List.of("width", "height", "original_filename"))
                  if (preset.get(key) != null) row.put(key, preset.get(key));
                db.insert(asset, row);
                mapping("product_packaging_selections", selection, "asset", Json.id(row.get("id")));
                var original = db.one(product, Json.id(selection.get("product_id")));
                var content = Json.map(original.get("content_json"));
                content.put("packaging_asset_id", row.get("id"));
                content.put("packaging_preset_id", selection.get("preset_id"));
                db.update(
                    product,
                    new LinkedHashMap<>(
                        Map.of("id", original.get("id"), "content_json", Json.write(content))));
              }
              for (var old : tables.getOrDefault("import_batches", List.of())) {
                var row = new LinkedHashMap<String, Object>();
                for (String key :
                    List.of("id", "filename", "status", "total_rows", "valid_rows", "issue_rows"))
                  row.put(key, old.get(key));
                var issues =
                    tables.getOrDefault("import_issues", List.of()).stream()
                        .filter(v -> Json.id(v.get("batch_id")) == Json.id(old.get("id")))
                        .toList();
                row.put("issues_json", Json.write(issues));
                row.put("error_count", issues.size());
                row.put(
                    "product_ids_json",
                    Json.write(
                        tables.getOrDefault("products", List.of()).stream()
                            .filter(
                                v ->
                                    v.get("imported_batch_id") != null
                                        && Json.id(v.get("imported_batch_id"))
                                            == Json.id(old.get("id")))
                            .map(v -> v.get("id"))
                            .toList()));
                db.insert(import_batch, row);
                mapping("import_batches", old, "import_batch", Json.id(row.get("id")));
              }
              for (var old : tables.getOrDefault("review_decisions", List.of())) {
                boolean auto = Objects.toString(old.get("note"), "").contains("自动");
                var p =
                    new LinkedHashMap<String, Object>(
                        Map.of(
                            "product_id",
                            old.get("product_id"),
                            "approved_version",
                            0,
                            "fingerprint",
                            Objects.toString(old.get("subject_fingerprint"), Json.hash(old)),
                            "decision",
                            auto ? "LEGACY_AUTO_APPROVED" : "LEGACY_REVIEW_UNVERIFIED",
                            "note",
                            "原审核记录 #" + old.get("id") + "，保留于legacy_record；迁移后须重新人工审核"));
                db.insert(review, p);
                mapping("review_decisions", old, "review", Json.id(p.get("id")));
              }
              for (String table : List.of("miaoshou_drafts", "store_listings"))
                for (var old : tables.getOrDefault(table, List.of())) {
                  var p = new LinkedHashMap<String, Object>();
                  p.put("product_id", old.get("product_id"));
                  p.put("store_id", old.get("store_id"));
                  p.put(
                      "external_id",
                      old.getOrDefault("external_id", old.get("external_product_id")));
                  p.put("original_status", old.get("status"));
                  p.put("record_json", Json.write(old));
                  db.insert(legacy_external, p);
                  mapping(table, old, "legacy_external", Json.id(p.get("id")));
                }
              var report = new LinkedHashMap<String, Object>();
              report.put("source_rows", tables.values().stream().mapToInt(List::size).sum());
              report.put(
                  "archived_rows",
                  jdbc.queryForObject("SELECT COUNT(*) FROM legacy_record", Long.class));
              report.put("verified_files", files.size());
              report.put("unresolved", unresolved);
              report.put("recovered_by_exact_sha256", recovered);
              report.put("external_calls", 0);
              report.put("replayed_tasks", 0);
              report.put("approval_reset", true);
              report.put("source_untouched", true);
              if (Json.id(report.get("source_rows")) != Json.id(report.get("archived_rows")))
                throw new IllegalStateException("Archive row count mismatch");
              int amountChecks = 0;
              for (String table : List.of("products", "sku_variants"))
                for (var old : tables.getOrDefault(table, List.of()))
                  for (String field :
                      table.equals("products") ? List.of("price", "cost") : List.of("price"))
                    if (old.get(field) != null) {
                      String target = table.equals("products") ? "product" : "sku";
                      var value =
                          jdbc.queryForObject(
                              "SELECT " + field + " FROM " + target + " WHERE id=?",
                              BigDecimal.class,
                              old.get("id"));
                      if (value == null
                          || value.compareTo(new BigDecimal(old.get(field).toString())) != 0)
                        throw new IllegalStateException("Amount changed during migration");
                      amountChecks++;
                    }
              report.put("exact_amount_checks", amountChecks);
              report.put(
                  "legacy_external_records",
                  jdbc.queryForObject("SELECT COUNT(*) FROM legacy_external", Long.class));
              jdbc.update(
                  "INSERT INTO migration_run(manifest_hash,report_json) VALUES(?,?)",
                  hash,
                  Json.write(report));
              return report;
            });
    writeReport(root, database, finalReport);
  }

  private void mapping(String table, Map<String, Object> old, String target, long id) {
    jdbc.update(
        "INSERT INTO legacy_id_map(table_name,original_id,target_table,target_id) VALUES(?,?,?,?)",
        table,
        old.get("id").toString(),
        target,
        id);
  }

  private static void writeReport(Path root, String database, Map<String, Object> report)
      throws IOException {
    Path path = root.resolve("mysql-validation-" + database + ".json");
    if (Files.exists(path)) {
      if (!Json.hash(Json.map(Files.readString(path))).equals(Json.hash(report)))
        throw new IllegalStateException("Refuse to replace an existing migration report");
    } else Files.writeString(path, Json.write(report), StandardOpenOption.CREATE_NEW);
  }

  private static String fileHash(Path path) throws IOException {
    try (var stream = Files.newInputStream(path)) {
      var hash = java.security.MessageDigest.getInstance("SHA-256");
      byte[] bytes = new byte[65536];
      int count;
      while ((count = stream.read(bytes)) != -1) hash.update(bytes, 0, count);
      return HexFormat.of().formatHex(hash.digest());
    } catch (java.security.NoSuchAlgorithmException e) {
      throw new IllegalStateException(e);
    }
  }
}
