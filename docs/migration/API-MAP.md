# 逐项API迁移对照

来源：实际FastAPI OpenAPI导出。每个旧方法列出保留、兼容或显式替代；URL保留不代表匿名访问或旧副作用继续保留。Java任务创建202，错误返回结构化HTTP状态。

| 旧方法与路径 | 处理 | 新行为 / 对应 |
|---|---|---|
| `GET /api/products/{product_id}/compliance` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `GET /api/compliance-library` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `POST /api/products/{product_id}/compliance/{kind}/reuse/{asset_id}` | 文件/算法操作替代 | /api/products/{id}/compliance、/api/compliance-library、/api/assets/{id}/operations/{jobId}；原文保留 |
| `PUT /api/products/{product_id}/compliance/{kind}` | 文件/算法操作替代 | /api/products/{id}/compliance、/api/compliance-library、/api/assets/{id}/operations/{jobId}；原文保留 |
| `GET /api/products/{product_id}/compliance/files/{asset_id}` | 文件/算法操作替代 | /api/products/{id}/compliance、/api/compliance-library、/api/assets/{id}/operations/{jobId}；原文保留 |
| `DELETE /api/products/{product_id}/compliance/files/{asset_id}` | 文件/算法操作替代 | /api/products/{id}/compliance、/api/compliance-library、/api/assets/{id}/operations/{jobId}；原文保留 |
| `GET /health` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `GET /api/overview` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `GET /api/products` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `GET /api/products/{product_id}` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `DELETE /api/products/{product_id}` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `PATCH /api/products/{product_id}` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `POST /api/products/bulk-delete` | 逐项归档 | DELETE /api/products/{id}保留文件与历史；Vue不提供无确认批量删除 |
| `POST /api/simple-products` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `GET /api/products/{product_id}/workflow` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `POST /api/products/{product_id}/listing-copies` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `PUT /api/listing-copies/{copy_id}` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `PUT /api/reviews/images/{asset_id}` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `PUT /api/products/{product_id}/review` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `PUT /api/source-assets/{slot}` | 追加版本替代 | POST /api/source-assets、PUT /api/generated-assets/{id}；历史素材不物理删除 |
| `DELETE /api/source-assets/{asset_id}` | 追加版本替代 | POST /api/source-assets、PUT /api/generated-assets/{id}；历史素材不物理删除 |
| `POST /api/products/{product_id}/generate-all` | 显式替代 | POST /api/assets/{id}/operations/{jobId}；按实际图像模型/算法配置执行 |
| `PUT /api/generated-assets/{asset_id}` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `DELETE /api/generated-assets/{asset_id}` | 追加版本替代 | POST /api/source-assets、PUT /api/generated-assets/{id}；历史素材不物理删除 |
| `GET /api/miaoshou/status` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `GET /api/miaoshou/category-rules/{cid}` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `POST /api/miaoshou/stores/sync` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `DELETE /api/stores/{store_id}` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `GET /api/automation/overview` | 任务台替代 | /api/publish-tasks、/api/publish-batches、/api/automation/schedules；不删除历史运行证据 |
| `POST /api/automation/schedules` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `PATCH /api/automation/schedules/{schedule_id}` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `DELETE /api/automation/schedules/{schedule_id}` | 任务台替代 | /api/publish-tasks、/api/publish-batches、/api/automation/schedules；不删除历史运行证据 |
| `PUT /api/automation/stores/{store_id}` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `POST /api/automation/runs` | 任务台替代 | /api/publish-tasks、/api/publish-batches、/api/automation/schedules；不删除历史运行证据 |
| `GET /api/automation/runs` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `DELETE /api/automation/runs/{run_id}` | 任务台替代 | /api/publish-tasks、/api/publish-batches、/api/automation/schedules；不删除历史运行证据 |
| `POST /api/products/{product_id}/miaoshou-drafts` | 持久化任务/包替代 | POST /api/publish-batches，或GET /api/local-packages/{id}/content |
| `POST /api/products/{product_id}/aliexpress-import-package` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `GET /api/miaoshou-drafts/{draft_id}/package` | 持久化任务/包替代 | POST /api/publish-batches，或GET /api/local-packages/{id}/content |
| `PATCH /api/skus/{sku_id}` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `POST /api/skus/{sku_id}/components` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `DELETE /api/components/{component_id}` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `POST /api/source-assets` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `GET /api/image-provider/status` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `GET /api/scene-templates` | 素材操作/实际模型替代 | /api/assets/{id}/transform、/operations/{jobId}、/api/image-operations；旧模板/流水线字段保留legacy_record |
| `GET /api/products/{product_id}/scene-profile` | 素材操作/实际模型替代 | /api/assets/{id}/transform、/operations/{jobId}、/api/image-operations；旧模板/流水线字段保留legacy_record |
| `PATCH /api/products/{product_id}/scene-profile` | 素材操作/实际模型替代 | /api/assets/{id}/transform、/operations/{jobId}、/api/image-operations；旧模板/流水线字段保留legacy_record |
| `POST /api/products/{product_id}/scene-batches` | 显式替代 | POST /api/assets/{id}/operations/{jobId}；按实际图像模型/算法配置执行 |
| `GET /api/scene-batches` | 素材操作/实际模型替代 | /api/assets/{id}/transform、/operations/{jobId}、/api/image-operations；旧模板/流水线字段保留legacy_record |
| `GET /api/scene-batches/{batch_id}` | 素材操作/实际模型替代 | /api/assets/{id}/transform、/operations/{jobId}、/api/image-operations；旧模板/流水线字段保留legacy_record |
| `POST /api/scene-jobs/{job_id}/retry` | 素材操作/实际模型替代 | /api/assets/{id}/transform、/operations/{jobId}、/api/image-operations；旧模板/流水线字段保留legacy_record |
| `GET /api/products/{product_id}/image-readiness` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `POST /api/products/{product_id}/image-batches` | 素材操作/实际模型替代 | /api/assets/{id}/transform、/operations/{jobId}、/api/image-operations；旧模板/流水线字段保留legacy_record |
| `GET /api/image-batches` | 素材操作/实际模型替代 | /api/assets/{id}/transform、/operations/{jobId}、/api/image-operations；旧模板/流水线字段保留legacy_record |
| `GET /api/image-batches/{batch_id}` | 素材操作/实际模型替代 | /api/assets/{id}/transform、/operations/{jobId}、/api/image-operations；旧模板/流水线字段保留legacy_record |
| `POST /api/image-jobs/{job_id}/retry` | 素材操作/实际模型替代 | /api/assets/{id}/transform、/operations/{jobId}、/api/image-operations；旧模板/流水线字段保留legacy_record |
| `GET /api/assets/{asset_id}/content` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `POST /api/products/{product_id}/listings` | 任务创建替代 | POST /api/publish-batches；不在同步请求内发布 |
| `GET /api/stores` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `GET /api/imports` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `POST /api/imports/excel` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `POST /api/imports/package` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `POST /api/imports/finished-images` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `POST /api/imports/finished-images/auto-drafts` | 明确拒绝 | 409：先人工审核，再POST /api/publish-batches |
| `GET /api/packaging-presets` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `PUT /api/packaging-presets/{slot}` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `DELETE /api/packaging-presets/{slot}` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `GET /api/packaging-presets/{slot}/content` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `PUT /api/products/{product_id}/packaging-selection` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
| `PUT /api/products/packaging-selection/bulk` | 版本化预设 | /api/packaging-presets、/api/products/{id}/packaging-selection；批量入口改为逐项显式选择 |
| `GET /api/imports/template` | 保留URL | 新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md |
