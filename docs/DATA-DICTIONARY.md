# 数据字典与约束

数据库使用Flyway `server/src/main/resources/db/migration/`。表名为新版单数命名；金额`DECIMAL(24,8)`，Java `BigDecimal`，JSON接口返回十进制字符串。超过精度的输入拒绝，不静默舍入。

| 表 | 作用与关键约束 |
|---|---|
| app_user | username唯一、BCrypt、ADMIN/OPERATOR/REVIEWER、active、auth_version |
| product | spu_code唯一、content_version、价格/库存、content_json保留商品事实、updated_by、软归档 |
| sku | sku_code全局唯一、product_id外键、数量/价格/库存；禁止跨SPU迁移归属 |
| component | SKU外键、组件编码/数量、(sku_id,component_code)唯一 |
| store | 平台、模式、真实授权ID、配置版本；content_json不接收密钥 |
| asset | 商品与可选SKU、槽位、来源、版本、存储键、SHA-256、尺寸、元数据；素材只追加新版本 |
| packaging_preset | 槽位与版本唯一、团队包装预设；应用时复制到商品，停用不删除历史 |
| listing_copy | 商品×平台唯一；事实模板或人工编辑，不宣称LLM文案 |
| review | 批准版本、稳定指纹、审核人、决定和备注；历史自动确认须重审 |
| import_batch | 总行数、有效行、出错行去重数、错误项数与详细问题 |
| publish_batch / batch_task | 发起人、目标与商品×店铺分母；关联复用任务 |
| publish_request | 客户端请求键唯一、参数指纹、任务ID |
| publish_batch_request | 整批请求键唯一；绑定规范化商品/店铺/版本/动作，重试复用整个批次 |
| publish_task | 商品×店铺×版本×动作唯一；不可变快照、外部ID、阶段、状态、次数、owner与租约、next_run_at |
| publish_attempt | 阶段、起止时间、HTTP码、脱敏响应和错误；不是成功数 |
| outbox_event | event_id唯一、投递状态/次数/租约；只有confirm且无return才SENT |
| local_package | PACKAGE_READY、本地ZIP及哈希；与线上任务分表 |
| image_operation | 输入素材与参数哈希、jobId唯一、实际产物与证据；模型未知结果禁止自动重复收费请求 |
| automation_schedule | 时间/时区、明确商品与店铺、动作；每日日期认领与批次创建同事务；新建默认停用 |
| audit | 操作人、动作、对象、原因和时间；不记录密码或密钥 |
| legacy_record | 所有旧表原ID和脱敏JSONL记录，完整保留未结构化字段 |
| legacy_id_map | 旧表+原ID到新版实体映射，素材/SKU绑定可追溯 |
| legacy_external | 原外部ID与原状态独立保留，默认HISTORICAL_UNVERIFIED，不自动重放 |
| migration_run | 导出manifest哈希与验证报告，防止重复迁移 |

任务索引覆盖`(status,next_run_at,id)`、`(batch_id,id)`和`external_id`。Outbox同样具有到期扫描索引。查询和调度不依赖JSON全文扫描。

文件使用随机名，原上传字节另存不可覆盖副本，标准展示产物为PNG。文件按数据库ID下载并检查会话、商品和路径；禁止路径越界和符号链接逃逸。旧WebP只读保留，Java不能解码时明确拒绝转换。无任意远程取图接口：模型仅接受内嵌b64结果，不抓取用户或模型返回的URL。
