package com.flowconsole;

import static org.junit.jupiter.api.Assertions.*;

import com.flowconsole.asset.AssetService;
import java.awt.image.BufferedImage;
import java.nio.file.*;
import java.sql.*;
import java.util.*;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

@EnabledIfEnvironmentVariable(named = "RUN_INTEGRATION", matches = "true")
class MigrationIT {
  @Test
  void standaloneMigrationPreservesIdsAmountsFilesAndExternalHistory(
      @org.junit.jupiter.api.io.TempDir Path root) throws Exception {
    String database =
        "flow_migration_ci_" + UUID.randomUUID().toString().replace("-", "").substring(0, 10);
    String testUrl =
        System.getenv()
            .getOrDefault(
                "IT_DB_URL", "jdbc:mysql://127.0.0.1:13316/flow_test_java?connectionTimeZone=UTC");
    if (!testUrl.matches("jdbc:mysql://[^/]+/flow_test_[A-Za-z0-9_]+(\\?.*)?"))
      throw new IllegalArgumentException("Test databases only");
    String base = testUrl.substring(0, testUrl.indexOf('/', 13) + 1),
        user = System.getenv().getOrDefault("IT_DB_USER", "root"),
        password = System.getenv().getOrDefault("IT_DB_PASSWORD", "");
    try (var connection = DriverManager.getConnection(testUrl, user, password);
        var statement = connection.createStatement()) {
      statement.execute("CREATE DATABASE " + database + " CHARACTER SET utf8mb4");
    }
    var tables = new LinkedHashMap<String, List<Map<String, Object>>>();
    tables.put(
        "products",
        List.of(
            Map.of(
                "id",
                7,
                "spu_code",
                "MIGRATION-FIXTURE",
                "title",
                "Synthetic migration fixture",
                "category",
                "Test",
                "currency",
                "USD",
                "stock",
                5,
                "price",
                "9.12345678",
                "cost",
                "2.50000000",
                "material",
                "Steel")));
    tables.put(
        "sku_variants",
        List.of(
            Map.of(
                "id",
                11,
                "product_id",
                7,
                "sku_code",
                "MIGRATION-FIXTURE-S",
                "stock",
                5,
                "quantity",
                1,
                "price",
                "9.12345678")));
    tables.put(
        "stores",
        List.of(
            Map.of(
                "id",
                3,
                "name",
                "Synthetic migration store",
                "platform",
                "TEMU",
                "mode",
                "半托管",
                "currency",
                "USD",
                "external_shop_id",
                "123",
                "active",
                true)));
    tables.put(
        "review_decisions",
        List.of(
            Map.of(
                "id",
                18,
                "product_id",
                7,
                "subject_fingerprint",
                "a".repeat(64),
                "decision",
                "APPROVED",
                "note",
                "成品图导入后自动确认")));
    tables.put(
        "miaoshou_drafts",
        List.of(
            Map.of(
                "id",
                9,
                "product_id",
                7,
                "store_id",
                3,
                "external_id",
                "migration-external-fixture",
                "status",
                "PUBLISHED")));
    byte[] image = AssetService.png(new BufferedImage(20, 20, BufferedImage.TYPE_INT_RGB));
    Path files = root.resolve("files/assets");
    Files.createDirectories(files);
    Files.write(files.resolve("preserved.png"), image);
    tables.put(
        "asset_versions",
        List.of(
            Map.of(
                "id",
                23,
                "product_id",
                7,
                "role",
                "SPU_WHITE_MAIN",
                "version",
                1,
                "storage_key",
                "old-missing-name.png",
                "sha256",
                Json.sha(image),
                "mime_type",
                "image/png",
                "width",
                20,
                "height",
                20)));
    var inventory = new LinkedHashMap<String, Object>();
    int sourceRows = 0;
    for (var table : tables.entrySet()) {
      String data = String.join("\n", table.getValue().stream().map(Json::write).toList()) + "\n";
      Files.writeString(root.resolve(table.getKey() + ".jsonl"), data);
      inventory.put(
          table.getKey(),
          Map.of(
              "rows",
              table.getValue().size(),
              "sha256",
              Json.sha(data.getBytes(java.nio.charset.StandardCharsets.UTF_8)),
              "foreign_keys",
              List.of()));
      sourceRows += table.getValue().size();
    }
    Files.writeString(
        root.resolve("manifest.json"),
        Json.write(
            Map.of(
                "format",
                "flow-legacy-v1",
                "tables",
                inventory,
                "files",
                List.of(
                    Map.of(
                        "path",
                        "assets/preserved.png",
                        "size",
                        image.length,
                        "sha256",
                        Json.sha(image))),
                "foreign_key_issues",
                List.of())));
    Path log = root.resolve("migration.log");
    var process =
        new ProcessBuilder(
            Path.of(
                    System.getProperty("java.home"),
                    "bin",
                    System.getProperty("os.name").startsWith("Windows") ? "java.exe" : "java")
                .toString(),
            "-jar",
            Path.of("target/flow-console-2.0.0.jar").toAbsolutePath().toString(),
            "--spring.profiles.active=migration",
            "--flow.migration-path=" + root);
    process.environment().put("DB_URL", base + database + "?connectionTimeZone=UTC");
    process.environment().put("DB_USER", user);
    process.environment().put("DB_PASSWORD", password);
    process.environment().put("ASSET_ROOT", root.resolve("new-assets").toString());
    process.redirectErrorStream(true).redirectOutput(log.toFile());
    var child = process.start();
    assertTrue(child.waitFor(60, TimeUnit.SECONDS));
    assertEquals(0, child.exitValue(), Files.readString(log));
    try (var connection = DriverManager.getConnection(base + database, user, password);
        var statement = connection.createStatement()) {
      try (var result = statement.executeQuery("SELECT id,price FROM product")) {
        assertTrue(result.next());
        assertEquals(7, result.getLong(1));
        assertEquals("9.12345678", result.getBigDecimal(2).toPlainString());
      }
      try (var result = statement.executeQuery("SELECT COUNT(*) FROM legacy_record")) {
        result.next();
        assertEquals(sourceRows, result.getInt(1));
      }
      try (var result = statement.executeQuery("SELECT decision,reviewer_id FROM review")) {
        result.next();
        assertEquals("LEGACY_AUTO_APPROVED", result.getString(1));
        assertNull(result.getObject(2));
      }
      try (var result = statement.executeQuery("SELECT external_id,status FROM legacy_external")) {
        result.next();
        assertEquals("migration-external-fixture", result.getString(1));
        assertEquals("HISTORICAL_UNVERIFIED", result.getString(2));
      }
      try (var result = statement.executeQuery("SELECT COUNT(*) FROM publish_task")) {
        result.next();
        assertEquals(0, result.getInt(1));
      }
      try (var result = statement.executeQuery("SELECT platform,mode FROM store WHERE id=3")) {
        result.next();
        assertEquals("TEMU", result.getString(1));
        assertEquals("SEMI", result.getString(2));
      }
    }
    var report = Json.map(Files.readString(root.resolve("mysql-validation-" + database + ".json")));
    assertEquals(List.of(), report.get("unresolved"));
    assertEquals(1, ((List<?>) report.get("recovered_by_exact_sha256")).size());
    assertEquals(3, ((Number) report.get("exact_amount_checks")).intValue());
    var again = process.start();
    assertTrue(again.waitFor(60, TimeUnit.SECONDS));
    assertEquals(0, again.exitValue(), Files.readString(log));
  }
}
