from openpyxl import load_workbook
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

path = "outputs/aliexpress-necklace-template-cn.xlsx"
save_path = "outputs/aliexpress-necklace-template-cn-options.xlsx"
wb = load_workbook(path)
ws = wb[wb.sheetnames[0]]
ws.title = "商品参数与属性"
ws["A1"] = "产品编号"
ws["C1"] = "商品标题"
attrs = wb[wb.sheetnames[1]]
sku = wb[wb.sheetnames[2]]
sku.title = "销售属性_SKU"

catalogs = {}
for row in range(2, attrs.max_row + 1):
    name = attrs.cell(row, 1).value
    values = attrs.cell(row, 4).value
    if name and values:
        parsed = [v.strip() for v in str(values).split(",") if v.strip()]
        if str(name) in {"金属类型", "风格", "链类型", "形状\\图案", "认证"}:
            parsed.insert(0, "全选")
        catalogs[str(name)] = parsed

if "选项字典" in wb.sheetnames:
    del wb["选项字典"]
options = wb.create_sheet("选项字典")
options.sheet_state = "hidden"
for col, (name, values) in enumerate(catalogs.items(), 1):
    options.cell(1, col, name)
    for row, value in enumerate(values, 2):
        options.cell(row, col, value)
    letter = get_column_letter(col)
    dv = DataValidation(type="list", formula1=f"'选项字典'!${letter}$2:${letter}${len(values)+1}", allow_blank=True)
    dv.error = "请从妙手可选值中选择"
    dv.errorTitle = "无效属性值"
    dv.prompt = "单选属性直接选择；多选属性请用逗号分隔填写"
    dv.promptTitle = "速卖通类目属性"
    attrs.add_data_validation(dv)
    dv.add(f"B{row}:B{max(attrs.max_row, 200)}")

# Keep a practical multi-select editor: dropdown supplies options and the
# adjacent note documents comma-separated values for multi-select fields.
attrs.cell(1, 6, "选择方式")
attrs.cell(1, 6).font = Font(color="FFFFFF", bold=True)
attrs.cell(1, 6).fill = PatternFill("solid", fgColor="176B4A")
multi = {"金属类型", "风格", "链类型", "形状\\图案", "认证"}
for row in range(2, attrs.max_row + 1):
    name = str(attrs.cell(row, 1).value or "")
    attrs.cell(row, 6, "多选/全选：用逗号分隔" if name in multi else "单选")
    attrs.cell(row, 6).alignment = Alignment(vertical="center", wrap_text=True)
attrs.column_dimensions["F"].width = 24

# Merge the two visible pages into one worksheet: basic information stays at
# the top (required by the finished-folder importer), followed by attributes.
start_row = ws.max_row + 3
for row in attrs.iter_rows():
    for cell in row:
        target = ws.cell(start_row + cell.row - 1, cell.column, cell.value)
        if cell.has_style:
            target._style = cell._style
        if cell.number_format:
            target.number_format = cell.number_format
for width in range(1, attrs.max_column + 1):
    letter = get_column_letter(width)
    if attrs.column_dimensions[letter].width:
        ws.column_dimensions[letter].width = max(ws.column_dimensions[letter].width or 0, attrs.column_dimensions[letter].width)
for col, (name, values) in enumerate(catalogs.items(), 1):
    letter = get_column_letter(col)
    shifted = DataValidation(type="list", formula1=f"'选项字典'!${letter}$2:${letter}${len(values)+1}", allow_blank=True)
    shifted.error = "请从妙手可选值中选择"; shifted.errorTitle = "无效属性值"
    shifted.prompt = "单选属性直接选择；多选属性请用中文顿号分隔"
    ws.add_data_validation(shifted)
    shifted.add(f"B{start_row+1}:B{start_row+attrs.max_row-1}")
if attrs.title in wb.sheetnames:
    del wb[attrs.title]

# SKU metal colors are selectable from the full catalog captured in the UI.
color_values = ["红棕色","浅金色","镀枪色","蓝锌","深金色","铜色","钻紫","铁锈红","金色","镀铬","镀银","仿白金","浅黄色","足金色","玫瑰金色","镀黑枪","镀古青铜","镀古红铜","镀黑锌","镀蓝锌","镀蓝白锌","镀白金","镀钛","镀古金","镀古银","香槟金","镀黄铜","粉红色","红色","蓝色","绿色","紫色","多色"]
col = len(catalogs) + 2
options.cell(1, col, "金属颜色")
for r, value in enumerate(color_values, 2): options.cell(r, col, value)
letter = get_column_letter(col)
dv = DataValidation(type="list", formula1=f"'选项字典'!${letter}$2:${letter}${len(color_values)+1}", allow_blank=True)
# The SKU table is intentionally blank: SKU rows and images are discovered
# from the uploaded 成品 folder, matching the TEMU finished-upload workflow.
for row in range(2, sku.max_row + 1):
    for cell in sku[row]:
        cell.value = None
sku["A2"] = "无需填写；上传成品文件夹后系统自动识别 SKU 与图片"
sku.merge_cells(start_row=2, start_column=1, end_row=2, end_column=14)
sku.add_data_validation(dv); dv.add("C3:C200")

try:
    wb.save(path)
    save_path = path
except PermissionError:
    wb.save(save_path)
print(save_path)
