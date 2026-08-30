import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";
const p = "outputs/temu-template-v4/TEMU-女士时尚吊坠项链-单页产品参数模板-v4.xlsx";
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(p));
for (const name of ["商品参数","填写说明","选项表"]) {
  const blob = await wb.render({sheetName:name, autoCrop:"all", scale:1, format:"png"});
  await fs.writeFile(`outputs/temu-template-v4/${name}.png`, new Uint8Array(await blob.arrayBuffer()));
}
console.log((await wb.inspect({kind:"table",sheetId:"选项表",range:"A1:R20",include:"values",tableMaxRows:20,tableMaxCols:18,tableMaxCellChars:80})).ndjson);
console.log((await wb.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",options:{useRegex:true,maxResults:50},summary:"final formula error scan"})).ndjson);
