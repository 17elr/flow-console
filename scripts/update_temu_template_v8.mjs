import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = "C:/Users/17elr/Documents/New project4";
const inputPath = `${root}/outputs/temu-template-v7/TEMU-女士时尚吊坠项链-单页产品参数模板-v7.xlsx`;
const outputDir = `${root}/outputs/temu-template-v8`;
const outputPath = `${outputDir}/TEMU-女士时尚吊坠项链-单页产品参数模板-v8.xlsx`;
const previewDir = `${outputDir}/previews`;
await fs.mkdir(previewDir, { recursive: true });

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const product = workbook.worksheets.getItem("商品参数");
const options = workbook.worksheets.getItem("选项表");

// Keep only the real template fields through the new SKU packaging field.
product.getRange("AL1:AZ200").clear({ applyTo: "all" });
options.getRange("U1:AZ500").clear({ applyTo: "all" });

// Normalize the final three columns to the same visual language as the existing fields.
const headerFormat = {
  fill: "#4C7F8F",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
const bodyFormat = {
  fill: "#FFFFFF",
  font: { color: "#36586D" },
  verticalAlignment: "center",
};
product.getRange("AI4:AK4").format = headerFormat;
product.getRange("AI5:AK200").format = bodyFormat;
product.getRange("AI4:AK200").format.columnWidth = 18;
product.getRange("AI4:AK200").format.rowHeight = 24;
product.getRange("AI4:AK4").format.rowHeight = 42;
product.getRange("AI5:AK200").format.wrapText = false;
product.getRange("AI5:AK200").format.horizontalAlignment = "center";

options.getRange("R4:T4").format = {
  fill: "#2B75A3",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
options.getRange("R5:T500").format = bodyFormat;
options.getRange("R4:T500").format.columnWidth = 18;
options.getRange("R4:T4").format.rowHeight = 34;

const preview = await workbook.render({ sheetName: "商品参数", range: "AG1:AK8", scale: 2, format: "png" });
await fs.writeFile(`${previewDir}/商品参数.png`, new Uint8Array(await preview.arrayBuffer()));
const optionsPreview = await workbook.render({ sheetName: "选项表", range: "Q1:T16", scale: 2, format: "png" });
await fs.writeFile(`${previewDir}/选项表.png`, new Uint8Array(await optionsPreview.arrayBuffer()));

const check = await workbook.inspect({ kind: "table", range: "商品参数!AI4:AK7", include: "values,formulas", tableMaxRows: 4, tableMaxCols: 3, maxChars: 4000 });
await fs.writeFile(`${outputDir}/inspection.ndjson`, check.ndjson, "utf8");
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" });
await fs.writeFile(`${outputDir}/formula-errors.ndjson`, errors.ndjson, "utf8");

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath, retainedProductColumns: "A:AK", retainedOptionColumns: "A:T" }));
