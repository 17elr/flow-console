package com.flowconsole.publishing;

import static com.flowconsole.mapper.CatalogMapper.Table.*;

import com.flowconsole.*;
import com.flowconsole.auth.*;
import com.flowconsole.mapper.*;
import com.flowconsole.platform.PlatformGateway;
import com.flowconsole.product.CatalogService;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.bind.annotation.*;

@RestController
public class LegacyResults {
  private final CatalogMapper db;
  private final CatalogService catalog;
  private final PlatformGateway gateway;
  private final AuthService auth;
  private final TransactionTemplate tx;

  public LegacyResults(
      CatalogMapper db,
      CatalogService catalog,
      PlatformGateway gateway,
      AuthService auth,
      TransactionTemplate tx) {
    this.db = db;
    this.catalog = catalog;
    this.gateway = gateway;
    this.auth = auth;
    this.tx = tx;
  }

  @PostMapping("/api/legacy-external/{id}/verify")
  Object verify(
      @PathVariable long id, @RequestBody Map<String, Object> payload, HttpServletRequest request) {
    auth.require(AuthFilter.user(request), "ADMIN", "REVIEWER");
    String reason = Json.text(payload, "reason");
    if (reason.isBlank() || reason.length() > 500)
      throw ApiException.invalid("reason", "请填写核查原因，最多500字");
    var old = catalog.require(legacy_external, id);
    String external = Json.text(old, "external_id");
    if (external.isBlank()) {
      external = Json.text(payload, "externalId");
      if (!external.matches("[a-zA-Z0-9_-]{1,160}"))
        throw ApiException.invalid("externalId", "请填写人工核查得到的真实外部ID");
    }
    if (old.get("store_id") == null)
      throw new ApiException(409, "STORE_REQUIRED", "历史记录缺少店铺关系，请人工核查");
    var snapshot = new LinkedHashMap<String, Object>();
    snapshot.put(
        "target_store", catalog.decode(catalog.require(store, Json.id(old.get("store_id")))));
    String action =
        Set.of("PUBLISHED", "SUCCEEDED", "VERIFYING", "PUBLISHING")
                .contains(Json.text(old, "original_status"))
            ? "PUBLISH"
            : "CREATE_DRAFT";
    var task =
        new LinkedHashMap<String, Object>(
            Map.of(
                "payload_snapshot",
                Json.write(snapshot),
                "target_action",
                action,
                "external_id",
                external,
                "stage",
                "VERIFY"));
    var result = gateway.execute(task, true, () -> {});
    if (result.externalStatus().equals("UNKNOWN"))
      throw new ApiException(409, "STILL_UNVERIFIED", "权威查询尚未匹配该外部ID，历史状态继续保留待核验");
    String verifiedId = external;
    return tx.execute(
        s -> {
          catalog.lock(Json.id(old.get("product_id")));
          var evidence = Json.map(old.get("record_json"));
          evidence.put(
              "_verification",
              Map.of(
                  "reason",
                  reason,
                  "reviewer_id",
                  AuthFilter.userId(request),
                  "at",
                  java.time.Instant.now().toString(),
                  "external_id",
                  verifiedId,
                  "state",
                  result.externalStatus(),
                  "response",
                  result.evidence()));
          var update =
              new LinkedHashMap<String, Object>(
                  Map.of(
                      "id",
                      id,
                      "external_id",
                      verifiedId,
                      "status",
                      "CONFIRMED_" + result.externalStatus(),
                      "record_json",
                      Json.write(evidence)));
          db.update(legacy_external, update);
          db.audit(AuthFilter.userId(request), "VERIFY_LEGACY_RESULT", id, reason);
          return update;
        });
  }
}
