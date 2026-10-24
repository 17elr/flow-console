# 非破坏性迁移与回退

先导出和校验，不写旧SQLite或覆盖旧素材。原ID、金额字符串、外部ID和原状态保留；未知历史结果不会自动重放。完整旧表归档于`legacy_record`，结构化映射见`legacy_id_map`。

## 只读导出

关闭旧应用写入后，使用新的输出目录：

```bash
python migration/export_legacy.py --database apps/api/data/app.db --assets apps/api/data/assets --compliance apps/api/data/compliance --output .runtime/migration-20261024
```

导出通过SQLite只读事务生成一致性私有快照、每表JSONL、行数、外键及文件SHA-256清单。文件只复制。输出目录必须全新，不能覆盖已有备份。JSONL敏感字段脱敏；私有SQLite快照仍属于敏感本地备份，不放Git或普通报告。

浮点金额导出十进制字符串，并在manifest报告与IEEE754二进制的差异；Java/MySQL只接受声明精度，不静默四舍五入。原文件哈希不一致就中止。旧路径缺失时，只允许用清单中SHA-256完全相同的文件恢复独立副本，并写入恢复记录。

如果原系统使用S3而本地镜像缺失，可使用可选`migration/recover_remote_assets.py`，用原有只读凭据将缺失对象GET到全新overlay目录。它不会PUT/DELETE，不打印凭据，且必须匹配数据库中的SHA-256。再以`export_legacy.py --extra-assets <overlay>`生成一份新的完整导出；不要修改原备份manifest或把下载副本写回原素材目录。此可选工具需要旧Python环境中的boto3/python-dotenv，Java运行不依赖它们。

## 导入独立MySQL

先创建全新`flow_migration_<name>`数据库。migration profile在校验数据库名后才运行Flyway；拒绝flow_console等普通业务库。配置`DB_URL/USER/PASSWORD`指向该独立库、`ASSET_ROOT`指向新素材目录。

```bash
java -jar server/target/flow-console-2.0.0.jar --spring.profiles.active=migration --flow.migration-path=.runtime/migration-20261024
```

先校验每个JSONL的行数及哈希、全部文件哈希和外键检查，再按关系导入。产品、SKU、组件、店铺保留原ID；素材、SKU绑定、文案、包装选择、审核和历史外部结果保存映射。重复导入同manifest不重复写入，非空新目标拒绝覆盖。

所有旧字段另保存在原表JSON中。旧自动确认标记`LEGACY_AUTO_APPROVED`，没有可验证身份的旧人工记录标记`LEGACY_REVIEW_UNVERIFIED`；不编造审核人，重新人工审核。旧任务与计划不自动恢复执行，原运行记录保留归档；新每日计划需要管理员明确建立或启用。

历史外部ID与原状态保存在`legacy_external`。没有新权威核验前统一`HISTORICAL_UNVERIFIED`，有重复上架风险的记录阻止新建线上任务。人工查清真实ID后只能查询权威状态，不能直接点击“标记成功”。

验证报告写入`mysql-validation-<数据库名>.json`，SQL事务提交后才落盘。核对：源/归档行数、核心实体原ID、SKU归属、金额精确比较、素材SHA、包装/SKU映射、历史外部ID与零任务重放。缺失或异常保留在报告，不偷偷生成替代内容。

## 回退检查与正式切换

```bash
python migration/verify_rollback.py --database apps/api/data/app.db --export .runtime/migration-20261024 --assets apps/api/data/assets --compliance apps/api/data/compliance --report .runtime/rollback-check.json
```

该检查以只读方式比较原SQLite和快照逐表记录、外键及全部复制素材哈希；不代表已经切换生产。原应用入口、SQLite和素材目录必须保留到验收完成。

正式切换前停止旧写进程，冻结原SQLite；新API和worker指向通过校验的独立MySQL库和新素材副本。先验证登录、资料、审核、下载和未配置平台的拒绝行为，再另行授权受控商品验证真实平台。切换后不要同时启动旧应用写同一业务数据。

需要回退时先停止Java API/worker，保留新MySQL与素材卷，再恢复原版本入口和保留的数据副本。若切换后已产生新业务写入，先导出新增记录并制定显式回迁，不把旧SQLite覆盖到新MySQL，也不把回退当成删除新数据。

本次仓库改造只在独立库完成迁移与只读回退检查，未替换本机原业务数据库。原入口与原数据仍在。
