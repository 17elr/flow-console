CREATE TABLE publish_batch_request (
 request_key VARCHAR(100) PRIMARY KEY, request_hash CHAR(64) NOT NULL, batch_id BIGINT NOT NULL,
 FOREIGN KEY(batch_id) REFERENCES publish_batch(id)
);
