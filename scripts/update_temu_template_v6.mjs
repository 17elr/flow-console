import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = "C:/Users/17elr/Documents/New project4";
const inputPath = `${root}/outputs/temu-category-id/TEMU-女士时尚吊坠项链-单页产品参数模板-v3-含类目ID.xlsx`;
const outputDir = `${root}/outputs/temu-template-v6`;
const outputPath = `${outputDir}/TEMU-女士时尚吊坠项链-单页产品参数模板-v6.xlsx`;
const previewDir = `${outputDir}/previews`;

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const product = workbook.worksheets.getItem("商品参数");
const instructions = workbook.worksheets.getItem("填写说明");
const options = workbook.worksheets.getItem("选项表");

// Required before editing an existing formatted workbook: capture the baseline.
const baseline = await workbook.render({ sheetName: "商品参数", range: "A1:AJ8", scale: 1, format: "png" });
await fs.writeFile(`${previewDir}/before-product.png`, new Uint8Array(await baseline.arrayBuffer()));

const response = await fetch("http://127.0.0.1:8000/api/miaoshou/category-rules/29542");
if (!response.ok) throw new Error(`类目规则读取失败: HTTP ${response.status}`);
const ruleResponse = await response.json();
const rulesByName = new Map((ruleResponse.attributes ?? []).map((item) => [item.name, item]));
product.getCell(0, 0).values = [["TEMU 女士时尚吊坠项链 - 单页产品参数 v6"]];

const norm = (value) => String(value ?? "").toLowerCase().replace(/[\s_（）()/:：-]+/g, "");
const multiSuffix = "（多选，用“、”分隔；可填“全选”）";
const birthstoneOptions = [
  "一月生日石", "二月生日石", "三月生日石", "四月生日石",
  "五月生日石", "六月生日石", "七月生日石", "八月生日石",
  "九月生日石", "十月生日石", "十一月生日石", "十二月生日石",
];
const fields = [
  { match: ["镀层", "plating"], rule: "镀层", label: "镀层 Plating" },
  { match: ["镶嵌材质", "inlaymaterial"], rule: "镶嵌材质", label: "镶嵌材质 Inlay Material" },
  { match: ["主体材质", "mainmaterial"], rule: "主体材质", label: "主体材质 Main Material" },
  { match: ["风格", "style"], rule: "风格", label: `风格 Style${multiSuffix}`, multi: true },
  { match: ["佩戴场合", "occasion"], rule: "佩戴场合", label: `佩戴场合 Occasion${multiSuffix}`, multi: true },
  { match: ["适配季节", "season"], rule: "适配季节", label: "适配季节 Season" },
  { match: ["节日", "营销节日", "holiday"], rule: "营销节日", label: `营销节日 Holiday${multiSuffix}`, multi: true },
  { match: ["金属材质", "金属部件材质类型", "materialtypesofmetalparts"], rule: "金属部件材质类型", label: `金属部件材质类型 Material Types of Metal Parts${multiSuffix}`, multi: true },
  { match: ["是否含金属部件", "whetheritcontainsmetalcomponents"], rule: "是否含金属部件", label: "是否含金属部件 Whether it contains metal components" },
  { match: ["诞生石", "birthstone"], rule: "诞生石", label: `诞生石 Birthstone${multiSuffix}`, multi: true },
  { match: ["主题", "theme"], rule: "主题", label: `主题 Theme${multiSuffix}`, multi: true },
  { match: ["品牌名", "brand"], rule: "品牌名", label: "品牌名 Brand（自由填写）", freeText: true },
  { match: ["供电方式", "powersupply"], rule: "供电方式", label: "供电方式 Power Supply" },
  { match: ["系列", "系列线", "collection"], rule: "系列线", label: `系列线 Collection${multiSuffix}`, multi: true },
  { match: ["有无礼盒", "withorwithoutgiftbox"], rule: "有无礼盒", label: "有无礼盒 With Or Without Gift Box" },
];

function findField(header) {
  const key = norm(header);
  return fields.find((field) => field.match.some((alias) => key.includes(norm(alias))));
}

const productValues = product.getRange("A4:AZ200").values;
const productHeaders = productValues[0] ?? [];
for (let col = 0; col < productHeaders.length; col += 1) {
  const header = productHeaders[col];
  if (!header) continue;
  const field = findField(header);
  if (field) {
    product.getCell(3, col).values = [[field.label]];
    for (let row = 4; row < 200; row += 1) {
      const cell = product.getCell(row, col);
      const value = cell.values?.[0]?.[0];
      if (field.rule === "营销节日" && value === "生日") cell.values = [["无"]];
      if (field.rule === "供电方式" && value === "无需供电") cell.values = [["无需供电使用"]];
    }
  }
  if (norm(header) === norm("SKU分类")) {
    for (let row = 4; row < 200; row += 1) {
      const cell = product.getCell(row, col);
      const value = cell.values?.[0]?.[0];
      if (value === "多件混装" || value === "组合装/套装") cell.values = [["混合套装"]];
    }
  }
}

