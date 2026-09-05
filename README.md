# Flow Console

面向女士饰品电商运营的本地上架工作台。Flow Console 将商品资料导入、SPU/SKU 校验、商品图处理、英文文案审核、店铺草稿创建和自动化运行记录集中在一个 Windows 桌面工作流中。

> 当前仓库按本地单机环境设计。TEMU 流程已包含草稿、认领、库存保存、发布和权威状态核验；AliExpress 已实现公共采集箱创建与店铺认领代码路径，但真实副作用调用仍需在受控商品上验证。AliExpress 默认只创建草稿，不自动发布。

## 核心能力

- Excel 或商品文件夹导入，支持中英文字段别名和重复 SPU/SKU 更新。
- SPU、可售 SKU、套装组件、包装图和店铺版本的完整数据校验。
- 本地白底图流水线，以及基于 Hensun/OpenAI 兼容接口的场景图能力。
- 图片、英文文案和整款商品三级人工审核门禁。
- 妙手店铺同步、TEMU 草稿/发布闭环、AliExpress 草稿与 ZIP 导入包。
- 手动运行和按时区调度的批量自动化，保留请求、外部 ID 和状态证据。
- SQLite 本地开发；可切换 PostgreSQL、Redis/Celery 和 S3 兼容存储。
- 当前素材存储已切换到新腾讯云 COS 桶 `flow-commerce-assets-1480282320`，公开地址仍为 `https://img.yyjds.site`；旧 COS 历史文件不迁移。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| Web | Next.js 16、React 19、TypeScript、Tailwind CSS 4 |
| API | FastAPI、SQLAlchemy、Pydantic、Alembic |
| 图片 | Pillow、OpenCV、RapidOCR、rembg/BiRefNet |
| 数据与任务 | SQLite/PostgreSQL、进程内任务/Celery、Redis |
| 存储 | 本地文件、S3 兼容对象存储 |
| 外部平台 | 妙手开放平台、TEMU、AliExpress、Hensun/OpenAI 兼容图片 API |

## 快速开始

环境要求：Windows、PowerShell、Python 3.10+、Node.js 20+。Docker 仅在使用 PostgreSQL、Redis 或 MinIO 时需要。

首次安装：

```powershell
.\安装环境.cmd
```

安装脚本会创建 `.venv`、安装前后端依赖、复制 `.env.example` 为根目录 `.env`，并初始化本地 SQLite 数据库。需要外部服务时，再在 `.env` 中填写对应凭据；不要提交该文件。

启动与停止：

```powershell
.\启动系统.cmd
.\停止系统.cmd
```

开发者也可以直接使用：

```powershell
.\scripts\start-dev.ps1
.\scripts\stop-dev.ps1
```

默认地址：

- 工作台：`http://localhost:3000`
- API：`http://127.0.0.1:8000`
- OpenAPI 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`

## 项目结构

```text
flow-console/
|-- apps/
|   |-- api/                 FastAPI、数据模型、平台适配器和测试
|   `-- web/                 Next.js 工作台
|-- docs/                    开发文档
|-- outputs/                 Excel 模板、检查结果和预览产物
|-- scripts/                 开发启停和模板维护脚本
|-- docker-compose.yml       PostgreSQL、Redis、MinIO
|-- PROJECT-HANDOFF.md       当前业务状态与后续验证事项
`-- README.md
```

## 开发与验证

完整的环境变量、架构、数据库迁移、测试和排错说明见 [开发指南](./docs/DEVELOPMENT.md)。

常用验证命令：

```powershell
Set-Location apps/api
& ..\..\.venv\Scripts\python.exe -m pytest -q
& ..\..\.venv\Scripts\python.exe -m compileall app tests

Set-Location ..\web
npm run lint
npm run build
```

模块验收记录见 [模块一](./MODULE-1-ACCEPTANCE.md)、[模块二](./MODULE-2-ACCEPTANCE.md) 和 [模块三至七](./MODULES-3-7-ACCEPTANCE.md)。当前平台衔接状态见 [项目交接](./PROJECT-HANDOFF.md)。

## 数据与安全边界

- `.env`、数据库、素材目录、运行日志、虚拟环境、依赖目录和本地模型均被 Git 忽略。
- 不得虚构商品事实、材质、尺寸、重量、认证、品牌或类目属性；缺少数据时必须阻止草稿创建。
- 异步发布请求被平台接受不等于发布成功。只有权威状态查询命中已发布结果，才能记录为 `PUBLISHED`。
- AliExpress 当前只允许创建草稿；未经明确开发和验证，不得增加自动发布。

本仓库目前为私有项目，未声明开源许可证。
