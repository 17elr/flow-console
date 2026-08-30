# Flow Console 开发指南

本文面向需要在 Windows 上安装、调试和扩展 Flow Console 的开发者。业务交接与平台验证进度另见 [`PROJECT-HANDOFF.md`](../PROJECT-HANDOFF.md)。

## 1. 环境要求

- Windows 10/11 与 PowerShell 5.1 或更高版本
- Python 3.10+
- Node.js 20+ 与 npm
- 可选：Docker Desktop，用于 PostgreSQL、Redis 和 MinIO

首次安装推荐在仓库根目录运行：

```powershell
.\安装环境.cmd
```

它会调用 `setup-delivery.ps1`，创建 `.venv`、安装 API 和 Web 依赖、生成根目录 `.env`，并初始化 SQLite。API 首次启动时会检查 `BiRefNet` 模型；模型约 973 MB，尚未缓存时可能需要较长下载时间。

## 2. 手动安装

需要单独控制依赖时，可执行：

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r .\apps\api\requirements.txt
Copy-Item .\apps\api\.env.example .\.env

Set-Location .\apps\web
npm install
Set-Location ..\..
```

根目录 `.env` 只保存本机配置和密钥，已被 `.gitignore` 排除。不要将真实密钥写入 `.env.example`、代码、测试夹具或日志。

## 3. 启动方式

推荐使用统一脚本：

```powershell
.\scripts\start-dev.ps1
```

脚本会：

1. 检查 `.venv` 和前端依赖；
2. 初始化数据库表；
3. 在 `127.0.0.1:8000` 启动 FastAPI；
4. 在 `127.0.0.1:3000` 启动 Next.js；
5. 将进程、日志和 PID 记录写入 `.runtime/`；
6. 等待 API 和前端健康检查通过后返回。

自定义端口：

```powershell
.\scripts\start-dev.ps1 -ApiPort 8100 -WebPort 3100
```

自定义 API 端口时还要在前端启动前设置 `NEXT_PUBLIC_API_URL`。停止脚本只结束本项目记录且启动时间匹配的进程：

```powershell
.\scripts\stop-dev.ps1
```

## 4. 环境变量

### 本地核心配置

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./data/app.db` | SQLAlchemy 数据库地址 |
| `API_CORS_ORIGINS` | 本地 3000 端口 | 允许访问 API 的前端来源，逗号分隔 |
| `LOCAL_ASSET_ROOT` | `apps/api/data/assets` | 本地素材镜像目录 |
| `STORAGE_BACKEND` | `local` | `local` 或 `s3` |
| `TASK_BACKEND` | `local` | `local` 或 `celery` |
| `LOCAL_IMAGE_WORKERS` | `2` | 本地图片任务并发数 |
| `REMBG_MODEL` | `birefnet-general` | rembg 抠图模型 |
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` | Web 端访问的 API 地址 |

### PostgreSQL、Redis 与对象存储

| 变量 | 用途 |
| --- | --- |
| `REDIS_URL` | Celery/Redis 地址 |
| `S3_ENDPOINT_URL` | S3 兼容服务地址 |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | 对象存储凭据 |
| `S3_BUCKET` / `S3_REGION` | 存储桶与区域 |

启动可选基础设施：

```powershell
docker compose up -d postgres redis minio
```

启用 PostgreSQL 的开发地址：

```text
postgresql+psycopg://commerce:commerce_dev@localhost:5432/commerce
```

`STORAGE_BACKEND=s3` 时，写入会保留本地镜像，并尽力上传远端；远端读取失败会回退到本地副本。

### 图片 Provider

| 变量 | 用途 |
| --- | --- |
| `IMAGE_PROVIDER` | `hensun` 或 `openai` |
| `HENSUN_BASE_URL` / `HENSUN_MODEL` / `HENSUN_API_KEY` | Hensun OpenAI 兼容接口 |
| `OPENAI_BASE_URL` / `OPENAI_IMAGE_MODEL` / `OPENAI_API_KEY` | OpenAI 图片接口 |

没有对应 API Key 时，Provider 会报告未配置，并在联网调用前失败；本地确定性图片处理仍可独立运行。

### 妙手平台

| 变量 | 用途 |
| --- | --- |
| `MIAOSHOU_BASE_URL` | 妙手开放平台根地址 |
| `MIAOSHOU_APP_KEY` / `MIAOSHOU_APP_SECRET` | HMAC 签名凭据 |
| `PUBLIC_ASSET_BASE_URL` | 妙手可通过 HTTPS 访问的图片公开地址 |
| `MIAOSHOU_MIN_REQUEST_INTERVAL` | 同一账号请求的最小间隔秒数，默认 `1.2` |
| `MIAOSHOU_PUBLIC_COLLECT_CREATE_PATH` | AliExpress 公共采集箱创建接口路径 |
| `MIAOSHOU_PUBLIC_COLLECT_CLAIM_PATH` | AliExpress 店铺认领接口路径，可选 |

平台接口路径必须来自当前妙手官方契约或已验证请求，不得从 TEMU 字段猜测。AliExpress 路径仅用于创建草稿和可选认领，不代表允许发布。

## 5. 系统结构

```text
Browser (Next.js)
    |
    | JSON / multipart
    v
