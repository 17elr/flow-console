CREATE TABLE image_operation (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, job_id VARCHAR(80) NOT NULL UNIQUE,
 input_asset_id BIGINT NOT NULL, input_hash CHAR(64) NOT NULL, params_hash CHAR(64) NOT NULL,
 operation VARCHAR(40) NOT NULL, status VARCHAR(30) NOT NULL, result_asset_id BIGINT,
 evidence_json JSON NOT NULL, created_by BIGINT NOT NULL,
 created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), FOREIGN KEY(input_asset_id) REFERENCES asset(id)
);
