CREATE TABLE publish_request (
 request_key VARCHAR(160) PRIMARY KEY, request_hash CHAR(64) NOT NULL, task_id BIGINT NOT NULL,
 FOREIGN KEY(task_id) REFERENCES publish_task(id)
);
