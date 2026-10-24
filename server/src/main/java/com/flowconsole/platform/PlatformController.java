package com.flowconsole.platform;

import com.flowconsole.ApiException;
import java.util.*;
import org.springframework.web.bind.annotation.*;

@RestController
public class PlatformController {
  private final PlatformGateway gateway;

  public PlatformController(PlatformGateway gateway) {
    this.gateway = gateway;
  }

  @GetMapping("/api/miaoshou/status")
  Object status() {
    return gateway.status();
  }

  @PostMapping({"/api/products/{id}/generate-all", "/api/products/{id}/scene-batches"})
  Object missingModel() {
    throw new ApiException(409, "MODEL_NOT_CONFIGURED", "图像模型未配置，不能执行场景生图");
  }
}
