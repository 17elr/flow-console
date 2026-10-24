package com.flowconsole.mapper;

import java.util.*;
import org.apache.ibatis.annotations.*;

public interface TaskMapper {
  @Select("SELECT * FROM publish_task WHERE id=#{id} FOR UPDATE")
  Map<String, Object> lock(long id);

  @Select(
      "SELECT * FROM publish_task WHERE product_id=#{product} AND store_id=#{store} AND"
          + " approved_version=#{version} AND target_action=#{action}")
  Map<String, Object> target(
      @Param("product") long product,
      @Param("store") long store,
      @Param("version") long version,
      @Param("action") String action);

  @Select(
      "SELECT r.request_hash,t.* FROM publish_request r JOIN publish_task t ON t.id=r.task_id WHERE"
          + " r.request_key=#{key}")
  Map<String, Object> request(String key);

  @Select("SELECT * FROM publish_batch_request WHERE request_key=#{key}")
  Map<String, Object> batchRequest(String key);

  @Insert(
      "INSERT INTO publish_batch_request(request_key,request_hash,batch_id)"
          + " VALUES(#{key},#{hash},#{id})")
  void rememberBatch(@Param("key") String key, @Param("hash") String hash, @Param("id") long id);

  @Insert(
      "INSERT INTO publish_request(request_key,request_hash,task_id) VALUES(#{key},#{hash},#{id})")
  void remember(@Param("key") String key, @Param("hash") String hash, @Param("id") long id);

  @Insert("INSERT IGNORE INTO batch_task(batch_id,task_id) VALUES(#{batch},#{task})")
  void attach(@Param("batch") long batch, @Param("task") long task);

  @Select(
      "SELECT t.*,s.name AS store_name,s.platform,p.spu_code,p.title FROM publish_task t JOIN"
          + " batch_task b ON b.task_id=t.id JOIN store s ON s.id=t.store_id JOIN product p ON"
          + " p.id=t.product_id WHERE b.batch_id=#{id} ORDER BY t.id")
  List<Map<String, Object>> batch(long id);

  @Select(
      "SELECT"
          + " t.id,t.batch_id,t.product_id,t.store_id,t.approved_version,t.target_action,t.status,t.external_id,t.external_status,t.stage,t.attempt,t.last_error,t.next_run_at,t.updated_at,s.name"
          + " AS store_name,s.platform,p.spu_code,p.title FROM publish_task t JOIN store s ON"
          + " s.id=t.store_id JOIN product p ON p.id=t.product_id ORDER BY t.id DESC LIMIT 300")
  List<Map<String, Object>> recent();

  @Select(
      "SELECT id FROM outbox_event WHERE (status='PENDING' AND next_run_at<=CURRENT_TIMESTAMP(6))"
          + " OR (status='SENDING' AND lease_until<CURRENT_TIMESTAMP(6)) ORDER BY id LIMIT 50")
  List<Long> outboxDue();

  @Update(
      "UPDATE outbox_event SET"
          + " status='SENDING',owner_token=#{owner},lease_until=TIMESTAMPADD(SECOND,45,CURRENT_TIMESTAMP(6)),attempt=attempt+1"
          + " WHERE id=#{id} AND ((status='PENDING' AND next_run_at<=CURRENT_TIMESTAMP(6)) OR"
          + " (status='SENDING' AND lease_until<CURRENT_TIMESTAMP(6)))")
  int claimOutbox(@Param("id") long id, @Param("owner") String owner);

  @Update(
      "UPDATE outbox_event SET"
          + " status=#{status},next_run_at=TIMESTAMPADD(SECOND,5,CURRENT_TIMESTAMP(6)),owner_token=NULL,lease_until=NULL"
          + " WHERE id=#{id} AND owner_token=#{owner}")
  int finishOutbox(
      @Param("id") long id, @Param("owner") String owner, @Param("status") String status);

