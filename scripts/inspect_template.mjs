import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";
const path = "C:/Users/17elr/Documents/New project4/outputs/temu-category-id/TEMU-女士时尚吊坠项链-单页产品参数模板-v3-含类目ID.xlsx";
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(path));
console.log((await wb.inspect({kind:"sheet", include:"id,name"})).ndjson);
for (const name of ["商品参数","选项表","填写说明"]) {
  try { console.log(name, (await wb.inspect({kind:"region", sheetId:name, range:"A1:AZ25", maxChars:12000})).ndjson); } catch {}
}
console.log("headers", JSON.stringify(wb.worksheets.getItem("商品参数").getRange("A4:AJ5").values));
console.log("options", JSON.stringify(wb.worksheets.getItem("选项表").getRange("A4:M13").values));
