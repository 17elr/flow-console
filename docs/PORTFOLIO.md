# 负责模块与关键技术决策

## 个人负责范围

本人主导电商运营工作流需求梳理、模块设计、Next.js 工作台、FastAPI 服务、平台适配、测试与交付文档，使用 AI 辅助编码与排错；贡献方式经本人确认。

| 负责模块 | 代码入口 | 讲解重点 |
| --- | --- | --- |
| 商品和素材导入 | [importer](../apps/api/app/importer.py)、[finished_import](../apps/api/app/finished_import.py) | Excel、SPU/SKU、组件与图片映射、异常记录 |
| 图片与文档处理 | [image_pipeline](../apps/api/app/image_pipeline.py)、[scene_pipeline](../apps/api/app/scene_pipeline.py)、[compliance](../apps/api/app/compliance.py) | 原图版本、指纹去重、质检、OCR 与文件提取 |
| 文案与审核 | [copywriting](../apps/api/app/copywriting.py)、[reviews](../apps/api/app/reviews.py) | 字段核验、审核门禁、失败原因 |
| 平台草稿与自动化 | [publishing](../apps/api/app/publishing.py)、[miaoshou](../apps/api/app/miaoshou.py)、[automation](../apps/api/app/automation.py) | 外部 ID、状态核验、任务恢复、时区排程 |
| 前端与交付 | [components](../apps/web/src/components/)、[tests](../apps/api/tests/)、[scripts](../scripts/) | 工作台、API 契约、启停、诊断与可复现证据 |

## 技术决策

| 决策 | 原因与代价 |
| --- | --- |
| 本地 SQLite 与素材目录为默认 | 降低 Windows 单机交付成本；PostgreSQL、S3 为可选部署路径，不代表全部已实测。 |
| 素材版本、SHA256 与任务状态 | 将重复处理和失败定位落到持久化证据，避免只依赖界面提示。 |
| 后端审核门禁 | 缺少必需字段或审核未通过时阻止草稿创建。 |
| 线程池默认，Celery/Redis 可选 | 小规模本地运行先降低运维负担；高并发能力需另行测量。 |
| 平台确认后才认定发布成功 | 异步接收并不等于线上发布；AliExpress 导入包就绪也不等于线上草稿创建。 |
| 运行证据使用隔离数据库与本地素材 | 能复现导入和素材链路，同时不影响真实业务库、店铺或收费模型。 |

## 可复现证据

- [本地 API 运行记录](demo-run.md)，[机器可读结果](evidence/demo-run.json)，[复现脚本](../scripts/demo_evidence.py)。
- [工作台截图](images/)、[当前架构](architecture-overview.md)、[GitHub Actions](../.github/workflows/ci.yml)。
- [原有平台验证边界](../PROJECT-HANDOFF.md)：本次本地证据不替代真实店铺草稿/发布验收。

## 简历表述

主导 Next.js + FastAPI 电商商品工作台开发，贯通商品/SPU/SKU 导入、素材上传校验、图片任务、文案审核及平台草稿适配流程；通过素材版本、任务状态与外部平台状态核验提升可追踪性，并补充可复现 API 运行证据及前后端 CI。

不将种子商品、合成测试图片或本地运行耗时包装为真实销售规模与效率提升；没有业务原始数据时不写“日上架 1000 件”或“效率提升 50%”。
