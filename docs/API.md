# Flow Console 接口文档

API 默认地址为 `http://127.0.0.1:8000`，JSON 接口使用 `application/json`，上传接口使用 `multipart/form-data`。运行中的 `/docs` 和 `/openapi.json` 是完整契约。

## 统一约定

- 路径统一使用 `/api` 前缀；删除接口一般返回 `204`。
- `product_id`、`store_id`、`draft_id` 是数据库 ID；平台外部 ID 保存在店铺或草稿记录中。
- 平台值：`TEMU`、`ALIEXPRESS`；任务后端：`local`、`celery`。
- 草稿状态：`DRAFT_CREATED`、`PACKAGE_READY`、`PUBLISHING`、`PUBLISHED`、`FAILED`。
- 商品资料、图片、平台英文文案和人工审核未完成时，草稿创建会被阻止。

## 健康、总览与基础数据

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/health` | 服务、数据库和依赖健康检查 |
| GET | `/api/overview` | 工作台汇总统计 |
| GET | `/api/stores` | 店铺列表 |
| GET | `/api/imports` | 导入批次列表 |

## 商品、SKU 与店铺映射

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/api/products` | 按 `platform`、`q`、`status`、`store_id` 查询商品 |
| GET | `/api/products/{product_id}` | 商品详情、SKU、素材、审核和草稿 |
| PATCH | `/api/products/{product_id}` | 更新商品基础资料 |
| DELETE | `/api/products/{product_id}` | 删除商品 |
| POST | `/api/products/bulk-delete` | 批量删除商品 |
| POST | `/api/simple-products` | 保存简化商品和 SKU |
| GET | `/api/products/{product_id}/workflow` | 查看简化工作流状态 |
| PATCH | `/api/skus/{sku_id}` | 更新 SKU |
| POST | `/api/skus/{sku_id}/components` | 添加套装组件 |
| DELETE | `/api/components/{component_id}` | 删除套装组件 |
| POST | `/api/products/{product_id}/listings` | 添加店铺商品映射 |

## 导入与素材

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/api/imports/template` | 下载 Excel 模板 |
| POST | `/api/imports/excel` | 导入 Excel 商品资料 |
| POST | `/api/imports/package` | 导入本地商品包 |
| POST | `/api/imports/finished-images` | 导入成品图工作簿和图片 |
| POST | `/api/imports/finished-images/auto-drafts` | 重试成品图导入后的草稿 |
| POST | `/api/source-assets` | 上传源素材 |
| PUT | `/api/source-assets/{slot}` | 替换指定素材槽位 |
| DELETE | `/api/source-assets/{asset_id}` | 删除源素材 |
| GET | `/api/assets/{asset_id}/content` | 获取素材内容 |

成品图导入支持 `platform=TEMU` 或 `platform=ALIEXPRESS`，两个平台使用独立商品标识。

## 图片与场景任务

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/api/image-provider/status` | 查看图片 Provider 配置 |
| GET | `/api/scene-templates` | 获取场景模板 |
| GET/PATCH | `/api/products/{product_id}/scene-profile` | 读取或更新场景配置 |
| POST | `/api/products/{product_id}/image-batches` | 创建图片批次 |
| GET | `/api/image-batches` | 查询图片批次 |
| GET | `/api/image-batches/{batch_id}` | 查看图片批次详情 |
| POST | `/api/image-jobs/{job_id}/retry` | 重试图片任务 |
| GET | `/api/products/{product_id}/image-readiness` | 查看图片就绪状态 |
| POST | `/api/products/{product_id}/scene-batches` | 创建场景图批次 |
| GET | `/api/scene-batches` | 查询场景批次 |
| GET | `/api/scene-batches/{batch_id}` | 查看场景批次详情 |
| POST | `/api/scene-jobs/{job_id}/retry` | 重试场景任务 |
| POST | `/api/products/{product_id}/generate-all` | 创建全套图片任务 |
| PUT | `/api/generated-assets/{asset_id}` | 替换生成图 |
| DELETE | `/api/generated-assets/{asset_id}` | 删除生成图 |

