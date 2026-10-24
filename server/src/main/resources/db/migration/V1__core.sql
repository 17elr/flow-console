CREATE TABLE app_user (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, username VARCHAR(80) NOT NULL UNIQUE,
 password_hash VARCHAR(100) NOT NULL, role VARCHAR(20) NOT NULL,
 active BOOLEAN NOT NULL DEFAULT TRUE, auth_version INT NOT NULL DEFAULT 1
);
CREATE TABLE product (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, spu_code VARCHAR(80) NOT NULL UNIQUE,
 title VARCHAR(255) NOT NULL, category VARCHAR(255) NOT NULL DEFAULT '',
 price DECIMAL(24,8), cost DECIMAL(24,8), currency VARCHAR(8) NOT NULL DEFAULT 'USD',
 stock INT NOT NULL DEFAULT 0, content_version BIGINT NOT NULL DEFAULT 1,
 content_json JSON NOT NULL, updated_by BIGINT, deleted BOOLEAN NOT NULL DEFAULT FALSE,
 created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);
CREATE TABLE sku (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, product_id BIGINT NOT NULL, sku_code VARCHAR(100) NOT NULL UNIQUE,
 price DECIMAL(24,8), stock INT NOT NULL DEFAULT 0, quantity INT NOT NULL,
 content_json JSON NOT NULL, FOREIGN KEY(product_id) REFERENCES product(id)
);
CREATE TABLE component (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, sku_id BIGINT NOT NULL, component_code VARCHAR(100) NOT NULL,
 component_name VARCHAR(255) NOT NULL, quantity INT NOT NULL, content_json JSON NOT NULL,
 UNIQUE(sku_id,component_code), FOREIGN KEY(sku_id) REFERENCES sku(id)
);
CREATE TABLE store (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(120) NOT NULL UNIQUE,
 platform VARCHAR(30) NOT NULL, mode VARCHAR(30) NOT NULL, currency VARCHAR(8) NOT NULL DEFAULT 'USD',
 external_shop_id VARCHAR(160), account_key VARCHAR(160) NOT NULL,
 active BOOLEAN NOT NULL DEFAULT TRUE, config_version BIGINT NOT NULL DEFAULT 1, content_json JSON NOT NULL
);
CREATE TABLE asset (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, product_id BIGINT NOT NULL, sku_id BIGINT,
 role VARCHAR(60) NOT NULL, source VARCHAR(30) NOT NULL, version BIGINT NOT NULL,
 storage_key VARCHAR(255) NOT NULL UNIQUE, sha256 CHAR(64) NOT NULL, mime_type VARCHAR(80) NOT NULL,
 width INT, height INT, byte_size BIGINT NOT NULL, original_filename VARCHAR(255),
 metadata_json JSON NOT NULL, created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 INDEX(product_id,role,id), FOREIGN KEY(product_id) REFERENCES product(id), FOREIGN KEY(sku_id) REFERENCES sku(id)
);
CREATE TABLE listing_copy (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, product_id BIGINT NOT NULL, platform VARCHAR(30) NOT NULL,
 title VARCHAR(500) NOT NULL, description TEXT NOT NULL, bullet_points_json JSON NOT NULL,
 generator VARCHAR(60) NOT NULL DEFAULT 'facts-template-v1', UNIQUE(product_id,platform),
 FOREIGN KEY(product_id) REFERENCES product(id)
);
CREATE TABLE review (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, product_id BIGINT NOT NULL, approved_version BIGINT NOT NULL,
 fingerprint CHAR(64) NOT NULL, reviewer_id BIGINT, decision VARCHAR(40) NOT NULL, note TEXT,
 created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), INDEX(product_id,id),
 FOREIGN KEY(product_id) REFERENCES product(id), FOREIGN KEY(reviewer_id) REFERENCES app_user(id)
);
CREATE TABLE import_batch (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, filename VARCHAR(255) NOT NULL, status VARCHAR(40) NOT NULL,
 total_rows INT NOT NULL DEFAULT 0, valid_rows INT NOT NULL DEFAULT 0, issue_rows INT NOT NULL DEFAULT 0,
 error_count INT NOT NULL DEFAULT 0, issues_json JSON NOT NULL,
 created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
);
CREATE TABLE publish_batch (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, created_by BIGINT NOT NULL, target_action VARCHAR(30) NOT NULL,
 total_tasks INT NOT NULL, created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 FOREIGN KEY(created_by) REFERENCES app_user(id)
);
CREATE TABLE publish_task (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, batch_id BIGINT NOT NULL, product_id BIGINT NOT NULL,
 store_id BIGINT NOT NULL, approved_version BIGINT NOT NULL, target_action VARCHAR(30) NOT NULL,
 status VARCHAR(30) NOT NULL DEFAULT 'PENDING', request_key VARCHAR(160) NOT NULL UNIQUE,
 request_hash CHAR(64) NOT NULL, payload_hash CHAR(64) NOT NULL, payload_snapshot JSON NOT NULL,
 external_id VARCHAR(160), external_status VARCHAR(80), stage VARCHAR(30) NOT NULL DEFAULT 'CREATE',
 attempt INT NOT NULL DEFAULT 0, next_run_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 owner_token VARCHAR(40), lease_until TIMESTAMP(6), request_started BOOLEAN NOT NULL DEFAULT FALSE,
 last_error VARCHAR(1000), created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
 UNIQUE(product_id,store_id,approved_version,target_action),
 INDEX(status,next_run_at,id), INDEX(batch_id,id), INDEX(external_id),
 FOREIGN KEY(batch_id) REFERENCES publish_batch(id), FOREIGN KEY(product_id) REFERENCES product(id),
 FOREIGN KEY(store_id) REFERENCES store(id)
);
CREATE TABLE batch_task (
 batch_id BIGINT NOT NULL, task_id BIGINT NOT NULL, PRIMARY KEY(batch_id,task_id),
 FOREIGN KEY(batch_id) REFERENCES publish_batch(id), FOREIGN KEY(task_id) REFERENCES publish_task(id)
);
CREATE TABLE publish_attempt (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, task_id BIGINT NOT NULL, stage VARCHAR(30) NOT NULL,
 started_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), finished_at TIMESTAMP(6),
 http_code INT, business_code VARCHAR(80), response_json JSON, error VARCHAR(1000),
 FOREIGN KEY(task_id) REFERENCES publish_task(id)
);
CREATE TABLE outbox_event (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, event_id VARCHAR(40) NOT NULL UNIQUE, task_id BIGINT NOT NULL,
 approved_version BIGINT NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'PENDING', attempt INT NOT NULL DEFAULT 0,
 next_run_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), owner_token VARCHAR(40), lease_until TIMESTAMP(6),
 INDEX(status,next_run_at,id), FOREIGN KEY(task_id) REFERENCES publish_task(id)
);
CREATE TABLE audit (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, user_id BIGINT, action VARCHAR(80) NOT NULL,
 subject_id BIGINT, detail VARCHAR(1000), created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
);
CREATE TABLE legacy_record (
 table_name VARCHAR(80) NOT NULL, original_id VARCHAR(80) NOT NULL, record_json JSON NOT NULL,
 PRIMARY KEY(table_name,original_id)
);
CREATE TABLE migration_run (
 manifest_hash CHAR(64) PRIMARY KEY, imported_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), report_json JSON NOT NULL
);
CREATE TABLE automation_schedule (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(120) NOT NULL, active BOOLEAN NOT NULL DEFAULT FALSE,
 run_time VARCHAR(5) NOT NULL, timezone VARCHAR(80) NOT NULL, product_ids_json JSON NOT NULL,
 store_ids_json JSON NOT NULL, target_action VARCHAR(30) NOT NULL, last_run_date VARCHAR(10), created_by BIGINT NOT NULL
);