  @Update(
      "UPDATE publish_task SET"
          + " status='RUNNING',owner_token=#{owner},lease_until=TIMESTAMPADD(SECOND,600,CURRENT_TIMESTAMP(6))"
          + " WHERE id=#{id} AND status IN ('PENDING','RETRY_WAIT','VERIFYING') AND"
          + " next_run_at<=CURRENT_TIMESTAMP(6) AND (owner_token IS NULL OR"
          + " lease_until<CURRENT_TIMESTAMP(6))")
  int claim(@Param("id") long id, @Param("owner") String owner);

  @Update(
      "UPDATE publish_task SET request_started=TRUE,external_started=TRUE WHERE id=#{id} AND"
          + " owner_token=#{owner} AND status='RUNNING' AND lease_until>CURRENT_TIMESTAMP(6)")
  int sent(@Param("id") long id, @Param("owner") String owner);

  @Update(
      "UPDATE publish_task SET"
          + " status=#{status},stage=#{stage},external_id=#{external},external_status=#{externalStatus},attempt=#{attempt},next_run_at=TIMESTAMPADD(SECOND,#{delay},CURRENT_TIMESTAMP(6)),request_started=#{sent},owner_token=NULL,lease_until=NULL,last_error=#{error}"
          + " WHERE id=#{id} AND owner_token=#{owner} AND lease_until>CURRENT_TIMESTAMP(6)")
  int finish(
      @Param("id") long id,
      @Param("owner") String owner,
      @Param("status") String status,
      @Param("stage") String stage,
      @Param("external") String external,
      @Param("externalStatus") String externalStatus,
      @Param("attempt") int attempt,
      @Param("delay") int delay,
      @Param("sent") boolean sent,
      @Param("error") String error);

  @Select(
      "SELECT id FROM publish_task WHERE status='RUNNING' AND lease_until<CURRENT_TIMESTAMP(6)"
          + " ORDER BY id LIMIT 100")
  List<Long> expired();

  @Update(
      "UPDATE publish_task SET status=CASE WHEN request_started THEN 'VERIFYING' ELSE 'RETRY_WAIT'"
          + " END,owner_token=NULL,lease_until=NULL,next_run_at=CURRENT_TIMESTAMP(6),last_error='租约过期，恢复至可核验步骤'"
          + " WHERE id=#{id} AND status='RUNNING' AND lease_until<CURRENT_TIMESTAMP(6)")
  int recover(long id);

  @Select(
      "SELECT t.* FROM publish_task t WHERE t.status IN ('PENDING','RETRY_WAIT','VERIFYING') AND"
          + " t.next_run_at<=CURRENT_TIMESTAMP(6) AND NOT EXISTS (SELECT 1 FROM outbox_event o"
          + " WHERE o.task_id=t.id AND o.status IN ('PENDING','SENDING')) ORDER BY t.id LIMIT 100")
  List<Map<String, Object>> due();

  @Select(
      "SELECT EXISTS(SELECT 1 FROM publish_task t WHERE t.id=#{id} AND t.status IN"
          + " ('PENDING','RETRY_WAIT','VERIFYING') AND t.next_run_at<=CURRENT_TIMESTAMP(6) AND NOT"
          + " EXISTS(SELECT 1 FROM outbox_event o WHERE o.task_id=t.id AND o.status IN"
          + " ('PENDING','SENDING')))")
  boolean needsEvent(long id);

  @Select(
      "SELECT COUNT(*) FROM publish_task WHERE product_id=#{product} AND store_id=#{store} AND"
          + " external_started=TRUE AND status IN"
          + " ('RUNNING','VERIFYING','NEEDS_REVIEW','RETRY_WAIT')")
  int uncertain(@Param("product") long product, @Param("store") long store);

  @Select(
      "SELECT COUNT(*) FROM legacy_external WHERE product_id=#{product} AND store_id=#{store} AND"
          + " status='HISTORICAL_UNVERIFIED' AND (external_id IS NOT NULL OR original_status IN"
          + " ('PUBLISHED','VERIFYING','PUBLISHING','DRAFT_CREATED','SUCCEEDED','RUNNING'))")
  int legacyUnverified(@Param("product") long product, @Param("store") long store);
}
