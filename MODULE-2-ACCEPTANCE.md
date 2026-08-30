# 模块二验收记录

## 交付范围

- Alembic 向后兼容迁移，保留模块一 SQLite 数据。
- 本地/S3 兼容素材存储，外链镜像含公网校验、20MB、50MP、格式与 SHA-256 限制。
- 数据库持久任务、本地线程池恢复机制，以及 Redis/Celery 分发适配器。
- `AssetVersion`、`SkuAsset`、`ImageBatch`、`ImageJob` 与独立 `image_readiness`。
- SPU 四张确定性图片与每个可销售 SKU 的独立白底图。
- 套装原图优先；没有套装原图时严格按组件和数量排版。
- 画布、白底、主体占比、清晰度、裁切、空图、颜色、文字、水印和分隔线质检。
- `/images` 商品队列、批次进度、结果分区、版本历史、素材补充和失败重试。
- 模块三两个场景图位置保持锁定。

## 自动验收

```text
pytest:                 12 passed
Python compileall:      passed
pip check:              no broken requirements
npm audit:              0 vulnerabilities
ESLint:                 passed
TypeScript:             passed
Next.js production:     passed (/ and /images)
```

测试夹具覆盖 10 个 SPU、35 个 SKU，对应 40 个 SPU 任务和 35 个 SKU 任务；另有本地透明素材真实输出测试，验证四张 SPU 图片、SKU 图片、1024×1024 PNG、纯白角点和 SKU 数据库映射。

## 当前数据迁移

迁移后核对保留：5 个 SPU、7 个 SKU、2 个套装组件、3 个店铺、5 个店铺版本、1 个导入批次。迁移后的数据库副本位于被忽略的 `.runtime/app-after-module2-migration.db`。

## 模型缓存说明

`rembg`、ONNX Runtime 和 RapidOCR 已安装。`birefnet-general` 模型本体约 973MB；默认 GitHub 下载在当前网络不可用，国内镜像支持断点续传。工程测试使用预抠透明夹具，不伪造真实模型集成通过状态。首次处理非透明真实原图前，应完成模型缓存并校验 rembg 内置 MD5：`7a35a0141cbbc80de11d9c9a28f52697`。

## 边界

模块二调用 `gpt-image-2` 次数为 0。Hensun Provider 保留，模特佩戴图和生活场景图等待模块二人工验收后进入模块三。