const operationalOptions = [
  { label: "敏感属性", match: ["敏感属性"], values: ["无敏感属性", "纯电", "内电", "磁性", "液体", "粉末", "膏体", "刀具", "其他敏感属性"] },
  { label: "商品类型", match: ["商品类型"], values: ["定制商品", "非定制商品"] },
  { label: "SKU分类", match: ["sku分类"], values: ["单品", "同款多件装", "混合套装"] },
  { label: "外包装类型", match: ["外包装类型"], values: ["硬包装", "软包装+硬物", "软包装+软物"] },
  { label: "外包装形状", match: ["外包装形状"], values: ["不规则", "长方体", "圆柱体"] },
];
const optionColumns = [
  ...fields.filter((field) => !field.freeText).map((field) => ({
    label: field.label,
    match: field.match,
    values: [
      ...(field.multi ? ["全选"] : []),
      ...(field.rule === "诞生石"
        ? birthstoneOptions
        : (rulesByName.get(field.rule)?.values ?? []).map((item) => item.name)),
    ],
  })),
  ...operationalOptions,
];
options.getRange("A4:AZ500").clear({ applyTo: "contents" });
options.getRangeByIndexes(3, 0, 1, optionColumns.length).values = [optionColumns.map((item) => item.label)];
const maxOptionRows = Math.max(...optionColumns.map((item) => item.values.length), 1);
const optionMatrix = Array.from({ length: maxOptionRows }, (_, row) => optionColumns.map((item) => item.values[row] ?? null));
options.getRangeByIndexes(4, 0, maxOptionRows, optionColumns.length).values = optionMatrix;
options.getRangeByIndexes(3, 0, maxOptionRows + 1, optionColumns.length).format.wrapText = true;
try { options.unmergeCells("A1:M1"); } catch {}
try { options.unmergeCells("A2:M2"); } catch {}
options.mergeCells("A1:S1");
options.mergeCells("A2:S2");
options.getRange("A4:S4").format = {
  fill: "#2B75A3",
  font: { color: "#FFFFFF", bold: true },
  wrapText: true,
  verticalAlignment: "center",
};
options.getRange("N4:S500").format.columnWidth = 16;

// Rebind every categorical input to the rebuilt option columns. Multi-select
// columns include a one-click "全选" value and also accept manually separated values.
const refreshedHeaders = product.getRange("A4:AZ4").values[0] ?? [];
for (let productCol = 0; productCol < refreshedHeaders.length; productCol += 1) {
  const header = refreshedHeaders[productCol];
  if (!header) continue;
  const key = norm(header);
  const optionCol = optionColumns.findIndex((item) => item.match.some((alias) => key.includes(norm(alias))));
  if (optionCol < 0) continue;
  const excelCol = (() => {
    let number = optionCol + 1;
    let result = "";
    while (number > 0) {
      number -= 1;
      result = String.fromCharCode(65 + (number % 26)) + result;
      number = Math.floor(number / 26);
    }
    return result;
  })();
  const lastRow = optionColumns[optionCol].values.length + 4;
  const multiField = fields.find((field) => field.match.some((alias) => key.includes(norm(alias))))?.multi;
  product.getRangeByIndexes(4, productCol, 196, 1).dataValidation = {
    rule: { type: "list", formula1: `'选项表'!$${excelCol}$5:$${excelCol}$${lastRow}` },
    ...(multiField ? { showErrorMessage: false, errorStyle: "information" } : {}),
  };
}

// Add a concise instruction without changing the template's existing structure.
const instructionRange = instructions.getUsedRange(true);
const instructionRows = instructionRange?.values ?? [];
const noteRow = Math.max(instructionRows.length, 5);
instructions.getCell(noteRow, 0).values = [["多选属性填写"]];
instructions.getCell(noteRow, 1).values = [["标注“多选”的字段保留下拉选项，同时允许在同一格填写多个值；请使用中文顿号“、”分隔（例如：优雅、可爱、派对），需要选择全部妙手选项时填写“全选”。品牌名为自由填写。"]];
instructions.getRangeByIndexes(noteRow, 0, 1, 2).format.wrapText = true;

product.freezePanes.freezeRows(4);
options.freezePanes.freezeRows(4);

const keyInspect = await workbook.inspect({
  kind: "table",
  range: "商品参数!A4:AJ7",
  include: "values,formulas",
  tableMaxRows: 4,
  tableMaxCols: 36,
  maxChars: 12000,
});
await fs.writeFile(`${outputDir}/inspection.ndjson`, keyInspect.ndjson, "utf8");

const errorScan = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
await fs.writeFile(`${outputDir}/formula-errors.ndjson`, errorScan.ndjson, "utf8");

for (const [sheetName, range] of [["商品参数", "A1:AJ8"], ["填写说明", "A1:H16"], ["选项表", "A1:S35"]]) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(`${previewDir}/${sheetName}.png`, new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath, sheets: ["商品参数", "填写说明", "选项表"], relevantAttributeCount: fields.length }));
