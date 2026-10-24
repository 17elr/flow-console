"""Produce a reviewable mapping for every actual legacy endpoint method."""
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
paths = json.loads((root / 'docs/migration/legacy-openapi-paths.json').read_text(encoding='utf-8'))['paths']
java = '\n'.join(path.read_text(encoding='utf-8') for path in (root/'server/src/main/java').rglob('*Controller.java'))
java += (root/'server/src/main/java/com/flowconsole/publishing/LegacyResults.java').read_text(encoding='utf-8')
implemented = set()
for match in re.finditer(r'@(Get|Post|Put|Patch|Delete)Mapping\((.*?)\)',java,re.S):
    for path in re.findall(r'"([^"\n]+)"',match[2]):
        normalized = re.sub(r'\{[^}]+\}', '{id}', path)
        implemented.add((match[1].upper(),normalized))

def replacement(method, path):
    normalized = re.sub(r'\{[^}]+\}', '{id}', path)
    if (method.upper(),normalized) in implemented:
        if 'auto-drafts' in path: return '明确拒绝', '409：先人工审核，再POST /api/publish-batches'
        if 'generate-all' in path or 'scene-batches' in path: return '显式替代', 'POST /api/assets/{id}/operations/{jobId}；按实际图像模型/算法配置执行'
        if '/automation/runs' == path and method.upper() == 'GET': return '兼容查询', '返回持久化任务列表；统计按目标动作分离'
        return '保留URL', '新增登录/CSRF/角色；写入后审核失效；字段详见API-JAVA.md'
    if '/miaoshou-drafts' in path: return '持久化任务/包替代', 'POST /api/publish-batches，或GET /api/local-packages/{id}/content'
    if '/automation/' in path:
        return '任务台替代', '/api/publish-tasks、/api/publish-batches、/api/automation/schedules；不删除历史运行证据'
    if path.endswith('/bulk-delete'): return '逐项归档', 'DELETE /api/products/{id}保留文件与历史；Vue不提供无确认批量删除'
    if '/scene-' in path or '/image-batch' in path or '/image-job' in path or path == '/api/scene-templates':
        return '素材操作/实际模型替代', '/api/assets/{id}/transform、/operations/{jobId}、/api/image-operations；旧模板/流水线字段保留legacy_record'
    if '/source-assets/' in path or '/generated-assets/' in path:
        return '追加版本替代', 'POST /api/source-assets、PUT /api/generated-assets/{id}；历史素材不物理删除'
    if '/packaging' in path:
        return '版本化预设', '/api/packaging-presets、/api/products/{id}/packaging-selection；批量入口改为逐项显式选择'
    if path.endswith('/listings'): return '任务创建替代', 'POST /api/publish-batches；不在同步请求内发布'
    if '/miaoshou/category-rules/' in path or '/miaoshou/stores/sync' in path:
        return '显式管理员配置', 'GET /api/miaoshou/status；管理员维护已核对店铺/平台参数，不猜动态契约'
    if '/compliance' in path:
        return '文件/算法操作替代', '/api/products/{id}/compliance、/api/compliance-library、/api/assets/{id}/operations/{jobId}；原文保留'
    return '需适配旧脚本', '改用API-JAVA.md列出的认证接口；不保留匿名写后门'

rows = []
for path, methods in paths.items():
    for method in methods:
        if method.lower() not in {'get','post','put','patch','delete'}: continue
        disposition, note = replacement(method,path)
        rows.append(f'| `{method.upper()} {path}` | {disposition} | {note} |')
text = '# 逐项API迁移对照\n\n来源：实际FastAPI OpenAPI导出。每个旧方法列出保留、兼容或显式替代；URL保留不代表匿名访问或旧副作用继续保留。Java任务创建202，错误返回结构化HTTP状态。\n\n| 旧方法与路径 | 处理 | 新行为 / 对应 |\n|---|---|---|\n'+'\n'.join(rows)+'\n'
(root/'docs/migration/API-MAP.md').write_text(text,encoding='utf-8')
print(f'Mapped {len(rows)} legacy endpoint methods')
