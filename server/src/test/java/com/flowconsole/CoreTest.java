package com.flowconsole;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.flowconsole.asset.AssetService;
import com.flowconsole.platform.*;
import com.flowconsole.product.CatalogService;
import java.awt.image.BufferedImage;
import java.math.BigDecimal;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

class CoreTest {
  @Test
  void exactMoneyAndInvalidAmounts() {
    assertEquals(
        new BigDecimal("9999999999999999.12345678"),
        CatalogService.money("9999999999999999.12345678", "price", true));
    for (String value : List.of("-1", "NaN", "1.000000001", "10000000000000000"))
      assertThrows(ApiException.class, () -> CatalogService.money(value, "price", true));
    assertThrows(ApiException.class, () -> CatalogService.integer("1.5", "quantity", 1));
    assertThrows(ApiException.class, () -> CatalogService.integer("0", "quantity", 1));
  }

  @Test
  void imageMustDecodeAndRejectOversizedHeaders() {
    assertThrows(ApiException.class, () -> AssetService.decode("not a png".getBytes()));
    byte[] png = AssetService.png(new BufferedImage(40, 30, BufferedImage.TYPE_INT_RGB));
    assertEquals(40, AssetService.decode(png).getWidth());
  }

  @Test
  void fileBoundaryAllowsChineseButRejectsTraversal(
      @org.junit.jupiter.api.io.TempDir java.nio.file.Path root) {
    var files = new AssetService(root.toString(), null, null, null);
    assertTrue(files.path("legacy/中文 文件.png").startsWith(root));
    for (String key :
        List.of(
            "../private", "x/../../private", "C:/private", "/private", "x\\private", "x\u0000.png"))
      assertThrows(ApiException.class, () -> files.path(key));
  }

  @Test
  void fingerprintsUseStableKeyOrderAndPreserveArrayOrder() {
    var first = new LinkedHashMap<String, Object>();
    first.put("z", 1);
    first.put("a", List.of(1, 2));
    assertEquals(Json.hash(first), Json.hash(Map.of("a", List.of(1, 2), "z", 1)));
    assertNotEquals(Json.hash(first), Json.hash(Map.of("a", List.of(2, 1), "z", 1)));
  }

  @Test
  void disabledAndAliexpressContractsAreExplicit() {
    var environment = new MockEnvironment().withProperty("flow.real-publishing", "false");
    var gateway = new PlatformGateway(environment, mock(AccountLimiter.class));
    var store =
        Map.<String, Object>of("active", true, "external_shop_id", "42", "platform", "ALIEXPRESS");
    assertEquals(
        "PUBLISHING_DISABLED",
        assertThrows(ApiException.class, () -> gateway.validate(store, "CREATE_DRAFT")).code);
    environment
        .withProperty("flow.real-publishing", "true")
        .withProperty("flow.app-key", "test-key")
        .withProperty("flow.app-secret", "test-secret");
    assertEquals(
        "CONTRACT_MISSING",
        assertThrows(ApiException.class, () -> gateway.validate(store, "CREATE_DRAFT")).code);
    assertEquals(
        "UNSUPPORTED_ACTION",
        assertThrows(ApiException.class, () -> gateway.validate(store, "PUBLISH")).code);
  }

  @Test
  void payloadsCannotSilentlyInventCategoryOrPublicImages() {
    var gateway = new PlatformGateway(new MockEnvironment(), mock(AccountLimiter.class));
    var snapshot =
        new LinkedHashMap<String, Object>(
            Map.of(
                "target_store",
                Map.of("platform", "TEMU"),
                "spu_code",
                "TEST",
                "copies",
                List.of(Map.of("platform", "TEMU", "title", "Test", "description", "Facts"))));
    assertThrows(ApiException.class, () -> gateway.wire(snapshot));
    snapshot.put("platform_payload", Map.of("cid", "123"));
    assertEquals(
        "PUBLIC_IMAGES_REQUIRED",
        assertThrows(ApiException.class, () -> gateway.wire(snapshot)).code);
  }

  @Test
  void credentialsAreNotAcceptedInsideBusinessPayloads() {
    assertThrows(
        ApiException.class,
        () ->
            Json.rejectCredentials(
                Map.of(
                    "platform_payload",
                    Map.of("nested", List.of(Map.of("appKey", "do-not-save"))))));
    assertDoesNotThrow(
        () ->
            Json.rejectCredentials(
                Map.of(
                    "account_key",
                    "public-account-label",
                    "platform_payload",
                    Map.of("cid", "123"))));
  }
}
