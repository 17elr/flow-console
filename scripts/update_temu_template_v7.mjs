import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = "C:/Users/17elr/Documents/New project4";
const inputPath = `${root}/outputs/temu-template-v6/TEMU-女士时尚吊坠项链-单页产品参数模板-v6.xlsx`;
const outputDir = `${root}/outputs/temu-template-v7`;
const outputPath = `${outputDir}/TEMU-女士时尚吊坠项链-单页产品参数模板-v7.xlsx`;
const previewDir = `${outputDir}/previews`;

await fs.mkdir(previewDir, { recursive: true });
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const product = workbook.worksheets.getItem("商品参数");
const instructions = workbook.worksheets.getItem("填写说明");
const options = workbook.worksheets.getItem("选项表");

const before = await workbook.render({ sheetName: "商品参数", range: "A1:AJ8", scale: 1, format: "png" });
await fs.writeFile(`${previewDir}/before-product.png`, new Uint8Array(await before.arrayBuffer()));

// Preserve the final column's established format, then append the new field.
product.getRange("AJ1:AJ200").copyTo(product.getRange("AK1:AK200"), "all");
product.getRange("A1").values = [["TEMU 女士时尚吊坠项链 - 单页产品参数 v7"]];
product.getRange("AK4").values = [["SKU是否独立包装"]];
product.getRange("AK5:AK6").values = [["不是独立包装"], ["不是独立包装"]];
product.getRange("AK4:AK200").format.columnWidth = 18;
product.getRange("AK4").format = {
  fill: "#4C7F8F",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
  horizontalAlignment: "center",
  verticalAlignment: "center",
};

options.getRange("T4").values = [["SKU是否独立包装"]];
options.getRange("T5:T6").values = [["是独立包装"], ["不是独立包装"]];
options.getRange("T4:T500").format.columnWidth = 18;
options.getRange("T4").format = {
  fill: "#2B75A3",
  font: { color: "#FFFFFF", bold: true },
  wrapText: true,
  verticalAlignment: "center",
};
product.getRange("AK5:AK200").dataValidation = {
  rule: { type: "list", formula1: "='选项表'!$T$5:$T$6" },
};

const used = instructions.getUsedRange(true)?.values ?? [];
const noteRow = Math.max(used.length, 6);
instructions.getCell(noteRow, 0).values = [["SKU是否独立包装"]];
instructions.getCell(noteRow, 1).values = [["下拉选择“是独立包装”或“不是独立包装”。导入后会写入妙手每个 SKU 的独立包装属性；未填写时按“不是独立包装”处理。"]];
instructions.getRangeByIndexes(noteRow, 0, 1, 2).format.wrapText = true;

const check = await workbook.inspect({
  kind: "table",
  range: "商品参数!AH4:AK7",
  include: "values,formulas",
  tableMaxRows: 4,
  tableMaxCols: 4,
  maxChars: 5000,
});
await fs.writeFile(`${outputDir}/inspection.ndjson`, check.ndjson, "utf8");

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
await fs.writeFile(`${outputDir}/formula-errors.ndjson`, errors.ndjson, "utf8");

for (const [sheetName, range] of [["商品参数", "AH1:AK8"], ["填写说明", `A1:H${noteRow + 2}`], ["选项表", "Q1:T16"]]) {
  const preview = await workbook.render({ sheetName, range, scale: 2, format: "png" });
  await fs.writeFile(`${previewDir}/${sheetName}.png`, new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath, field: "SKU是否独立包装", values: ["是独立包装", "不是独立包装"] }));
