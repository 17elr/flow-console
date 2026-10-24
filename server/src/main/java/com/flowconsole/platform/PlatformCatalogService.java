package com.flowconsole.platform;

import com.flowconsole.*;
import com.flowconsole.mapper.CatalogMapper;
import com.flowconsole.product.CatalogService;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class PlatformCatalogService {
  private final PlatformGateway gateway;
  private final CatalogMapper db;
  private final CatalogService catalog;
  private final TransactionTemplate tx;

  public PlatformCatalogService(
      PlatformGateway gateway, CatalogMapper db, CatalogService catalog, TransactionTemplate tx) {
    this.gateway = gateway;
    this.db = db;
    this.catalog = catalog;
    this.tx = tx;
  }

  @SuppressWarnings("unchecked")
  public Object synchronize(String mode, long user) {
    if (!Set.of("SEMI", "FULL", "ALIEXPRESS").contains(mode))
      throw ApiException.invalid("mode", "请选择SEMI、FULL或ALIEXPRESS");
    String platform =
        mode.equals("ALIEXPRESS") ? "aliexpress" : mode.equals("SEMI") ? "pddkjChoice" : "pddkj";
    String site =
        mode.equals("ALIEXPRESS") ? "ALIEXPRESS" : mode.equals("SEMI") ? "PDDKJCHOICE" : "PDDKJ";
    var candidates = new ArrayList<Map<String, Object>>();
    for (int page = 1; page <= 20; page++) {
      var response =
          gateway.lookup(
              "/open/v1/product/shop/shop/get_shop_list",
              Map.of("platform", platform, "site", site, "pageNo", page, "pageSize", 100));
      Object data = response.get("data");
      List<?> values;
      if (data instanceof List<?> list) values = list;
      else if (data instanceof Map<?, ?> map)
        values =
            map.entrySet().stream()
                .filter(
                    e ->
                        Set.of("list", "records", "rows", "shoplist", "datalist")
                                .contains(e.getKey().toString().toLowerCase(Locale.ROOT))
                            && e.getValue() instanceof List<?>)
                .map(e -> (List<?>) e.getValue())
                .findFirst()
                .orElse(List.of());
      else throw new ApiException(422, "INVALID_PLATFORM_RESPONSE", "平台店铺列表结构无法识别，未写入配置");
      for (Object value : values) {
        if (!(value instanceof Map<?, ?> map))
          throw new ApiException(422, "INVALID_PLATFORM_RESPONSE", "平台店铺条目无效，未写入配置");
        candidates.add((Map<String, Object>) map);
      }
      if (values.size() < 100) break;
      if (page == 20) throw new ApiException(422, "SHOP_LIST_LIMIT", "店铺列表超过2000项，请按受控范围同步");
    }
    return tx.execute(
        s -> {
          var result = new ArrayList<Object>();
          for (var candidate : candidates) {
            String external = first(candidate, "shopId", "shop_id", "id"),
                name =
                    first(
                        candidate, "shopName", "shop_name", "platformShopName", "shopNick", "name");
            if (external.isBlank() || name.isBlank())
              throw new ApiException(422, "INVALID_PLATFORM_RESPONSE", "店铺缺少真实ID或名称，本次同步已回滚");
            String raw =
                first(candidate, "platform", "platformCode", "site").toLowerCase(Locale.ROOT);
            if (!raw.isBlank()
                && (raw.contains("ali") || raw.contains("速卖通")) != mode.equals("ALIEXPRESS"))
              throw new ApiException(422, "PLATFORM_MISMATCH", "返回店铺平台与所选模式不符，本次同步已回滚");
            var existing =
                db.all(CatalogMapper.Table.store).stream()
                    .filter(
                        row ->
                            external.equals(row.get("external_shop_id"))
                                && row.get("platform")
                                    .equals(mode.equals("ALIEXPRESS") ? "ALIEXPRESS" : "TEMU"))
                    .findFirst()
                    .orElse(null);
            var input =
                new LinkedHashMap<String, Object>(
                    Map.of(
                        "name",
                        name,
                        "external_shop_id",
                        external,
                        "platform",
                        mode.equals("ALIEXPRESS") ? "ALIEXPRESS" : "TEMU",
                        "mode",
                        mode,
                        "account_key",
                        existing == null ? "miaoshou-shared-account" : existing.get("account_key"),
                        "active",
                        true));
            result.add(
                catalog.saveStore(
                    existing == null ? null : Json.id(existing.get("id")), input, user));
          }
          db.audit(user, "SYNC_STORES", null, "mode=" + mode + " count=" + result.size());
          return Map.of("mode", mode, "count", result.size(), "stores", result);
        });
  }

  private static String first(Map<String, Object> row, String... keys) {
    for (String key : keys) if (!Json.text(row, key).isBlank()) return Json.text(row, key);
    return "";
  }
}
