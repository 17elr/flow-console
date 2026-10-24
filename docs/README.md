# 文档中心

[返回项目首页](../README.md) · [查看界面预览](../README.md#preview) · [GitHub Actions](https://github.com/17elr/flow-console/actions/workflows/java-vue.yml)

**第一次使用，从运行手册开始；想理解可靠发布，先读架构与状态图。**

## 运行与使用

| 你想做什么 | 阅读这里 |
| --- | --- |
| 启动工作台、配置账号、停止服务 | [运行手册](RUNBOOK.md) |
| 搞清楚商品、素材、审核与任务的业务顺序 | [项目首页](../README.md#workflow) · [功能迁移对照](migration/FEATURE-MAP.md) |
| 查看接口、权限、错误码与典型请求 | [Java API](API-JAVA.md) |
| 迁移旧数据、校验素材、准备回退 | [迁移与回退](MIGRATION.md) |

## 架构与实现

| 主题 | 阅读这里 |
| --- | --- |
| API / worker、Outbox、账号限流与任务状态 | [架构设计](ARCHITECTURE.md) |
| 表结构、唯一约束、版本与原ID映射 | [数据字典](DATA-DICTIONARY.md) |
| 从关键设计找到对应源码和测试 | [实现与测试索引](INTERVIEW.md) |
| 图像模型、OCR与BiRefNet的实际边界 | [可选算法适配器](../compute-adapter/README.md) · [运行手册](RUNBOOK.md#平台与模型) |
| 旧API如何映射到Java版本 | [逐项API对照](migration/API-MAP.md) |

## 验证与视觉

| 主题 | 阅读这里 |
| --- | --- |
| Java、真实中间件、浏览器与迁移检查 | [验收记录](VERIFICATION.md) · [结构化证据](evidence/java-migration-verification.json) |
| 前端复查发现的问题和修复范围 | [UI复查](UI-REVIEW.md) |
| 页面颜色、布局和交互约定 | [界面设计](DESIGN.md) |
| 仓库首页视觉与参考项目 | [仓库展示设计](REPOSITORY-DESIGN.md) |
| 截图如何生成、哪些是演示数据 | [图片来源](images/SOURCES.md) |

## 历史资料

`apps/`保留2026-10-24 Java / Vue改造之前的FastAPI / Next.js实现。旧文档只描述旧版本；当前部署、接口与实现以本页上方的新版文档为准。

- [历史版本说明](LEGACY.md)
- [旧API说明](API.md) · [旧开发指南](DEVELOPMENT.md)
- [旧版演示记录](demo-run.md) · [旧架构概览](architecture-overview.md)

真实平台发布、付费图像模型和实际算法质量的授权验收，与仓库中的合成测试证据分别记录。