## 文案与审核

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| POST | `/api/products/{product_id}/listing-copies` | 生成指定平台或全部平台文案 |
| PUT | `/api/listing-copies/{copy_id}` | 保存人工修改后的文案 |
| PUT | `/api/reviews/images/{asset_id}` | 审核图片 |
| PUT | `/api/products/{product_id}/review` | 审核整款商品 |

示例：`POST /api/products/12/listing-copies?platform=ALIEXPRESS`。

## 合规材料

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/api/products/{product_id}/compliance` | 查看商品合规文件 |
| GET | `/api/compliance-library` | 查看可复用材料库 |
| PUT | `/api/products/{product_id}/compliance/{kind}` | 上传 `label`、`reach` 或 `other` |
| POST | `/api/products/{product_id}/compliance/{kind}/reuse/{asset_id}` | 复用已有材料 |
| GET | `/api/products/{product_id}/compliance/files/{asset_id}` | 下载材料 |
| DELETE | `/api/products/{product_id}/compliance/files/{asset_id}` | 删除材料 |

图片会尝试 OCR；PDF 提取前 20 页文字；PPTX 提取文本节点。识别结果只作辅助信息，最终仍需人工核对。

## 妙手、店铺与草稿

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/api/miaoshou/status` | 查看妙手配置和连通性 |
| GET | `/api/miaoshou/category-rules/{cid}` | 查询类目规则 |
| POST | `/api/miaoshou/stores/sync?mode=SEMI` | 同步店铺，支持 `SEMI`、`FULL`、`ALIEXPRESS` |
| DELETE | `/api/stores/{store_id}` | 停用店铺 |
| POST | `/api/products/{product_id}/miaoshou-drafts` | 创建 TEMU 或 AliExpress 草稿 |
| POST | `/api/products/{product_id}/aliexpress-import-package` | 生成 AliExpress 本地导入包 |
| GET | `/api/miaoshou-drafts/{draft_id}/package` | 下载导入包 |

TEMU 发布成功必须经过平台权威状态查询。AliExpress 当前只走草稿或导入包路径，不提供自动发布接口。

## 包装与自动化

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/api/packaging-presets` | 包装图预设列表 |
| PUT | `/api/packaging-presets/{slot}` | 上传包装图预设 |
| DELETE | `/api/packaging-presets/{slot}` | 删除包装图预设 |
| GET | `/api/packaging-presets/{slot}/content` | 获取包装图 |
| PUT | `/api/products/{product_id}/packaging-selection` | 设置商品包装图 |
| PUT | `/api/products/packaging-selection/bulk` | 批量设置包装图 |
| GET | `/api/automation/overview` | 自动化运行概览 |
| POST | `/api/automation/schedules` | 创建计划 |
| PATCH | `/api/automation/schedules/{schedule_id}` | 更新计划 |
| DELETE | `/api/automation/schedules/{schedule_id}` | 删除计划 |
| PUT | `/api/automation/stores/{store_id}` | 更新店铺自动化配置 |
| POST | `/api/automation/runs` | 启动自动化运行 |
| GET | `/api/automation/runs` | 查询运行记录 |
| DELETE | `/api/automation/runs/{run_id}` | 删除运行记录 |

## 典型调用顺序

```text
导入商品 → 校验 SPU/SKU → 上传或生成图片 → 审核图片
       → 生成平台英文文案 → 审核文案/整款 → 同步店铺
       → 创建草稿 → 保存外部 ID → 查询权威状态
```

## 错误处理

常见状态码：`400` 参数错误、`404` 资源不存在、`409` 商品或 SKU 冲突、`413` 文件过大、`422` 校验失败、`500` 服务端异常。FastAPI 错误响应通常包含 `detail` 字段。
