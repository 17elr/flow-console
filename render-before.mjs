import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";
const input = await FileBlob.load("D:/17elr/微信数据/xwechat_files/wxid_3otnuj9qhfnu22_a815/msg/file/2026-08/副本TEMU-女士时尚吊坠项链-单页产品参数模板-v3.xlsx");
const wb = await SpreadsheetFile.importXlsx(input);
const blob = await wb.render({sheetName:"商品参数",range:"A1:AI8",scale:1,format:"png"});
await fs.writeFile("before-template.png",new Uint8Array(await blob.arrayBuffer()));
