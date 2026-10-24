# 原功能与新版对应

原基线OpenAPI实际导出63个路径，静态装饰器清单71个方法；完整清单分别见`legacy-openapi-paths.json`、`legacy-inventory.json`。方法和URL变更见`API-MAP.md`。

| 原能力 | Java/Vue对应 | 验证与边界 |
|---|---|---|
| 商品/SPU/SKU、组件 | CatalogService、ProductPanel、SkuComponents | MySQL外键与编码约束；价格BigDecimal；归档保留文件 |
| Excel、文件夹、ZIP | ImportService、ImportPanel | 重复导入不增重复编码，SPU事务，错误行数独立，ZIP越界和解压限制 |
| 成品图快捷入口 | finished-images与六图槽位 | 取消自动批准和自动上架，审核人为显式数据库账号 |
| 原图、成品图、版本 | AssetService、素材网格 | 原上传字节与标准PNG分别保存、SKU独立图、SHA-256 |
| 基础图片处理 | Java ImageIO | 裁剪、缩放、真实尺寸标注，实际解码与像素限制 |
| 模特/场景生图 | Java ImageOperations、ImageTools | 配置后调用实际图像编辑模型；默认关闭，不生成假替代图 |
| OCR / BiRefNet | 可选Python compute-adapter | 内部token+multipart协议；缺模型503；不是Java算法重写 |
| 英文文案 | listing_copy与事实模板/人工编辑 | 文案版本变化重审；未声明LLM |
| 人工审核 | 内容版本+稳定指纹 | 角色与最后修改人隔离；变更失效，发布保存不可变快照 |
| 店铺与模式 | store、AdminPanel | ADMIN写配置，保存即使批准失效；保留原授权ID |
| 店铺同步/类目规则 | PlatformCatalogService、管理员同步入口、类目规则查询 | 保留原妙手读取路径及全/半托管映射；不猜类目及枚举；默认关闭真实调用 |
| TEMU建稿/认领/库存/发布 | PlatformGateway分阶段+TaskExecutor | 本地假平台全链路测试；实际发布默认禁用 |
| AliExpress在线草稿 | 独立配置路径和分支 | 不走TEMU接口，契约缺失409；不支持自动发布 |
| AliExpress本地格式2包 | PackageService、认证下载 | 保留图片、SKU、包装与manifest；PACKAGE_READY单独计数 |
| 包装预设与商品选择 | packaging_preset及版本复制 | 历史预设迁入，上传/停用不覆盖旧版素材 |
| 合规材料与复用 | AssetService、compliance-library | PDF/PPTX真实提取、图片OCR可选；不宣称上传即认证 |
| 自动运行与计划 | 持久化任务、每日时区计划、任务台 | Java worker替代Celery/线程池；历史计划归档，不自动激活 |
| 历史草稿和外部ID | legacy_external、LegacyHistory | 未核验历史阻止重复创建，权威核验保留证据 |
| 运行证据与计数 | 发布目标分离+尝试记录+审计 | 草稿/包/待核验/确认发布分别统计，不改写原证据 |

原场景profile、模板参数与流水线任务的全部旧字段仍在legacy_record中；新版提供显式模型提示词、素材版本与实际请求证据，未逐像素复刻旧场景配置子表。旧批量自动化运行不直接恢复执行，避免重复外部操作。历史AI模型质量、真实平台契约和旧素材包在平台端导入效果需另行授权验收，不用假服务器结果代替。