FastAPI routes (apps/api/app/main.py)
    |
    |-- import/review/workflow services
    |-- local or Celery image dispatcher
    |-- Miaoshou provider adapter
    v
SQLAlchemy + asset storage
    |-- SQLite or PostgreSQL
    `-- local mirror or S3-compatible storage
```

关键模块：

| 文件 | 职责 |
| --- | --- |
| `apps/api/app/main.py` | HTTP 路由、启动生命周期和 API 契约 |
| `apps/api/app/models.py` | 商品、SKU、素材、审核、店铺、草稿和自动化数据模型 |
| `apps/api/app/importer.py` | Excel 和商品包导入 |
| `apps/api/app/image_pipeline.py` | 确定性图片任务与质检 |
| `apps/api/app/scene_pipeline.py` | 场景图任务编排 |
| `apps/api/app/publishing.py` | 发布门禁、幂等、草稿和状态持久化 |
| `apps/api/app/miaoshou.py` | 妙手签名、店铺同步、TEMU 与 AliExpress 适配 |
| `apps/web/src/components/simple-workbench.tsx` | 主工作台和草稿创建入口 |
| `apps/web/src/components/automation-console.tsx` | 自动化配置和运行记录 |

## 6. 关键工作流与状态

商品进入草稿创建前，必须满足资料完整、图片齐全、图片审核通过、对应平台英文文案审核通过、整款审核通过。发布层使用幂等键避免同一商品、店铺和输入版本重复创建。

常见草稿状态：

| 状态 | 含义 |
| --- | --- |
| `DRAFT_CREATED` | 平台已返回草稿外部 ID |
| `PACKAGE_READY` | 只生成了可下载的 ZIP 导入包，不等于线上草稿 |
| `PUBLISHING` | 发布任务已被接受或仍在等待权威状态确认 |
| `PUBLISHED` | 权威平台查询已命中发布结果 |
| `FAILED` | 创建、认领、发布或验证失败，错误已持久化 |

不要根据异步请求的成功响应直接写入 `PUBLISHED`。

## 7. 数据库与迁移

开发启动脚本会通过 SQLAlchemy `create_all` 保证本地表存在。需要验证正式迁移链时，在 API 目录运行：

```powershell
Set-Location .\apps\api
& ..\..\.venv\Scripts\python.exe -m alembic upgrade head
& ..\..\.venv\Scripts\python.exe -m alembic current
```

修改模型时应新增 Alembic revision，不要改写已经使用过的历史迁移。数据库文件位于 `apps/api/data/`，属于本地运行数据，禁止提交、清理或用空库覆盖。

## 8. 测试与质量检查

后端：

```powershell
Set-Location .\apps\api
& ..\..\.venv\Scripts\python.exe -m pytest -q
& ..\..\.venv\Scripts\python.exe -m compileall app tests
```

前端：

```powershell
Set-Location .\apps\web
npm run lint
npm run build
```

平台适配改动至少覆盖 `test_miaoshou.py` 和 `test_publishing_automation.py`。真实平台验证必须使用受控商品，并记录外部草稿 ID、响应和人工核对结果；AliExpress 验证不得执行发布。

## 9. 常见问题

### 启动提示缺少虚拟环境或前端依赖

重新运行 `.\安装环境.cmd`，或按“手动安装”章节补齐依赖。已有安装不需要因为代码更新而重复安装，除非依赖清单发生变化。

### 端口被占用

先运行 `.\scripts\stop-dev.ps1`。如果占用者不是本项目，使用 `-ApiPort` 和 `-WebPort` 选择新端口，并同步设置前端 API 地址。

### API 或前端未就绪

查看 `.runtime/api.err.log`、`.runtime/api.out.log`、`.runtime/web.err.log` 和 `.runtime/web.out.log`。安装阶段错误记录在根目录 `install.log`。

### SQLite 文件被占用或数据异常

先停止 API。不要删除数据库来绕过错误；应备份后检查迁移状态、日志和具体异常。

### Excel 生成报 `EBUSY`

关闭正在占用目标文件的 WPS/Excel，再重新运行模板脚本。修改模板时应同时核对表头、下拉验证、选项映射和新增列的格式范围。

## 10. 提交约定

1. 保持改动集中在对应模块，不提交本地数据或凭据。
2. 先运行相关后端测试；改动前端时再运行 lint 和 build。
3. 平台状态必须按可验证证据命名，避免把“请求已接受”描述成“已经发布”。
4. 推送前检查 `git status` 和暂存区，确认 `.env`、数据库、素材与日志均未进入提交。
