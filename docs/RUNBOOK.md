# 运行手册

## Docker Compose / Linux

需要Docker及Compose v2。`.env.example`复制到`.env.java`，分别设置MySQL、Redis、RabbitMQ和初始管理员密码；不要覆盖旧`.env`。数据库密码在Compose中为必填，不使用固定默认生产密码。

```bash
docker compose --env-file .env.java up -d --build
docker compose --env-file .env.java ps
docker compose --env-file .env.java logs --tail=100 api worker
docker compose --env-file .env.java stop
```

首次账号admin，仅在用户表为空且设置了`BOOTSTRAP_ADMIN_PASSWORD`时创建。进入成员管理创建OPERATOR与REVIEWER；最后修改人不能批准自己的商品。改密、停用或变更角色会使旧session失效。

工作台3000、API8000、MySQL13316、Redis16376、RabbitMQ15676与管理15677均仅映射127.0.0.1。容器内部用3306/6379/5672。MySQL、Redis、RabbitMQ、素材分别使用命名卷。停止不删除卷；不要使用`down -v`做排错。

Linux公网部署在工作台前配置HTTPS反向代理，设置`COOKIE_SECURE=true`；仅公开HTTPS入口，保留内部端口和认证检查。前端Nginx代理`/api`到Java，无跨域凭据配置。先运行`/health`确认进程，再登录检查`/api/readiness`；二者不访问收费服务。

## 原生开发

需要JDK17（确保`java -version`不是旧Java8）、Maven3.9+、Node24与独立MySQL8/Redis/RabbitMQ。也可只用Compose启动`mysql redis rabbitmq`，然后本机运行Java和Vue。

配置`DB_URL/DB_USER/DB_PASSWORD`、`REDIS_HOST/REDIS_PORT/REDIS_PASSWORD`、`RABBIT_HOST/RABBIT_PORT/RABBIT_USER/RABBIT_PASSWORD`、`ASSET_ROOT`和`BOOTSTRAP_ADMIN_PASSWORD`。这些值放环境或受保护本地配置，不提交Git。

```bash
mvn -B -f server/pom.xml package
java -jar server/target/flow-console-2.0.0.jar --spring.profiles.active=api
# 另一个进程，使用相同数据库与素材配置：
java -jar server/target/flow-console-2.0.0.jar --spring.profiles.active=worker
# 另一个终端：
cd web
npm ci
npm run dev
```

API默认8000、Vite默认3000。api/worker两个profile禁止在同一进程同时启用。worker无HTTP服务。`SCHEDULERS_ENABLED=false`只用于隔离验收，正常运行需要API的Outbox扫描与worker的恢复扫描。

## 平台与模型

默认`REAL_PUBLISHING_ENABLED=false`、`IMAGE_MODEL_ENABLED=false`。没有获得真实店铺和付费调用授权前，不启用。模型URL、AppKey、AppSecret和内部token均只在服务端配置。

TEMU需要店铺授权ID、正确模式、已批准商品和经过核对的`platform_payload`；公开图片URL应由你控制的素材/CDN提供，不能把带认证Cookie的内部下载地址交给平台。Java不自动下载任意远程图片。

AliExpress在线草稿必须配置`MIAOSHOU_PUBLIC_COLLECT_CREATE_PATH`，查询另配`MIAOSHOU_PUBLIC_COLLECT_QUERY_PATH`；未配置409。AliExpress不支持自动发布，本地导入包单独下载，不是线上成功证据。

图像模型配置`IMAGE_MODEL_ENABLED/URL/API_KEY/MODEL`，仅支持返回可验证内嵌图片的兼容编辑接口，保存输入、提示词版本与实际请求ID。可选算法见`compute-adapter/README.md`。启用Compose compute profile前设置强token及`COMPUTE_URL=http://compute:8100`；默认镜像只有Pillow，OCR/BiRefNet需明确安装运行时与本地模型。

## 处理异常

- MQ离线：任务和Outbox继续在MySQL保留，恢复后补投，不删除任务或清空队列。
- Redis离线：暂停外部发送，修复共享限流服务后按任务状态恢复，禁止实例各自无限降级发送。
- 平台超时：查看阶段、外部ID与尝试记录。结果未知使用重新核验；没有ID时人工核查后补充ID，不重新创建。
- 业务字段错误：修正资料并重新审核，创建新批准版本任务。老版本不能用force绕过唯一约束。
- 素材哈希或路径错误：从保留的只读导出补齐匹配SHA的文件，不能用另一张“相似”图片代替。
- 登录403：先获取csrf，再登录，写请求携带token。改密后401是预期会话失效。

## 检查命令

`mvn verify`默认运行单元检查。完整检查设置`RUN_INTEGRATION=true`以及`IT_DB_URL`（只接受flow_test_*）、`IT_DB_USER/PASSWORD`、`IT_RABBIT_USER/PASSWORD`，服务端口同上。集成测试还创建独立`flow_migration_ci_*`库验证CLI迁移，不清理业务库或卷。

在完成完整Java检查并启动关闭外部操作的测试API后，`cd web && npm test && npm run build && npm run test:e2e`。Windows浏览器测试使用独立Edge测试配置；Linux CI安装Playwright Chromium。测试中的固定账号和密码仅用于隔离测试库。
