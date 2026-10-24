# Java API

所有业务接口使用相同站点Cookie。公共白名单只有`GET /health`、`GET /api/auth/csrf`及携带CSRF的`POST /api/auth/login`。匿名业务读取401，缺CSRF写请求403；不接受`X-User-Id`或客户端角色。

先获取csrf，再登录；后续每个写请求发送`X-CSRF-Token`。浏览器统一实现见`web/src/api.js`，支持FormData且204不解析JSON。错误结构固定为`code/message/fieldErrors/requestId`，使用400/401/403/404/409/422/503。

| 方法与路径 | 内容 / 权限 |
|---|---|
| GET `/api/auth/csrf` | 匿名会话CSRF token |
| POST `/api/auth/login` | username/password；成功变更sessionId |
| GET `/api/auth/me`、POST `/api/auth/logout` | 当前身份 / 注销204 |
| GET/POST `/api/users`、PATCH `/api/users/{id}` | ADMIN；建号、角色、停用或改密；旧会话失效 |
| GET `/api/overview`、`/api/readiness` | 业务统计 / 数据库就绪，均不调用模型 |
| GET/POST `/api/products` | 商品列表 / 新建；写入OPERATOR或ADMIN |
| GET/PATCH/DELETE `/api/products/{id}` | 详情 / 修改 / 软归档，保留历史与文件 |
| PATCH `/api/skus/{id}` | 更新规格、数量、价格与库存，禁止跨SPU归属 |
| POST `/api/skus/{id}/components`、DELETE `/api/components/{id}` | 套装组件；编码重复409 |
| GET `/api/products/{id}/workflow`、`/image-readiness` | 商品、审核、资料缺项 |
| POST `/api/products/{id}/listing-copies` | platform、可选title/description/bullet_points；省略正文使用事实模板 |
| PUT `/api/listing-copies/{id}` | 保存人工文案，修改后重审 |
| PUT `/api/products/{id}/review` | REVIEWER/ADMIN；decision、content_version、note；最后修改人不能自批 |
| POST `/api/source-assets` | multipart product_id、可选sku_id、role、source、file |
| PUT `/api/generated-assets/{id}` | 追加替换版本，不覆盖旧文件 |
| GET `/api/assets/{id}/content`、`/original` | 认证下载，校验商品、路径与SHA-256 |
| POST `/api/assets/{id}/transform` | RESIZE/CROP/SIZE_CARD，裁剪坐标与尺寸校验 |
| PUT `/api/reviews/images/{id}` | 显式人工图片决定，不自动批准商品 |
| GET `/api/image-provider/status`、`/api/image-operations` | 配置可用性与真实处理记录 |
| POST `/api/assets/{id}/operations/{jobId}` | MODEL/OCR/REMOVE_BACKGROUND/RESIZE；同jobId异输入409；默认模型关闭 |
| GET `/api/imports`、`/api/imports/template` | 批次、问题清单 / xlsx模板 |
| POST `/api/imports/excel` | multipart file；SPU事务，按行去重计错 |
| POST `/api/imports/finished-images` | file工作簿、files数组、同长paths数组；不自动批准 |
| POST `/api/imports/package` | ZIP内一个工作簿和SPU图片文件夹；限制路径、数量及解压量 |
| POST `/api/imports/finished-images/auto-drafts` | 409；明确要求人工审核后创建发布批次 |
| GET/POST `/api/stores`、PUT/DELETE `/api/stores/{id}` | 写入仅ADMIN；删除为停用；配置变化重新审核 |
| GET `/api/miaoshou/status` | 真实开关和契约状态，不返回密钥 |
| POST `/api/miaoshou/stores/sync?mode=SEMI` | ADMIN；真实授权店铺分页读取，模式SEMI/FULL/ALIEXPRESS；缺配置409，写配置同事务 |
| GET `/api/miaoshou/category-rules/{cid}` | 数字末级类目ID；读取平台规则与真实枚举，不填猜测值 |
| POST `/api/publish-batches` | 持久化后202；OPERATOR/ADMIN；不等待外部HTTP |
| GET `/api/publish-batches`、`/{id}` | 批次及包/草稿/已确认发布/待核验/失败/跳过分别计数 |
| GET `/api/publish-tasks`、`/{id}/attempts` | 最近300任务 / 脱敏阶段证据 |
| POST `/api/publish-tasks/{id}/verify`、`/retry`、`/cancel` | REVIEWER/ADMIN；必须reason；不绕过版本或未知结果限制 |
| POST `/api/publish-tasks/{id}/resolve` | 人工查明外部ID后补充externalId/reason，仅进入核验，不直接成功 |
| POST `/api/products/{id}/aliexpress-import-package` | store_id；已批准版本；PACKAGE_READY及下载URL |
| GET `/api/local-packages`、`/{id}/content` | 包清单与认证下载，独立于线上成功数 |
| GET/POST `/api/products/{id}/compliance` | 合规清单 / multipart kind及file，支持PNG/JPEG/PDF/PPTX |
| GET `/api/compliance-library`、POST `/api/products/{id}/compliance/{assetId}/reuse` | 资料复用，真实文本提取，不伪造认证 |
| GET `/api/packaging-presets`、PUT/DELETE `/api/packaging-presets/{slot}` | 团队包装预设，上传新版本或停用；GET `/{slot}/content`读取最新有效版本 |
| PUT `/api/products/{id}/packaging-selection` | 包装素材复制；preset_id是版本化预设ID |
| GET/POST `/api/automation/schedules`、PATCH `/{id}` | ADMIN写；明确商品/店铺ID、每日时间、IANA时区；默认停用 |
| POST `/api/legacy-external/{id}/verify` | REVIEWER/ADMIN读取权威状态，保留核查原因；未知历史阻止重复建稿 |
| GET `/api/audit`、`/api/migration/reports` | 审计 / ADMIN迁移报告 |

发布示例：

```json
{"productIds":[7],"storeIds":[3],"targetAction":"CREATE_DRAFT","requestKey":"client-unique-request-123"}
```

目标固定`CREATE_DRAFT`或`PUBLISH`。同键不同参数409；相同目标复用任务。商品的`platform_payload`必须保存经核对的平台线协议对象，包含真实`cid`、按顺序的6个HTTPS图片URL及`skuMap`，不自动猜测属性/包装。TEMU创建时包为`siteCollectItemInfo`；AliExpress走独立配置路径，禁止落入TEMU分支或冒充本地包为线上结果。

所有新上传素材保留原始字节及标准PNG，金额返回字符串。旧调用脚本需要加入登录/CSRF、使用新版任务响应并检查HTTP状态；不提供匿名写兼容后门。
