# Java worker

API和worker复用 `server/target/flow-console-2.0.0.jar`，无需复制Service或额外Maven模块。

```bash
java -jar server/target/flow-console-2.0.0.jar --spring.profiles.active=worker
```

worker没有HTTP端口，启用RabbitMQ手动确认消费者和每30秒任务恢复扫描；API进程启用Outbox扫描与每日计划扫描。组合启动 `api,worker` 会立即拒绝。默认2个消费者、prefetch=1。数据库和素材目录必须与API一致。不要把旧Celery入口作为Java worker启动。
