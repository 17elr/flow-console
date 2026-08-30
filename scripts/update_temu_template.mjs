import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:/Users/17elr/Documents/New project4/outputs/temu-category-id/TEMU-女士时尚吊坠项链-单页产品参数模板-v3-含类目ID.xlsx";
const outputPath = "C:/Users/17elr/Documents/New project4/outputs/temu-category-id/TEMU-女士时尚吊坠项链-单页产品参数模板-v4-妙手属性.xlsx";
const rules = await (await fetch("http://127.0.0.1:8000/api/miaoshou/category-rules/29542")).json();
if (!rules.attributes?.length) throw new Error("妙手类目规则为空");
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const productSheet = workbook.worksheets.getItem("商品参数");
const oldRows = productSheet.getRange("A4:AZ200").values;
const oldHeaders = oldRows[0] ?? [];
const oldData = oldRows.slice(1).filter((row) => row?.[0]);
const fixedHeaders = oldHeaders.slice(0, 5);
const attributeHeaders = rules.attributes.map((item) => item.name);
const operationalHeaders = oldHeaders.slice(20).filter(Boolean);
const newHeaders = [...fixedHeaders, ...attributeHeaders, ...operationalHeaders];
const attributeAliases = {
  "镀层": "镀层 Plating", "镶嵌材质": "镶嵌材质 Inlay Material", "主体材质": "主体材质 Main Material",
  "风格": "风格 Style", "佩戴场合": "佩戴场合 Occasion", "适配季节": "适配季节 Season", "节日": "节日 Holiday",
  "金属部件材质类型": "金属材质 Material Types of Metal Parts", "是否含金属部件": "是否含金属部件 Whether it contains metal components",
  "诞生石": "诞生石 Birthstone", "主题": "主题 Theme", "品牌名": "品牌名 Brand", "供电方式": "供电方式 Power Supply",
  "系列": "系列 Collection", "有无礼盒": "有无礼盒 With Or Without Gift Box"
};
const newData = oldData.map((row) => {
  const byHeader = new Map(oldHeaders.map((header, index) => [header, row[index]]));
  return newHeaders.map((header) => {
    if (byHeader.has(header)) return byHeader.get(header);
    const oldHeader = attributeAliases[header] ?? Object.entries(attributeAliases).find(([name]) => header === name)?.[1];
    return oldHeader ? (byHeader.get(oldHeader) ?? null) : null;
  });
});
productSheet.getRange("A4:AZ200").clear({ applyTo: "contents" });
productSheet.getRangeByIndexes(3, 0, 1, newHeaders.length).values = [newHeaders];
if (newData.length) productSheet.getRangeByIndexes(4, 0, newData.length, newHeaders.length).values = newData;
productSheet.freezePanes.freezeRows(4);
const sheet = workbook.worksheets.getItem("选项表");
sheet.getRange("A4:AZ500").clear({ applyTo: "contents" });
const columns = rules.attributes;
sheet.getRangeByIndexes(3, 0, 1, columns.length).values = [columns.map((item) => item.name)];
const rows = Math.max(...columns.map((item) => item.values.length), 0);
const matrix = Array.from({ length: rows }, (_, row) => columns.map((item) => item.values[row]?.name ?? null));
if (rows) sheet.getRangeByIndexes(4, 0, rows, columns.length).values = matrix;
sheet.getRangeByIndexes(3, 0, Math.max(rows + 1, 1), columns.length).format.wrapText = true;
sheet.freezePanes.freezeRows(4);
const out = await SpreadsheetFile.exportXlsx(workbook);
await out.save(outputPath);
const preview = await workbook.render({ sheetName: "选项表", range: "A1:Z18", scale: 1, format: "png" });
await fs.writeFile(outputPath + ".preview.png", new Uint8Array(await preview.arrayBuffer()));
console.log(JSON.stringify({ outputPath, attributeCount: columns.length, optionRows: rows }));
