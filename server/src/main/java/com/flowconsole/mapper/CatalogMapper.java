package com.flowconsole.mapper;

import java.util.*;
import org.apache.ibatis.annotations.*;

public interface CatalogMapper {
  enum Table {
    product,
    sku,
    component,
    store,
    asset,
    listing_copy,
    review,
    import_batch,
    publish_batch,
    publish_task,
    publish_attempt,
    outbox_event,
    audit,
    app_user,
    automation_schedule,
    local_package,
    legacy_external,
    image_operation,
    packaging_preset;
  }

  @Select("SELECT * FROM product WHERE deleted=FALSE ORDER BY id DESC LIMIT 2000")
  List<Map<String, Object>> products();

  @Select("SELECT * FROM product WHERE id=#{id} FOR UPDATE")
  Map<String, Object> lockProduct(long id);

  @Select("SELECT * FROM product WHERE spu_code=#{code}")
  Map<String, Object> bySpu(String code);

  @Select("SELECT * FROM sku WHERE sku_code=#{code}")
  Map<String, Object> bySku(String code);

  @Select("SELECT * FROM image_operation WHERE job_id=#{job}")
  Map<String, Object> imageJob(String job);

  @SelectProvider(type = Sql.class, method = "one")
  Map<String, Object> one(@Param("table") Table table, @Param("id") long id);

  @SelectProvider(type = Sql.class, method = "all")
  List<Map<String, Object>> all(@Param("table") Table table);

  @SelectProvider(type = Sql.class, method = "children")
  List<Map<String, Object>> children(
      @Param("table") Table table, @Param("column") String column, @Param("id") long id);

  @InsertProvider(type = Sql.class, method = "insert")
  @Options(useGeneratedKeys = true, keyProperty = "row.id")
  int insert(@Param("table") Table table, @Param("row") Map<String, Object> row);

  @UpdateProvider(type = Sql.class, method = "update")
  int update(@Param("table") Table table, @Param("row") Map<String, Object> row);

  @Delete("DELETE FROM component WHERE id=#{id}")
  int deleteComponent(long id);

  @Select("SELECT * FROM review WHERE product_id=#{id} ORDER BY id DESC LIMIT 1")
  Map<String, Object> lastReview(long id);

  @Update(
      "UPDATE publish_task SET status='NEEDS_REVIEW',last_error='内容版本已变化，需要重新审核' WHERE"
          + " product_id=#{id} AND status IN ('PENDING','RETRY_WAIT') AND external_started=FALSE")
  int invalidate(long id);

  @Insert(
      "INSERT INTO audit(user_id,action,subject_id,detail)"
          + " VALUES(#{user},#{action},#{subject},#{detail})")
  void audit(
      @Param("user") Long user,
      @Param("action") String action,
      @Param("subject") Long subject,
      @Param("detail") String detail);

  @Update(
      "UPDATE automation_schedule SET last_run_date=#{day} WHERE id=#{id} AND active=TRUE AND"
          + " (last_run_date IS NULL OR last_run_date<>#{day})")
  int claimSchedule(@Param("id") long id, @Param("day") String day);

  class Sql {
    private static String table(Map<String, Object> p) {
      return ((Table) p.get("table")).name();
    }

    private static String column(String column) {
      if (!Set.of("product_id", "sku_id", "task_id", "batch_id").contains(column))
        throw new IllegalArgumentException("Unsupported relation");
      return column;
    }

    public static String one(Map<String, Object> p) {
      return "SELECT * FROM " + table(p) + " WHERE id=#{id}";
    }

    public static String all(Map<String, Object> p) {
      return "SELECT * FROM " + table(p) + " ORDER BY id DESC LIMIT 2000";
    }

    public static String children(Map<String, Object> p) {
      return "SELECT * FROM "
          + table(p)
          + " WHERE "
          + column((String) p.get("column"))
          + "=#{id} ORDER BY id";
    }

    @SuppressWarnings("unchecked")
    public static String insert(Map<String, Object> p) {
      Map<String, Object> row = (Map<String, Object>) p.get("row");
      List<String> keys = keys(row);
      return "INSERT INTO "
          + table(p)
          + " ("
          + String.join(",", keys)
          + ") VALUES ("
          + String.join(",", keys.stream().map(k -> "#{row." + k + "}").toList())
          + ")";
    }

    @SuppressWarnings("unchecked")
    public static String update(Map<String, Object> p) {
      Map<String, Object> row = (Map<String, Object>) p.get("row");
      return "UPDATE "
          + table(p)
          + " SET "
          + String.join(
              ",",
              keys(row).stream()
                  .filter(k -> !k.equals("id"))
                  .map(k -> k + "=#{row." + k + "}")
                  .toList())
          + " WHERE id=#{row.id}";
    }

    private static List<String> keys(Map<String, Object> row) {
      for (String k : row.keySet())
        if (!k.matches("[a-z][a-z0-9_]*")) throw new IllegalArgumentException("Invalid column");
      return new ArrayList<>(row.keySet());
    }
  }
}
