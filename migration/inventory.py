"""Extract the legacy endpoint/model baseline without importing or starting FastAPI."""
import ast
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
endpoints, models = [], []
for filename in sorted((root / 'apps/api/app').glob('*.py')):
    tree = ast.parse(filename.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr in ('get','post','put','patch','delete') and decorator.args and isinstance(decorator.args[0], ast.Constant):
                    endpoints.append({'method': decorator.func.attr.upper(), 'path': decorator.args[0].value, 'file': filename.relative_to(root).as_posix(), 'handler': node.name})
        if isinstance(node, ast.ClassDef):
            for statement in node.body:
                if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == '__tablename__' for target in statement.targets):
                    models.append({'class': node.name, 'table': ast.literal_eval(statement.value), 'file': filename.relative_to(root).as_posix()})
output = root / 'docs/migration/legacy-inventory.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({'source_commit':'3bc056c375391cdabfd6002246aa3f2485a742ff','endpoints':endpoints,'models':models},ensure_ascii=False,indent=2),encoding='utf-8')
print(f'{len(endpoints)} endpoints; {len(models)} models')
