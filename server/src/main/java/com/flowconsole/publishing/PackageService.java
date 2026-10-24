package com.flowconsole.publishing;

import static com.flowconsole.mapper.CatalogMapper.Table.*;

import com.flowconsole.*;
import com.flowconsole.asset.AssetService;
import com.flowconsole.mapper.*;
import com.flowconsole.product.CatalogService;
import java.awt.Color;
import java.awt.image.BufferedImage;
import java.io.*;
import java.math.BigDecimal;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;
import javax.imageio.ImageIO;
import org.apache.poi.ss.usermodel.*;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PackageService {
  private final CatalogMapper db;
  private final CatalogService catalog;
  private final AssetService assets;

  public PackageService(CatalogMapper db, CatalogService catalog, AssetService assets) {
    this.db = db;
    this.catalog = catalog;
    this.assets = assets;
  }

  @Transactional
  public Object create(long id, long storeId, long user) {
    catalog.lock(id);
    var p = catalog.detail(id);
    var s = catalog.require(store, storeId);
    if (!s.get("platform").equals("ALIEXPRESS"))
      throw ApiException.invalid("store_id", "请选择AliExpress店铺");
    if (!catalog.reviewState(id).get("status").equals("APPROVED"))
      throw new ApiException(409, "REVIEW_REQUIRED", "请先审核当前商品版本");
    var copy =
        db.children(listing_copy, "product_id", id).stream()
            .filter(c -> c.get("platform").equals("ALIEXPRESS"))
            .findFirst()
            .orElseThrow(() -> new ApiException(409, "COPY_REQUIRED", "缺少AliExpress文案"));
    byte[] workbook;
    try (var book = new XSSFWorkbook();
        var out = new ByteArrayOutputStream()) {
      var sheet = book.createSheet("产品导入表格");
      sheet.createRow(0).createCell(0).setCellValue("产品素材包模版2 · 人工审核后生成，PACKAGE_READY不等于线上草稿");
      var headers =
          List.of(
              "* 货号",
              "* 产品名称",
              "货币类型",
              "货源链接",
              "货源平台",
              "详情描述",
              "属性",
              "规格1（颜色）",
              "SKU规格2（尺寸）",
              "平台SKU",
              "* SKU售价",
              "SKU库存",
              "SKU重量(KG)",
              "SKU尺寸(CM)");
      var header = sheet.createRow(1);
      for (int i = 0; i < headers.size(); i++) header.createCell(i).setCellValue(headers.get(i));
      int n = 2;
      for (var raw : db.children(sku, "product_id", id)) {
        var v = catalog.decode(raw);
        var row = sheet.createRow(n++);
        var values =
            List.of(
                p.get("spu_code"),
                copy.get("title"),
                p.get("currency"),
                "",
                "手动创建",
                copy.get("description"),
                "",
                Objects.toString(v.get("color"), v.get("sku_code").toString()),
                Objects.toString(v.get("size"), ""),
                v.get("sku_code"),
                v.get("price").toString(),
                v.get("stock"),
                new BigDecimal(p.get("weight_g").toString())
                    .divide(new BigDecimal("1000"))
                    .toPlainString(),
                p.get("dimensions"));
        // Monetary cells stay decimal strings: Excel's binary numbers lose precision beyond 15
        // digits.
        for (int i = 0; i < values.size(); i++)
          row.createCell(i).setCellValue(values.get(i).toString());
      }
      book.write(out);
      workbook = out.toByteArray();
    } catch (IOException e) {
      throw new ApiException(503, "PACKAGE_FAILED", "导入包生成失败");
    }
    String root = "产品素材包模版2/产品素材包/", code = p.get("spu_code").toString();
    if (!code.matches("[\\p{L}\\p{N}_.-]{1,80}") || code.equals(".."))
      throw ApiException.invalid("spu_code", "本地包货号不能包含路径或特殊字符");
    byte[] bytes;
    try (var out = new ByteArrayOutputStream();
        var zip = new ZipOutputStream(out)) {
      entry(zip, root + "产品导入表格.xlsx", workbook);
      var rows = db.children(asset, "product_id", id);
      for (int i = 0; i < CatalogService.MAIN_ROLES.size(); i++) {
        String role = CatalogService.MAIN_ROLES.get(i);
        var a =
            rows.stream()
                .filter(v -> v.get("role").equals(role))
                .reduce((first, last) -> last)
                .orElseThrow();
        entry(zip, root + "产品图片/" + code + "/产品主图/主图_" + (i + 1) + ".jpg", jpeg(assets.read(a)));
      }
      for (var v : db.children(sku, "product_id", id)) {
        var a =
            rows.stream()
                .filter(
                    r ->
                        "SKU_IMAGE".equals(r.get("role"))
                            && Objects.equals(r.get("sku_id"), v.get("id")))
                .reduce((first, last) -> last)
                .orElseThrow();
        String name =
            Objects.toString(catalog.decode(v).get("color"), v.get("sku_code").toString())
                .replaceAll("[\\\\/:*?\"<>|\\p{Cntrl}]", "_");
        entry(zip, root + "产品图片/" + code + "/SKU图/" + name + "_1.jpg", jpeg(assets.read(a)));
      }
      if (p.get("packaging_asset_id") != null) {
        var packaging = catalog.require(asset, Json.id(p.get("packaging_asset_id")));
        entry(zip, root + "产品图片/" + code + "/尺寸图表/包装图.jpg", jpeg(assets.read(packaging)));
      }
      entry(
          zip,
          root + "manifest.json",
          Json.write(
                  Map.of(
                      "status",
                      "PACKAGE_READY",
                      "product_id",
                      id,
                      "approved_version",
                      p.get("content_version"),
                      "fingerprint",
                      catalog.fingerprint(id),
                      "store_id",
                      storeId,
                      "online_draft_created",
                      false))
              .getBytes(java.nio.charset.StandardCharsets.UTF_8));
      zip.finish();
      bytes = out.toByteArray();
    } catch (IOException e) {
      throw new ApiException(503, "PACKAGE_FAILED", "素材包保存失败");
    }
    String key = "packages/" + UUID.randomUUID() + ".zip";
    try {
      Path path = assets.path(key);
      Files.createDirectories(path.getParent());
      Files.write(path, bytes, StandardOpenOption.CREATE_NEW);
    } catch (IOException e) {
      throw new ApiException(503, "STORAGE_UNAVAILABLE", "素材包无法写入，请重试");
    }
    var row =
        new LinkedHashMap<String, Object>(
            Map.of(
                "product_id",
                id,
                "store_id",
                storeId,
                "approved_version",
                p.get("content_version"),
                "storage_key",
                key,
                "sha256",
                Json.sha(bytes),
                "created_by",
                user));
    db.insert(local_package, row);
    db.audit(user, "CREATE_LOCAL_PACKAGE", Json.id(row.get("id")), "PACKAGE_READY");
    return Map.of(
        "id",
        row.get("id"),
        "status",
        "PACKAGE_READY",
        "download_url",
        "/api/local-packages/" + row.get("id") + "/content");
  }

  private static void entry(ZipOutputStream zip, String name, byte[] content) throws IOException {
    zip.putNextEntry(new ZipEntry(name));
    zip.write(content);
    zip.closeEntry();
  }

  private static byte[] jpeg(byte[] input) throws IOException {
    var source = AssetService.decode(input);
    var target =
        new BufferedImage(source.getWidth(), source.getHeight(), BufferedImage.TYPE_INT_RGB);
    var graphics = target.createGraphics();
    graphics.setColor(Color.WHITE);
    graphics.fillRect(0, 0, target.getWidth(), target.getHeight());
    graphics.drawImage(source, 0, 0, null);
    graphics.dispose();
    var out = new ByteArrayOutputStream();
    ImageIO.write(target, "jpeg", out);
    return out.toByteArray();
  }
}
