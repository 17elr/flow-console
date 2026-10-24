ALTER TABLE publish_task ADD COLUMN external_started BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE publish_task ADD COLUMN stage_context JSON;
CREATE TABLE local_package (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, product_id BIGINT NOT NULL, store_id BIGINT NOT NULL,
 approved_version BIGINT NOT NULL, storage_key VARCHAR(255) NOT NULL UNIQUE, sha256 CHAR(64) NOT NULL,
 status VARCHAR(30) NOT NULL DEFAULT 'PACKAGE_READY', created_by BIGINT NOT NULL,
 created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 FOREIGN KEY(product_id) REFERENCES product(id), FOREIGN KEY(store_id) REFERENCES store(id)
);
CREATE TABLE legacy_id_map (
 table_name VARCHAR(80) NOT NULL, original_id VARCHAR(80) NOT NULL, target_table VARCHAR(80) NOT NULL,
 target_id BIGINT NOT NULL, PRIMARY KEY(table_name,original_id)
);
CREATE TABLE legacy_external (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, product_id BIGINT NOT NULL, store_id BIGINT,
 external_id VARCHAR(160), original_status VARCHAR(80), status VARCHAR(40) NOT NULL DEFAULT 'HISTORICAL_UNVERIFIED',
 record_json JSON NOT NULL, INDEX(product_id,id), INDEX(external_id), FOREIGN KEY(product_id) REFERENCES product(id)
);
