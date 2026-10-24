package com.flowconsole.importdata;

import com.flowconsole.*;
import com.flowconsole.auth.*;
import com.flowconsole.mapper.*;
import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import java.util.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
public class ImportController {
  private final ImportService imports;
  private final CatalogMapper db;
  private final AuthService auth;

  public ImportController(ImportService imports, CatalogMapper db, AuthService auth) {
    this.imports = imports;
    this.db = db;
    this.auth = auth;
  }

  @GetMapping("/api/imports")
  Object history() {
    return db.all(CatalogMapper.Table.import_batch).stream()
        .map(
            b -> {
              var out = new LinkedHashMap<>(b);
              out.put("issues", Json.list(b.get("issues_json")));
              out.put("product_ids", Json.list(b.get("product_ids_json")));
              return out;
            })
        .toList();
  }

  @GetMapping("/api/imports/template")
  ResponseEntity<byte[]> template() {
    return ResponseEntity.ok()
        .header("Content-Disposition", "attachment; filename=flow-products.xlsx")
        .contentType(
            MediaType.parseMediaType(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
        .body(imports.template());
  }

  @PostMapping({"/api/imports/excel", "/api/imports/finished-images"})
  Object excel(
      @RequestParam MultipartFile file,
      @RequestParam(required = false) List<MultipartFile> files,
      @RequestParam(required = false) List<String> paths,
      HttpServletRequest r)
      throws IOException {
    auth.require(AuthFilter.user(r), "ADMIN", "OPERATOR");
    var images = new LinkedHashMap<String, byte[]>();
    if (files != null) {
      if (paths == null || paths.size() != files.size())
        throw ApiException.invalid("paths", "文件夹路径清单不匹配");
      for (int i = 0; i < files.size(); i++) {
        String path = paths.get(i).replace('\\', '/');
        if (path.contains("..") || path.startsWith("/") || path.contains(":"))
          throw ApiException.invalid("paths", "文件夹路径无效");
        if (images.put(path, files.get(i).getBytes()) != null)
          throw ApiException.invalid("paths", "文件夹含重复路径");
      }
    }
    return imports.run(file.getOriginalFilename(), file.getBytes(), images, AuthFilter.userId(r));
  }

  @PostMapping("/api/imports/package")
  Object archive(@RequestParam MultipartFile file, HttpServletRequest r) throws IOException {
    auth.require(AuthFilter.user(r), "ADMIN", "OPERATOR");
    return imports.archive(file.getOriginalFilename(), file.getBytes(), AuthFilter.userId(r));
  }

  @PostMapping("/api/imports/finished-images/auto-drafts")
  Object removed() {
    throw new ApiException(409, "EXPLICIT_REVIEW_REQUIRED", "成品图导入不会自动批准。请先完成人工审核，再创建发布批次");
  }
}
