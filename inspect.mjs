import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";
const input = await FileBlob.load("D:/17elr/微信数据/xwechat_files/wxid_3otnuj9qhfnu22_a815/msg/file/2026-08/副本TEMU-女士时尚吊坠项链-单页产品参数模板-v3.xlsx");
const wb = await SpreadsheetFile.importXlsx(input);
console.log((await wb.inspect({kind:"workbook,sheet,table",maxChars:10000,tableMaxRows:8,tableMaxCols:80,tableMaxCellChars:120})).ndjson);
for (const s of wb.worksheets.items) {
  const used = s.getUsedRange();
  console.log("SHEET", s.name, used?.address);
}
