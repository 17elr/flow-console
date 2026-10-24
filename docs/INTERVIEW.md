# 实现与验证索引

这是2026-10-24进行的后续个人Java/Vue改造，不追溯改写企业原始架构、实习工作量或开发时间。不使用合成测试推导日上架量、效率倍数或生产吞吐。

| 可以解释的内容 | 实现 | 证据 |
|---|---|---|
| 同事务任务与Outbox | `TaskService.create/enqueue`、MySQL唯一约束 | `WorkflowIT.concurrentRequestsAndDuplicateMessagesCreateOneExternalDraft` |
| 投递确认与不可路由返回 | `OutboxPublisher.publish` | `WorkflowIT.mysqlOutboxSurvivesUnavailableMqAndChecksRealConfirm`，真实RabbitMQ |
| 外部执行结果不确定 | `TaskExecutor`、`PlatformGateway` | `WorkflowIT.lostExternalResponseNeverBlindlyRecreates`，本地HTTP假平台 |
| 审核与内容版本 | `CatalogService.snapshot/fingerprint/decide/bump` | `WorkflowIT.changedVersionInvalidatesApprovalAndUnsentTask`及浏览器换图用例 |
| 多worker共享配额 | `AccountLimiter`原子Lua、Redis TIME | `WorkflowIT.redisIsSharedAndOfflineStopsAllExternalSending`，真实Redis |
| 旧owner不能覆盖 | `TaskMapper.finish`的owner+lease条件 | `WorkflowIT.expiredLeaseRejectsOldOwnerAndRecoversToVerification` |
| TEMU分阶段提交与核验 | `PlatformGateway.execute`、`TaskExecutor.finish` | `WorkflowIT.temuPublicationChecksClaimStockAndAuthoritativeBucket` |
| AliExpress独立分支 | `PlatformGateway.validate/execute`、`PackageService` | `WorkflowIT.aliexpressUsesSeparateEndpointAndNeverTemuPublish` |
| 安全基础 | `AuthFilter/AuthService`、`AssetService.path/decode` | MockMvc会话/CSRF/角色用例、路径和实际解码测试 |
| 非破坏性迁移 | `migration/export_legacy.py`、`LegacyImporter` | 只读导出测试、独立MySQL演练报告，文件SHA-256与原ID映射 |
| Vue生命周期与错误保留 | `web/src/api.js`、`ProductPanel/TaskPanel` | fetch单测与Playwright真实浏览器验收 |

外部平台接口仍需要在得到真实店铺授权后，用受控商品验证当前契约及发布效果。现有验证使用本地HTTP假服务器，没有调用真实店铺或收费图像模型。可选OCR/BiRefNet的大模型输出也不能用Pillow缩放测试替代验收。
