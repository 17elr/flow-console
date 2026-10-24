package com.flowconsole.asset;

import static com.flowconsole.mapper.CatalogMapper.Table.*;

import com.flowconsole.*;
import com.flowconsole.mapper.*;
import com.flowconsole.product.CatalogService;
import java.awt.*;
import java.awt.image.BufferedImage;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.List;
import javax.imageio.*;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.text.PDFTextStripper;
import org.apache.poi.xslf.usermodel.XMLSlideShow;
import org.apache.poi.xslf.usermodel.XSLFTextShape;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.multipart.MultipartFile;

@Service
public class AssetService {
  private final Path root;
  private final CatalogMapper db;
  private final CatalogService catalog;
  private final TransactionTemplate tx;

  public AssetService(
      @Value("${flow.assets}") String root,
      CatalogMapper db,
      CatalogService catalog,
      TransactionTemplate tx) {
    this.root = Path.of(root).toAbsolutePath().normalize();
    this.db = db;
    this.catalog = catalog;
    this.tx = tx;
  }

  public Path path(String key) {
    if (key.isBlank()
        || key.startsWith("/")
        || key.contains(":")
        || key.contains("\\")
        || key.codePoints().anyMatch(c -> Character.isISOControl(c))
        || Arrays.stream(key.split("/")).anyMatch(s -> s.equals("..") || s.equals(".")))
      throw new ApiException(403, "INVALID_PATH", "文件路径无效");
    Path p = root.resolve(key).normalize();
    if (!p.startsWith(root)) throw new ApiException(403, "INVALID_PATH", "禁止访问此路径");
    try {
      if (Files.exists(root)) {
        Path ancestor = p;
        while (!Files.exists(ancestor)) ancestor = ancestor.getParent();
        if (!ancestor.toRealPath().startsWith(root.toRealPath()))
          throw new ApiException(403, "INVALID_PATH", "禁止访问符号链接目标");
      }
    } catch (IOException e) {
      throw new ApiException(404, "FILE_MISSING", "素材文件不存在");
    }
    return p;
  }

  public byte[] read(Map<String, Object> asset) {
    try {
      byte[] bytes = Files.readAllBytes(path(asset.get("storage_key").toString()));
      if (!Json.sha(bytes).equals(asset.get("sha256")))
        throw new ApiException(409, "HASH_MISMATCH", "素材哈希已变化，请核查文件");
      return bytes;
    } catch (IOException e) {
      throw new ApiException(404, "FILE_MISSING", "素材文件未迁移或已丢失，请从原备份补齐");
    }
  }

  public static BufferedImage decode(byte[] bytes) {
    if (bytes.length == 0 || bytes.length > 30 * 1024 * 1024)
      throw ApiException.invalid("file", "图片不能为空或超过30MB");
    try (var stream = ImageIO.createImageInputStream(new ByteArrayInputStream(bytes))) {
      var readers = ImageIO.getImageReaders(stream);
      if (!readers.hasNext()) throw ApiException.invalid("file", "文件无法解码，请使用JPEG或PNG；旧WebP保留只读");
      var reader = readers.next();
      try {
        reader.setInput(stream);
        int w = reader.getWidth(0), h = reader.getHeight(0);
        if (w < 1 || h < 1 || w > 12000 || h > 12000 || (long) w * h > 40000000)
          throw ApiException.invalid("file", "图片最多4000万像素，单边不超过12000px");
        BufferedImage image = reader.read(0);
        if (image == null) throw ApiException.invalid("file", "图片解码失败");
        return image;
      } finally {
        reader.dispose();
      }
    } catch (ApiException e) {
      throw e;
    } catch (Exception e) {
      throw ApiException.invalid("file", "文件内容不是有效图片");
    }
  }

  public static byte[] png(BufferedImage image) {
    try (var out = new ByteArrayOutputStream()) {
      ImageIO.write(image, "png", out);
      return out.toByteArray();
    } catch (IOException e) {
      throw new IllegalStateException(e);
    }
  }

  public Map<String, Object> upload(
      long productId, Long skuId, String role, String source, MultipartFile file, long user) {
    try {
      return save(
          productId,
          skuId,
          role,
          source,
          file.getOriginalFilename(),
          file.getBytes(),
          Map.of(),
          user);
    } catch (IOException e) {
      throw ApiException.invalid("file", "上传读取失败，请重试");
    }
  }

