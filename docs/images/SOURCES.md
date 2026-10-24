# 演示截图来源

2026-10-12（上海时区），真实 Edge 无头浏览器，1440×1000，Next.js production build + 本地 Uvicorn / 独立 SQLite。

- `workbench.png`：商品资料与素材区的视口截图。
- `workbench-full.png`：同一页面的完整工作台截图。
- 商品 `EVIDENCE-DEMO` 与 PNG 为明确标记的合成测试数据；不声称真实销售、发布或 AI 生图成果。
- 浏览器 JS 错误与水平溢出检查见 [browser-check.json](../evidence/browser-check.json)。
# Java / Vue screenshots

`workbench-java.png`和`workbench-java-mobile.png`由`web/e2e/workbench.spec.js`在隔离MySQL数据库中生成，全部商品为合成验收数据，平台结果来自本地HTTP假服务器；不是生产发布证据。设计沿用旧截图中的深绿、浅色面板与业务顺序。

## 仓库首页展示素材

2026-10-24新增的`repository-cover.svg`为本项目原创矢量封面，PNG由同一SVG在Edge中以2倍像素密度渲染。配色沿用工作台的深绿与浅绿，未复制参考项目的品牌图形。

`showcase-workbench.png`、`showcase-import.png`、`showcase-tasks.png`和`showcase-mobile.png`使用真实Vue组件和显式合成的浏览器API数据。演示商品、店铺、导入记录和任务状态均在脚本中声明，**只用于界面展示，不是平台运行证据**。截图未修改业务页面的DOM、CSS或状态文案。

复现方式（先安装`web/`依赖和Playwright浏览器）：

```bash
npm --prefix web run dev -- --port 3100
# 另一个终端
node scripts/capture-repository.cjs http://127.0.0.1:3100
```

脚本拦截全部`/api/`读取，只接受声明的演示数据，拒绝写请求。无需启动Java或数据库，不连接真实店铺。历史截图和既有测试证据保留原路径与说明。
