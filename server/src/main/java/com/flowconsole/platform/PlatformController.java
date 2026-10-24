package com.flowconsole.platform;

import com.flowconsole.*;
import com.flowconsole.auth.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.web.bind.annotation.*;

@RestController
public class PlatformController {
  private final PlatformGateway gateway;
  private final PlatformCatalogService catalogs;
  private final AuthService auth;

  public PlatformController(
      PlatformGateway gateway, PlatformCatalogService catalogs, AuthService auth) {
    this.gateway = gateway;
    this.catalogs = catalogs;
    this.auth = auth;
  }

  @GetMapping("/api/miaoshou/status")
  Object status() {
    return gateway.status();
  }

  @PostMapping("/api/miaoshou/stores/sync")
  Object sync(@RequestParam(defaultValue = "SEMI") String mode, HttpServletRequest r) {
    auth.require(AuthFilter.user(r), "ADMIN");
    return catalogs.synchronize(mode, AuthFilter.userId(r));
  }

  @GetMapping("/api/miaoshou/category-rules/{cid}")
  Object rules(@PathVariable String cid) {
    if (!cid.matches("[0-9]{1,30}")) throw ApiException.invalid("cid", "请输入真实数字类目ID");
    return gateway.lookup(
        "/open/v1/product/collect_box/pddkj/collect_box/get_category_attribute_rules",
        Map.of("cid", cid));
  }

  @PostMapping({"/api/products/{id}/generate-all", "/api/products/{id}/scene-batches"})
  Object missingModel() {
    throw new ApiException(409, "MODEL_NOT_CONFIGURED", "图像模型未配置，不能执行场景生图");
  }
}
