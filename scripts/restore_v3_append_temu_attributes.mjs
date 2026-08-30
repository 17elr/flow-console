import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:/Users/17elr/Documents/New project4/outputs/temu-category-id/TEMU-女士时尚吊坠项链-单页产品参数模板-v3-含类目ID.xlsx";
const outputPath = "C:/Users/17elr/Documents/New project4/outputs/temu-category-id/TEMU-女士时尚吊坠项链-单页产品参数模板-v5-v3保留并追加妙手属性.xlsx";
const rules = await (await fetch("http://127.0.0.1:8000/api/miaoshou/category-rules/29542")).json();
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const product = wb.worksheets.getItem("商品参数");
const option = wb.worksheets.getItem("选项表");
const oldProduct = product.getRange("A4:AZ200").values;
const headers = oldProduct[0].filter(Boolean);
const data = oldProduct.slice(1).filter((row) => row?.[0]);
const norm = (value) => String(value ?? "").toLowerCase().replace(/[\s_（）()/:：-]+/g, "");
const existing = new Set(headers.map(norm));
const aliases = {
  "镀层": ["镀层", "plating"], "镶嵌材质": ["镶嵌材质", "inlaymaterial"], "主体材质": ["主体材质", "mainmaterial"],
  "风格": ["风格", "style"], "佩戴场合": ["佩戴场合", "occasion"], "适配季节": ["适配季节", "season"], "节日": ["节日", "holiday"],
  "金属部件材质类型": ["金属材质", "金属部件材质类型", "materialtypesofmetalparts"], "是否含金属部件": ["是否含金属部件", "whetheritcontainsmetalcomponents"],
  "诞生石": ["诞生石", "birthstone"], "主题": ["主题", "theme"], "品牌名": ["品牌名", "brand"], "供电方式": ["供电方式", "powersupply"],
  "系列": ["系列", "collection"], "有无礼盒": ["有无礼盒", "withorwithoutgiftbox"]
};
const missing = rules.attributes.map((item) => item.name).filter((name) => {
  const key = norm(name);
  if (existing.has(key)) return false;
  return !Object.values(aliases).some((list) => list.some((alias) => key === norm(alias) && list.some((x) => existing.has(norm(x)))));
});
const appendedHeaders = [...headers, ...missing];
const rows = data.map((row) => [...row.slice(0, headers.length), ...missing.map(() => null)]);
product.getRange("A4:AZ200").clear({ applyTo: "contents" });
product.getRangeByIndexes(3, 0, 1, appendedHeaders.length).values = [appendedHeaders];
product.getRangeByIndexes(4, 0, rows.length, appendedHeaders.length).values = rows;
product.freezePanes.freezeRows(4);

const oldOptions = option.getRange("A4:AZ200").values;
const optionHeaders = oldOptions[0].filter(Boolean);
const optionData = oldOptions.slice(1).filter((row) => row.some((value) => value != null && value !== ""));
const optionExisting = new Set(optionHeaders.map(norm));
const missingRules = rules.attributes.filter((item) => !optionExisting.has(norm(item.name)) && !Object.values(aliases).some((list) => list.some((alias) => norm(alias) === norm(item.name) && list.some((x) => optionExisting.has(norm(x))))));
const optionHeadersOut = [...optionHeaders, ...missingRules.map((item) => item.name)];
const maxRows = Math.max(optionData.length, ...missingRules.map((item) => item.values.length), 1);
const optionRowsOut = Array.from({ length: maxRows }, (_, index) => [
  ...Array.from({ length: optionHeaders.length }, (_, col) => optionData[index]?.[col] ?? null),
  ...missingRules.map((item) => item.values[index]?.name ?? null),
]);
option.getRange("A4:AZ200").clear({ applyTo: "contents" });
option.getRangeByIndexes(3, 0, 1, optionHeadersOut.length).values = [optionHeadersOut];
option.getRangeByIndexes(4, 0, optionRowsOut.length, optionHeadersOut.length).values = optionRowsOut;
option.freezePanes.freezeRows(4);

const out = await SpreadsheetFile.exportXlsx(wb);
await out.save(outputPath);
const preview = await wb.render({ sheetName: "商品参数", range: "A1:AU8", scale: 1, format: "png" });
await fs.writeFile(outputPath + ".preview.png", new Uint8Array(await preview.arrayBuffer()));
console.log(JSON.stringify({ outputPath, originalColumns: headers.length, appendedProductAttributes: missing.length, appendedOptionAttributes: missingRules.length }));
