package com.flowconsole.importdata;

import static com.flowconsole.mapper.CatalogMapper.Table.*;

import com.flowconsole.*;
import com.flowconsole.asset.AssetService;
import com.flowconsole.mapper.CatalogMapper;
import com.flowconsole.product.CatalogService;
import java.io.*;
import java.util.*;
import java.util.zip.*;
import org.apache.poi.ss.usermodel.*;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ImportService {
  public record Row(String sheet, int number, Map<String, Object> values) {
    String key() {
      return sheet + ":" + number;
    }
  }

  private final CatalogService catalog;
  private final CatalogMapper db;
  private final AssetService assets;
  private final TransactionTemplate tx;
  private static final Map<String, List<String>> ALIASES =
      Map.ofEntries(
          Map.entry("spu_code", List.of("spu", "spucode", "spu编码", "商品编码", "商品货号", "货号", "产品货号")),
          Map.entry("sku_code", List.of("sku", "skucode", "sku编码", "变体编码", "规格编码", "平台sku")),
          Map.entry("title", List.of("title", "name", "商品标题", "商品名称", "产品名称", "产品名称英文", "标题")),
          Map.entry("category", List.of("category", "类目", "商品类目", "分类")),
          Map.entry("material", List.of("material", "材质", "材料")),
          Map.entry("color", List.of("color", "颜色")),
          Map.entry("dimensions", List.of("dimensions", "商品尺寸", "包装尺寸")),
          Map.entry("size", List.of("size", "尺寸", "规格")),
          Map.entry("weight_g", List.of("weight", "weightg", "重量", "重量g", "克重")),
          Map.entry("price", List.of("price", "售价", "价格", "供货价", "sku售价")),
          Map.entry("cost", List.of("cost", "成本", "采购价")),
          Map.entry("currency", List.of("currency", "币种", "货币", "货币类型")),
          Map.entry("stock", List.of("stock", "库存", "可售库存", "sku库存")),
          Map.entry("quantity", List.of("quantity", "qty", "数量", "件数", "套装数量")),
          Map.entry("image_rights", List.of("imagerights", "图片授权", "图片版权")),
          Map.entry("source_image_url", List.of("imageurl", "图片链接", "原图", "图片地址")),
          Map.entry("component_code", List.of("componentcode", "组件编码", "子件编码")),
          Map.entry("component_name", List.of("componentname", "组件名称", "子件名称")),
          Map.entry("component_quantity", List.of("componentquantity", "组件数量", "子件数量")),
          Map.entry("store_name", List.of("store", "storename", "店铺", "店铺名称")));

  public ImportService(
      CatalogService catalog, CatalogMapper db, AssetService assets, TransactionTemplate tx) {
    this.catalog = catalog;
    this.db = db;
    this.assets = assets;
    this.tx = tx;
  }

  static String norm(String value) {
    return value.toLowerCase(Locale.ROOT).replaceAll("[\\s*\\-_/（）()]+", "");
  }

  public List<Row> parse(byte[] bytes) {
    if (bytes.length > 30 * 1024 * 1024) throw ApiException.invalid("file", "工作簿最多30MB");
    try (var workbook = WorkbookFactory.create(new ByteArrayInputStream(bytes))) {
      var out = new ArrayList<Row>();
      var formatter = new DataFormatter(Locale.ROOT);
      for (var sheet : workbook) {
        if (sheet.getPhysicalNumberOfRows() == 0) continue;
        var header = sheet.getRow(sheet.getFirstRowNum());
        var mapping = new LinkedHashMap<Integer, String>();
        for (var cell : header) {
          String label = formatter.formatCellValue(cell).trim();
          String canonical = label;
          for (var entry : ALIASES.entrySet())
            if (norm(label).equals(norm(entry.getKey()))
                || entry.getValue().stream().anyMatch(a -> norm(label).equals(norm(a)))) {
              canonical = entry.getKey();
              break;
            }
          mapping.put(cell.getColumnIndex(), canonical);
        }
        for (int n = header.getRowNum() + 1; n <= sheet.getLastRowNum(); n++) {
          var row = sheet.getRow(n);
          if (row == null) continue;
          var values = new LinkedHashMap<String, Object>();
          for (var entry : mapping.entrySet()) {
            var cell = row.getCell(entry.getKey());
            if (cell == null) continue;
            if (cell.getCellType() == CellType.FORMULA)
              throw ApiException.invalid(
                  "file", "导入不执行公式，请先将公式转为值：" + sheet.getSheetName() + ":" + (n + 1));
            String value =
                cell.getCellType() == CellType.NUMERIC
                    ? org.apache.poi.ss.util.NumberToTextConverter.toText(
                        cell.getNumericCellValue())
                    : formatter.formatCellValue(cell).trim();
            if (!value.isBlank()) values.put(entry.getValue(), value);
          }
          if (!values.isEmpty()) out.add(new Row(sheet.getSheetName(), n + 1, values));
          if (out.size() > 10000) throw ApiException.invalid("file", "单批最多10000行");
        }
      }
      if (out.isEmpty()) throw ApiException.invalid("file", "工作簿没有可导入的数据");
      return out;
    } catch (ApiException e) {
      throw e;
    } catch (Exception e) {
      throw ApiException.invalid("file", "工作簿无法读取，请上传有效xlsx");
    }
  }

  public Map<String, Object> run(
      String filename, byte[] bytes, Map<String, byte[]> images, long user) {
    var rows = parse(bytes);
    var groups = new LinkedHashMap<String, List<Row>>();
    var issues = new ArrayList<Map<String, Object>>();
    for (var row : rows) {
      String spu = Json.text(row.values(), "spu_code");
      if (spu.isBlank()) {
        issue(issues, row, "spu_code", "SPU_REQUIRED", "缺少SPU，不自动猜测归属");
        continue;
      }
      groups.computeIfAbsent(spu, k -> new ArrayList<>()).add(row);
    }
    var imported = new ArrayList<Long>();
    var failed = new HashSet<String>();
    var batch = new LinkedHashMap<String, Object>();
    batch.put("filename", filename);
    batch.put("status", "RUNNING");
    batch.put("total_rows", rows.size());
    batch.put("issues_json", Json.write(issues));
    batch.put("product_ids_json", "[]");
    db.insert(import_batch, batch);
    for (var group : groups.entrySet()) {
      try {
        Long id = tx.execute(s -> importSpu(group.getKey(), group.getValue(), images, user));
        imported.add(id);
      } catch (ApiException e) {
        failed.add(group.getKey());
        for (var row : group.getValue())
          issue(
              issues,
              row,
              e.fields.keySet().stream().findFirst().orElse("spu_code"),
              e.code,
              e.getMessage());
      } catch (org.springframework.dao.DataIntegrityViolationException e) {
        failed.add(group.getKey());
        for (var row : group.getValue())
          issue(issues, row, "sku_code", "CONFLICT", "编码冲突，此SPU整体回滚");
      } catch (RuntimeException e) {
        db.update(
            import_batch,
            new LinkedHashMap<>(
                Map.of(
                    "id",
                    batch.get("id"),
                    "status",
                    "INTERRUPTED",
                    "issues_json",
                    Json.write(issues),
                    "product_ids_json",
                    Json.write(imported))));
        throw e;
      }
      db.update(
          import_batch,
          new LinkedHashMap<>(
              Map.of(
                  "id",
                  batch.get("id"),
                  "product_ids_json",
                  Json.write(imported),
                  "issues_json",
                  Json.write(issues))));
    }
    long badRows =
        issues.stream().map(i -> i.get("sheet") + ":" + i.get("row_number")).distinct().count();
    batch.put("status", issues.isEmpty() ? "COMPLETED" : imported.isEmpty() ? "FAILED" : "PARTIAL");
    batch.put("valid_rows", rows.size() - badRows);
    batch.put("issue_rows", badRows);
    batch.put("error_count", issues.size());
    batch.put("issues_json", Json.write(issues));
    batch.put("product_ids_json", Json.write(imported));
    db.update(import_batch, batch);
    batch.put("issues", issues);
    batch.put("product_ids", imported);
    batch.put("review_status", "NEEDS_REVIEW");
    db.audit(user, "IMPORT", Json.id(batch.get("id")), batch.get("status").toString());
    return batch;
  }

  private Long importSpu(String code, List<Row> rows, Map<String, byte[]> images, long user) {
    var facts = new LinkedHashMap<String, Object>();
    var variants = new LinkedHashMap<String, Map<String, Object>>();
    var components = new HashSet<String>();
    for (var row : rows) {
      var values = row.values();
      values.forEach(
          (k, v) -> {
            if (!k.startsWith("component_") && !k.equals("sku_code")) facts.putIfAbsent(k, v);
          });
      Json.rejectCredentials(values);
      String skuCode = Json.text(values, "sku_code");
      if (!skuCode.isBlank() && !values.containsKey("component_code")) {
        if (variants.containsKey(skuCode))
          throw ApiException.invalid("sku_code", "工作簿内SKU重复：" + skuCode);
        if (!values.containsKey("quantity"))
          throw ApiException.invalid("quantity", "SKU数量缺失，不自动填充");
        variants.put(skuCode, new LinkedHashMap<>(values));
      }
      if (values.containsKey("store_name")
          && db.all(store).stream()
              .noneMatch(st -> st.get("name").equals(values.get("store_name"))))
        throw ApiException.invalid("store_name", "目标店铺不存在，请由管理员配置");
      if (values.containsKey("component_code")
          && !components.add(skuCode + ":" + values.get("component_code")))
        throw ApiException.invalid("component_code", "工作簿内重复组件：" + values.get("component_code"));
    }
    facts.put("spu_code", code);
    facts.put("import_parameters_json", Json.write(rows.stream().map(Row::values).toList()));
    facts.put("skus", new ArrayList<>(variants.values()));
    if (variants.isEmpty()) throw ApiException.invalid("sku_code", "至少需要一个SKU和真实价格、库存、数量");
    var existing = db.bySpu(code);
    var saved = catalog.save(existing == null ? null : Json.id(existing.get("id")), facts, user);
    long id = Json.id(saved.get("id"));
    for (var row : rows)
      if (row.values().containsKey("component_code")) {
        String skuCode = Json.text(row.values(), "sku_code");
        var s = db.bySku(skuCode);
        if (s == null || Json.id(s.get("product_id")) != id)
          throw ApiException.invalid("sku_code", "组件对应SKU不属于此SPU");
        var c = new LinkedHashMap<String, Object>(row.values());
        c.put("quantity", c.get("component_quantity"));
        long skuId = Json.id(s.get("id"));
        var previous =
            db.children(component, "sku_id", skuId).stream()
                .filter(v -> v.get("component_code").equals(c.get("component_code")))
                .findFirst()
                .orElse(null);
        if (previous == null) catalog.component(skuId, c, user);
        else {
          var change =
              new LinkedHashMap<String, Object>(
                  Map.of(
                      "id",
                      previous.get("id"),
                      "component_name",
                      Json.text(c, "component_name"),
                      "quantity",
                      CatalogService.integer(c.get("quantity"), "component_quantity", 1),
                      "content_json",
                      Json.write(c)));
          db.update(component, change);
        }
      }
    for (var entry : images.entrySet()) {
      String name = entry.getKey().replace('\\', '/');
      String[] parts = name.split("/");
      if (parts.length < 2 || !parts[parts.length - 2].equals(code)) continue;
      String stem = parts[parts.length - 1].replaceFirst("\\.[^.]+$", "");
      int index = List.of("01", "02", "03", "04", "05", "06").indexOf(stem);
      String role;
      Long skuId = null;
      if (index >= 0) role = CatalogService.MAIN_ROLES.get(index);
      else {
        var s = db.bySku(stem);
        if (s == null || Json.id(s.get("product_id")) != id) continue;
        role = "SKU_IMAGE";
        skuId = Json.id(s.get("id"));
      }
      var previous = db.children(asset, "product_id", id);
      String original = Json.sha(entry.getValue());
      Long targetSku = skuId;
      String targetRole = role;
      if (previous.stream()
          .noneMatch(
              a ->
                  targetRole.equals(a.get("role"))
                      && Objects.equals(a.get("sku_id"), targetSku)
                      && original.equals(Json.map(a.get("metadata_json")).get("original_sha256"))))
        assets.save(
            id,
            skuId,
            role,
            "FINISHED",
            parts[parts.length - 1],
            entry.getValue(),
            Map.of("import_source", name),
            user);
    }
    return id;
  }

  private void issue(
      List<Map<String, Object>> out, Row row, String field, String code, String message) {
    out.add(
        Map.of(
            "sheet",
            row.sheet(),
            "row_number",
            row.number(),
            "identifier",
            Json.text(row.values(), "spu_code"),
            "field",
            field,
            "severity",
            "ERROR",
            "code",
            code,
            "message",
            message));
  }

  public Object archive(String filename, byte[] zip, long user) {
    byte[] workbook = null;
    var images = new LinkedHashMap<String, byte[]>();
    long total = 0;
    int count = 0;
    try (var stream = new ZipInputStream(new ByteArrayInputStream(zip))) {
      ZipEntry entry;
      while ((entry = stream.getNextEntry()) != null) {
        if (++count > 2000) throw ApiException.invalid("file", "压缩包最多2000项");
        String name = entry.getName().replace('\\', '/');
        if (name.startsWith("/")
            || name.matches("^[A-Za-z]:.*")
            || Arrays.asList(name.split("/")).contains(".."))
          throw ApiException.invalid("file", "压缩包包含越界路径");
        if (entry.isDirectory()) continue;
        byte[] data = stream.readNBytes(30 * 1024 * 1024 + 1);
        total += data.length;
        if (data.length > 30 * 1024 * 1024 || total > 150 * 1024 * 1024)
          throw ApiException.invalid("file", "压缩包解压总量超过150MB或单文件超过30MB");
        if (name.toLowerCase(Locale.ROOT).endsWith(".xlsx")) {
          if (workbook != null) throw ApiException.invalid("file", "压缩包只能包含一个工作簿");
          workbook = data;
        } else if (name.toLowerCase(Locale.ROOT).matches(".*\\.(png|jpg|jpeg)$")) {
          if (images.put(name, data) != null) throw ApiException.invalid("file", "压缩包包含同名图片");
        }
      }
    } catch (IOException e) {
      throw ApiException.invalid("file", "压缩包损坏");
    }
    if (workbook == null) throw ApiException.invalid("file", "压缩包缺少工作簿");
    return run(filename, workbook, images, user);
  }

  public byte[] template() {
    try (var workbook = new XSSFWorkbook();
        var out = new ByteArrayOutputStream()) {
      var sheet = workbook.createSheet("商品SKU");
      var row = sheet.createRow(0);
      var headers =
          List.of(
              "spu_code",
              "sku_code",
              "title",
              "category",
              "material",
              "color",
              "dimensions",
              "weight_g",
              "price",
              "cost",
              "currency",
              "stock",
              "quantity",
              "size",
              "image_rights",
              "store_name");
      for (int i = 0; i < headers.size(); i++) {
        row.createCell(i).setCellValue(headers.get(i));
        sheet.setColumnWidth(i, 24 * 256);
      }
      workbook.write(out);
      return out.toByteArray();
    } catch (IOException e) {
      throw new IllegalStateException(e);
    }
  }
}