  public Map<String, Object> save(
      long productId,
      Long skuId,
      String role,
      String source,
      String filename,
      byte[] input,
      Map<String, Object> metadata,
      long user) {
    if (!Set.of("SOURCE", "FINISHED", "GENERATED", "COMPLIANCE", "PACKAGING").contains(source))
      throw ApiException.invalid("source", "素材来源无效");
    if (!(CatalogService.MAIN_ROLES.contains(role)
        || Set.of(
                "SKU_IMAGE",
                "SOURCE_MAIN",
                "SOURCE_DETAIL_1",
                "SOURCE_DETAIL_2",
                "label",
                "reach",
                "other",
                "PACKAGING")
            .contains(role))) throw ApiException.invalid("role", "素材槽位无效");
    if (role.equals("SKU_IMAGE") && skuId == null)
      throw ApiException.invalid("sku_id", "SKU图片需要独立绑定SKU");
    catalog.require(product, productId);
    if (skuId != null && Json.id(catalog.require(sku, skuId).get("product_id")) != productId)
      throw ApiException.invalid("sku_id", "SKU不属于当前SPU");
    byte[] bytes;
    String mime, ext;
    Integer width = null, height = null;
    var info = new LinkedHashMap<>(metadata);
    if (source.equals("COMPLIANCE")
        && filename != null
        && filename.toLowerCase(Locale.ROOT).endsWith(".pdf")) {
      if (input.length > 30 * 1024 * 1024) throw ApiException.invalid("file", "文件过大");
      try (var document = Loader.loadPDF(input)) {
        if (document.getNumberOfPages() > 200) throw ApiException.invalid("file", "PDF最多200页");
        info.put(
            "extracted_text",
            new PDFTextStripper()
                .getText(document)
                .substring(0, Math.min(12000, new PDFTextStripper().getText(document).length())));
      } catch (IOException e) {
        throw ApiException.invalid("file", "PDF无效或加密，无法读取");
      }
      bytes = input;
      mime = "application/pdf";
      ext = ".pdf";
    } else if (source.equals("COMPLIANCE")
        && filename != null
        && filename.toLowerCase(Locale.ROOT).endsWith(".pptx")) {
      if (input.length > 30 * 1024 * 1024) throw ApiException.invalid("file", "文件过大");
      try (var slides = new XMLSlideShow(new ByteArrayInputStream(input))) {
        if (slides.getSlides().size() > 100) throw ApiException.invalid("file", "PPTX最多100页");
        var text = new StringBuilder();
        for (var slide : slides.getSlides())
          for (var shape : slide.getShapes())
            if (shape instanceof XSLFTextShape t && text.length() < 12000)
              text.append(t.getText()).append('\n');
        info.put("extracted_text", text.substring(0, Math.min(12000, text.length())));
      } catch (IOException e) {
        throw ApiException.invalid("file", "PPTX无效");
      }
      bytes = input;
      mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation";
      ext = ".pptx";
    } else {
      var image = decode(input);
      width = image.getWidth();
      height = image.getHeight();
      bytes = png(image);
      mime = "image/png";
      ext = ".png";
      info.put("original_sha256", Json.sha(input));
      if (source.equals("COMPLIANCE")) info.put("ocr_status", "NOT_CONFIGURED");
    }
    String storageKey = UUID.randomUUID() + ext;
    Path target = path(storageKey);
    try {
      Files.createDirectories(root);
      if (mime.startsWith("image/")) {
        String originalKey = "originals/" + UUID.randomUUID() + ".bin";
        Path original = path(originalKey);
        Files.createDirectories(original.getParent());
        Files.write(original, input, StandardOpenOption.CREATE_NEW);
        info.put("original_storage_key", originalKey);
        info.put("original_sha256", Json.sha(input));
      }
      Files.write(target, bytes, StandardOpenOption.CREATE_NEW);
    } catch (IOException e) {
      throw new ApiException(503, "STORAGE_UNAVAILABLE", "素材无法保存，请保留原文件后重试");
    }
    var row = new LinkedHashMap<String, Object>();
    row.put("product_id", productId);
    row.put("sku_id", skuId);
    row.put("role", role);
    row.put("source", source);
    row.put("storage_key", storageKey);
    row.put("sha256", Json.sha(bytes));
    row.put("mime_type", mime);
    row.put("width", width);
    row.put("height", height);
    row.put("byte_size", bytes.length);
    row.put(
        "original_filename",
        filename == null
            ? "upload"
            : Path.of(filename.replace('\\', '/')).getFileName().toString());
    row.put("metadata_json", Json.write(info));
    return tx.execute(
        s -> {
          catalog.lock(productId);
          long version =
              db.children(asset, "product_id", productId).stream()
                      .filter(
                          a -> a.get("role").equals(role) && Objects.equals(a.get("sku_id"), skuId))
                      .mapToLong(a -> Json.id(a.get("version")))
                      .max()
                      .orElse(0)
                  + 1;
          row.put("version", version);
          db.insert(asset, row);
          catalog.bump(productId, user);
          db.audit(user, "UPLOAD_ASSET", Json.id(row.get("id")), source + ":" + role);
          return row;
        });
  }

