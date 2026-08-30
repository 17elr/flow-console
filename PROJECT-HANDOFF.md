# Flow Console 项目交接

更新时间：2026-08-29

## 1. 项目目标

为女士饰品提供本地 PC 上架工作台：导入 Excel 和成品图，严格匹配 SPU/SKU，审核图片与英文文案后，通过妙手为 TEMU 或速卖通创建商品草稿。当前新增目标是在原有网页中支持速卖通在线创建草稿；速卖通自动上架暂不开发。

## 2. 当前目录结构

```text
New project4/
├─ apps/api/       FastAPI 后端、数据库模型、妙手适配、测试
├─ apps/web/       Next.js 前端与现有商品工作台
├─ scripts/        本地启停与 Excel 模板脚本
├─ outputs/        Excel 模板、预览和验收产物
├─ .env            本机密钥与存储配置，禁止提交或输出
└─ PROJECT-HANDOFF.md
```

## 3. 已完成的功能

- Excel/文件夹导入、SPU/SKU/包装图匹配、六张主图排序、每个 SKU 独立图片、人工审核和平台英文文案确认。
- TEMU 妙手闭环：创建草稿、认领、保存 SKU 库存、发布，并以妙手 `published` 查询作为最终成功依据。
- 腾讯云 COS 已通过境外 CDN 域名 `https://img.yyjds.site` 提供 HTTPS 图片；15 张发布图片已验证为 `200 image/jpeg`。
- TEMU 实际发布已成功：妙手草稿外部 ID `3327429955`，平台产品 ID `1512257867`，本地状态已核验为 `PUBLISHED`。
- 速卖通店铺同步识别、独立英文文案、类目属性工作表、SKU/图片 ZIP 导入包已经存在。
- 妙手后台已授权速卖通店铺：`cn1082498068kyrae`，店铺 ID `3000004224068`，模式 `POP`。

## 4. 正在开发的功能

- 在现有 Flow Console 网页中显示并选择上述速卖通店铺。
- 将速卖通从当前 `PACKAGE_READY`（生成 ZIP 手工导入）升级为调用妙手开放 API 在线创建草稿，行为与 TEMU 的“仅创建草稿”一致。
- 草稿需携带真实标题、描述、速卖通类目属性、SPU/SKU、价格、库存、尺寸重量、六张主图、SKU 图和包装图。
- 本阶段只创建草稿并保存妙手外部 ID/响应；不认领、不发布、不新增速卖通自动上架开关。

## 5. 关键技术栈

- 前端：Next.js、React、TypeScript、lucide-react。
- 后端：FastAPI、SQLAlchemy、Alembic、Pydantic、pytest。
- 存储与图片：本地镜像、腾讯云 COS/CDN、Pillow。
- 外部系统：妙手开放平台、TEMU、AliExpress；Hensun/OpenAI 兼容图像接口。

## 6. 重要文件说明

- `apps/api/app/miaoshou.py`：妙手签名、店铺同步及平台 API；需新增速卖通草稿适配，不能复用 TEMU 专属路径和字段假设。
- `apps/api/app/publishing.py`：统一草稿入口；当前 TEMU 调 API，速卖通落入 ZIP `PACKAGE_READY` 分支，是主要改造点。
- `apps/api/app/main.py`：店铺同步和草稿 API；已能将平台识别为 `ALIEXPRESS`/`POP`。
- `apps/web/src/components/simple-workbench.tsx`：现有商品工作台、店铺选择、文案审核和创建草稿入口；新功能必须加在此页面，不另建独立站点。
- `apps/api/tests/test_miaoshou.py`、`test_publishing_automation.py`：妙手契约、草稿状态和回归测试重点。

## 7. 已知问题

- 当前 `MiaoshouProvider` 仅实现 TEMU 全/半托管 API；速卖通在线草稿接口路径、请求字段、类目 ID/属性 ID 和响应外部 ID 尚未从妙手官方契约确认，禁止凭 TEMU 格式猜测。
- 速卖通当前只生成 Excel/ZIP 导入包并标记 `PACKAGE_READY`，不代表妙手后台已有草稿。
- 店铺同步接口按 `FULL`/`SEMI` 拉取，需确认新速卖通授权能被现有同步结果返回并正确持久化；不要仅依据截图假定本地已有 Store 记录。
- 免费 SSL 证书有效期 90 天；CDN/COS/HTTPS 按实际用量可能计费。
- 工作区大部分文件未跟踪且含数据库、图片、Excel、密钥和模型，禁止清理或重置。

## 8. 下一步要做什么

1. 同步妙手店铺并确认本地 Store：平台 `ALIEXPRESS`、模式 `POP`、外部 ID `3000004224068`。
2. 从妙手开放平台官方文档或真实请求样例确认速卖通“创建商品草稿”接口、类目/属性/SKU/图片字段及成功响应；实现独立 provider adapter。
3. 在 `create_store_drafts` 中新增速卖通 API 分支，复用审核、幂等、CDN JPEG 和数据库状态框架；成功状态为 `DRAFT_CREATED`，保留 ZIP 作为明确的降级/下载能力。
4. 更新原网页的店铺与结果展示，速卖通按钮文案明确为“创建草稿”，隐藏/禁用自动发布。
5. 增加单元测试后，用一个已审核 SPU 创建真实速卖通草稿，人工核对主图、SKU 图、属性、价格和库存；不得执行上架。

## 9. 不能改动/需要注意的约束

- 不输出或提交 `.env`、AppKey、AppSecret、COS 密钥、证书私钥和用户密码。
- 不虚构商品、SKU、材质、尺寸、重量、认证、品牌或类目属性；缺数据必须阻止草稿创建并提示补充。
- 主图严格按上传顺序；`sku/` 仅用于 SKU 图片；每个可售 SKU 必须有独立图片。
- 人工审核和对应平台英文文案未通过时不得创建草稿。
- 速卖通本阶段默认且只能创建草稿，不得认领、发布或自动上架。
- API 异步任务被接受不等于成功；必须保存外部 ID 和真实响应，状态名称不得夸大。
- 不删除数据库、图片、Excel、历史草稿、用户未跟踪文件；不破坏已验证的 TEMU 流程。
