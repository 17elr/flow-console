# AI 电商自动化系统

当前交付范围包含模块一“商品与 SKU 资料中心”和模块二“确定性商品图与 SKU 白底图”。模块二使用本地 `rembg`、Pillow 与 RapidOCR，不调用 `gpt-image-2`；模特佩戴图和生活场景图留到模块三。

## 本地启动（SQLite）

SQLite 是默认开发模式，不需要 Docker。

推荐使用项目启动脚本，它会检查 API 和前端健康状态，并将日志与进程记录写入被忽略的 `.runtime` 目录：

```powershell
$repoRoot = "C:\Users\17elr\Documents\New project4"
Set-Location $repoRoot
& ".\scripts\start-dev.ps1"
```

停止本项目记录的开发进程：

```powershell
& ".\scripts\stop-dev.ps1"
```

也可以分别手动启动：

```powershell
$repoRoot = "C:\Users\17elr\Documents\New project4"

Set-Location "$repoRoot\apps\api"
& "$repoRoot\.venv\Scripts\python.exe" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
& "$repoRoot\.venv\Scripts\python.exe" -m alembic upgrade head
& "$repoRoot\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另开一个 PowerShell 窗口启动前端：

```powershell
$repoRoot = "C:\Users\17elr\Documents\New project4"
Set-Location "$repoRoot\apps\web"
npm install
npm run dev
```

- 前端商品资料：`http://localhost:3000`
- 前端图片流水线：`http://localhost:3000/images`
- API：`http://127.0.0.1:8000`
- API 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`

## 可选基础设施（Docker）

```powershell
docker compose up -d postgres redis minio
```

启用 PostgreSQL 时，将 API 的 `DATABASE_URL` 设置为：

```text
postgresql+psycopg://commerce:commerce_dev@localhost:5432/commerce
```

未设置 `DATABASE_URL` 时继续使用 `apps/api/data/app.db`。默认使用本地文件存储和进程内持久任务；设置 `STORAGE_BACKEND=s3` 和 `TASK_BACKEND=celery` 后可切换到 MinIO 与 Redis/Celery，API 契约不变。

## Excel 导入

在页面右上角选择“下载模板”，填写后通过“导入 Excel”上传。模板本身包含一套完全有效的演示数据，可直接回传验证。

工作表说明：

| 工作表 | 用途 | 关键字段 |
| --- | --- | --- |
| `Products` | SPU 商品母版 | `spu_code`、`title`、`category`、`material`、`source_image_url`、`image_rights` |
| `SKUs` | 可销售 SKU | `spu_code`、`sku_code`、`color`、`size`、`quantity`、`source_image_url` |
| `Components` | 套装组合矩阵 | 父 `sku_code`、`component_code`、`component_name`、`component_quantity` |
| `StoreListings` | 店铺发布版本 | `spu_code`、`store_name`、`platform`、`mode`、`price` |

标准英文列名和中英文字段别名均可识别。单品 SKU 必须有专属原图；套装 SKU 可使用套装原图，也可以由完整组件原图与数量矩阵组成。缺失真实素材时系统进入待补资料，不会猜测生成图片。重复导入相同 SPU/SKU 会更新现有记录。

## 确定性图片流水线

- 每款商品生成白底主图、两张独立细节图和一张尺寸信息图。
- 每个可销售 SKU 生成一张独立白底图，套装严格按组件编码和数量自然排列。
- 输出统一为 1024×1024 PNG；输入素材与输出记录 SHA-256、尺寸、角色、存储键、版本和质检结果。
- 相同输入指纹重复提交返回原批次，只有 `force=true` 才创建新版本。
- 默认素材目录是 `apps/api/data/assets`，只能通过受控 API 读取。

`birefnet-general` 首次使用需要下载约 973MB 的模型到 `%USERPROFILE%\.u2net\birefnet-general.onnx`。预抠透明 PNG 会跳过模型推理；模型下载失败不会触发任何生成式 AI 调用。

## 验证命令

```powershell
$repoRoot = "C:\Users\17elr\Documents\New project4"

Set-Location "$repoRoot\apps\api"
& "$repoRoot\.venv\Scripts\python.exe" -m pytest -q
& "$repoRoot\.venv\Scripts\python.exe" -m compileall app tests

Set-Location "$repoRoot\apps\web"
npm audit
npm run lint
npm run build
```

详细验收记录见 [MODULE-1-ACCEPTANCE.md](./MODULE-1-ACCEPTANCE.md) 和 [MODULE-2-ACCEPTANCE.md](./MODULE-2-ACCEPTANCE.md)。