  public Object transform(long id, Map<String, Object> options, long user) {
    var a = catalog.require(asset, id);
    var image = decode(read(a));
    String operation = Json.text(options, "operation");
    BufferedImage result;
    int size =
        options.containsKey("size")
            ? CatalogService.integer(options.get("size"), "size", 64)
            : 1200;
    if (size > 2400) throw ApiException.invalid("size", "输出最大2400px");
    if (operation.equals("CROP")) {
      int x = CatalogService.integer(options.get("x"), "x", 0),
          y = CatalogService.integer(options.get("y"), "y", 0),
          w = CatalogService.integer(options.get("width"), "width", 1),
          h = CatalogService.integer(options.get("height"), "height", 1);
      if ((long) x + w > image.getWidth() || (long) y + h > image.getHeight())
        throw ApiException.invalid("width", "裁剪区域超出原图");
      result = image.getSubimage(x, y, w, h);
    } else if (Set.of("RESIZE", "SIZE_CARD").contains(operation)) {
      int footer = operation.equals("SIZE_CARD") ? 100 : 0;
      result = new BufferedImage(size, size + footer, BufferedImage.TYPE_INT_RGB);
      var g = result.createGraphics();
      g.setColor(Color.WHITE);
      g.fillRect(0, 0, size, size + footer);
      g.setRenderingHint(
          RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BICUBIC);
      double scale = Math.min((double) size / image.getWidth(), (double) size / image.getHeight());
      int w = (int) (image.getWidth() * scale), h = (int) (image.getHeight() * scale);
      g.drawImage(image, (size - w) / 2, (size - h) / 2, w, h, null);
      if (footer > 0) {
        var facts = catalog.decode(catalog.require(product, Json.id(a.get("product_id"))));
        String dimensions = Json.text(facts, "dimensions");
        if (dimensions.isBlank()) {
          g.dispose();
          throw ApiException.invalid("dimensions", "缺少真实尺寸，不能生成尺寸图");
        }
        g.setColor(new Color(24, 33, 29));
        g.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, 26));
        g.drawString(dimensions, 32, size + 58);
      }
      g.dispose();
    } else throw new ApiException(409, "MODEL_NOT_CONFIGURED", "该操作需要可选算法或图像模型，请先配置并获得调用授权");
    String role = Json.text(options, "role");
    if (role.isBlank()) role = a.get("role").toString();
    return save(
        Json.id(a.get("product_id")),
        a.get("sku_id") == null ? null : Json.id(a.get("sku_id")),
        role,
        "GENERATED",
        "transformed.png",
        png(result),
        Map.of(
            "operation",
            operation,
            "input_sha256",
            a.get("sha256"),
            "pipeline_version",
            "java-image-v1",
            "options",
            options),
        user);
  }

  public List<Map<String, Object>> presets() {
    var latest = new LinkedHashMap<Integer, Map<String, Object>>();
    for (var row : db.all(packaging_preset))
      latest.putIfAbsent(((Number) row.get("slot")).intValue(), row);
    return latest.values().stream().filter(r -> Boolean.TRUE.equals(r.get("active"))).toList();
  }

  public Map<String, Object> preset(int slot) {
    return presets().stream()
        .filter(r -> ((Number) r.get("slot")).intValue() == slot)
        .findFirst()
        .orElseThrow(() -> new ApiException(404, "NOT_FOUND", "包装预设不存在"));
  }

  public Object savePreset(int slot, MultipartFile file, long user) {
    if (slot < 1 || slot > 20) throw ApiException.invalid("slot", "预设槽位需在1至20之间");
    try {
      byte[] raw = file.getBytes();
      var image = decode(raw);
      byte[] standard = png(image);
      String key = "packaging/" + UUID.randomUUID() + ".png",
          original = "originals/" + UUID.randomUUID() + ".bin";
      Files.createDirectories(path(key).getParent());
      Files.createDirectories(path(original).getParent());
      Files.write(path(key), standard, StandardOpenOption.CREATE_NEW);
      Files.write(path(original), raw, StandardOpenOption.CREATE_NEW);
      long version =
          db.all(packaging_preset).stream()
                  .filter(p -> ((Number) p.get("slot")).intValue() == slot)
                  .mapToLong(p -> Json.id(p.get("version")))
                  .max()
                  .orElse(0)
              + 1;
      var row =
          new LinkedHashMap<String, Object>(
              Map.of(
                  "slot",
                  slot,
                  "version",
                  version,
                  "storage_key",
                  key,
                  "sha256",
                  Json.sha(standard),
                  "mime_type",
                  "image/png",
                  "width",
                  image.getWidth(),
                  "height",
                  image.getHeight(),
                  "byte_size",
                  standard.length,
                  "metadata_json",
                  Json.write(
                      Map.of("original_storage_key", original, "original_sha256", Json.sha(raw)))));
      row.put("original_filename", Objects.toString(file.getOriginalFilename(), "packaging.png"));
      db.insert(packaging_preset, row);
      db.audit(user, "UPLOAD_PACKAGING_PRESET", Json.id(row.get("id")), "slot=" + slot);
      return row;
    } catch (IOException e) {
      throw new ApiException(503, "STORAGE_UNAVAILABLE", "包装图保存失败");
    }
  }
}
