import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "D:/17elr/微信数据/xwechat_files/wxid_3otnuj9qhfnu22_a815/msg/file/2026-08/副本TEMU-女士时尚吊坠项链-单页产品参数模板-v3.xlsx";
const outputDir = "outputs/temu-template-v4";
const outputPath = `${outputDir}/TEMU-女士时尚吊坠项链-单页产品参数模板-v4.xlsx`;

const unique = (values) => [...new Set(values.filter((v) => v && String(v).trim()))];

const options = {
  "镀层": unique(["未镀层", "无", "电镀", "镀金色", "镀银色", "镀玫瑰金色", "镀14K金", "镀18K金", "镀22K金", "镀24K金", "镀银", "镀925银", "镀白金", "镀玫瑰金", "镀UV", "镀铑", "镀枪黑", "镀白K", "镀铜合金", "镀KC金", "镀铜", "镀钛", "其他"]),
  "镶嵌材质": unique(["无", "莫桑钻", "孔雀石", "天然水晶", "天然石", "月光石", "松石", "欧泊", "碧玺", "贝壳", "鲍鱼贝", "玻璃", "塑料", "陶瓷", "树脂", "水草玛瑙", "海纹石", "培育钻", "5A钻石", "3A钻石", "冰花锆", "合成松石", "合成澳宝", "合成青金石", "合成坦桑石", "合成石榴石", "合成蓝宝石", "合成祖母绿", "合成尖晶石", "合成红宝石", "合成钻石", "海蓝宝", "青金石", "坦桑石", "合成托帕石", "橄榄石", "尖晶石", "石榴石", "摩根石", "猫眼石/虎眼石", "夜光石", "贝母", "天然玛瑙", "翡翠", "琥珀", "合成钻石（合成立方氧化锆）", "朱砂", "托帕石", "亚历山大变石", "紫水晶", "日光石", "黄水晶", "紫黄晶", "透辉石", "缅丝玛瑙", "锂辉石", "萤青石", "芬达石", "玉髓（石髓）", "蛇纹石", "红玉髓", "绿玉髓", "苏丹石", "其他"]),
  "主体/金属材质": unique(["合金", "铝合金", "锌合金", "铁合金", "铜", "925银", "不锈钢", "铁钢", "亚克力", "树脂", "玻璃", "聚酯纤维", "石头", "塑料", "PU革", "人造皮", "软陶", "贝壳", "铁", "201不锈钢", "202不锈钢", "304不锈钢", "304L不锈钢", "316不锈钢", "316L不锈钢", "真皮", "棉制绳", "麻制绳", "尼龙绳", "合成纤维绳", "塑料绳", "木头", "尼龙", "翡翠", "陶瓷", "天然水晶", "钨钢", "拉菲草", "纸质", "草", "硅胶原料", "大马士革钢", "朱砂", "腈纶纤维", "铜合金", "14K金", "18K金", "22K金", "990银", "999银", "合成蓝宝石", "合成祖母绿", "合成尖晶石", "合成红宝石", "合成钻石", "海蓝宝", "碧玺", "青金石", "坦桑石", "合成托帕石", "海纹石", "天然绿松石", "天然孔雀石", "橄榄石", "水草玛瑙", "尖晶石", "石榴石", "摩根石", "贝母", "猫眼石/虎眼石", "月光石", "夜光石", "欧泊/澳宝", "莫桑钻", "琥珀", "合成钻石（合成立方氧化锆）", "10K金", "24K金", "9K金", "玉髓（石髓）", "托帕石", "亚历山大变石", "紫水晶", "日光石", "黄水晶", "紫黄晶", "其他"]),
  "风格": unique(["简约", "时尚", "复古", "波西米亚", "优雅", "性感", "可爱", "度假", "民族风", "日韩", "奢华", "Y2K", "哥特", "撒娇风格", "印度风", "黑人时尚", "阿拉伯风", "西部风", "男孩风", "海洋风", "田园", "法式", "经典", "宫廷风", "中国风", "blingbling", "派对", "学院风", "Sporty运动", "卡通", "朋克", "嬉皮", "个性夸张", "其他"]),
  "佩戴场合": unique(["日常", "送礼", "派对", "音乐节", "度假", "婚礼", "宴会", "运动", "庆祝节日", "约会", "通勤", "聚会", "节日", "其他"]),
  "适配季节": unique(["全年", "春季", "夏季", "秋季", "冬季"]),
  "节日": unique(["无特定节日", "无", "农历新年", "橄榄球赛事", "情人节", "狂欢节", "圣帕特里克节", "复活节", "斋月", "母亲节", "父亲节", "万圣节", "感恩节", "圣诞节", "新年", "生日", "其他"]),
  "是/否": ["是", "否"],
  "敏感属性": unique(["无敏感属性", "纯电", "内电", "磁性", "液体", "粉末", "膏体", "刀具", "其他敏感属性"]),
  "商品类型": ["定制商品", "非定制商品"],
  "SKU分类": ["单品", "多件混装", "组合装/套装"],
  "外包装类型": ["硬包装", "软包装+硬物", "软包装+软物"],
  "外包装形状": ["不规则", "长方体", "圆柱体"],
  "供电方式": ["干电池供电", "插头供电", "太阳能充电", "USB供电", "接充电/硬接线", "无需供电使用", "USB充电（内置电池）"],
  "系列": ["中东专项", "日韩专项", "拉美专项", "非洲专项", "澳新专项", "欧洲专项", "男士专项"],
  "主题": unique(["动物", "体育", "假日", "食品和饮料", "航海主题", "天体符号", "脚本和数字符号", "鲜花", "户外标志", "心形", "宗教符号", "克拉达", "弓", "无穷大", "其他"]),
  "诞生石": ["一月生日石", "二月生日石", "三月生日石", "四月生日石", "五月生日石", "六月生日石", "七月生日石", "八月生日石", "九月生日石", "十月生日石", "十一月生日石", "十二月生日石"],
  "有无礼盒": ["有礼盒", "无礼盒"],
};

const input = await FileBlob.load(inputPath);
const wb = await SpreadsheetFile.importXlsx(input);
const product = wb.worksheets.getItem("商品参数");
const notes = wb.worksheets.getItem("填写说明");
const optionSheet = wb.worksheets.getItem("选项表");

// Preserve the existing formatting by copying the last formatted column, then append the new category ID.
product.getRange("AI1:AI104").copyTo(product.getRange("AJ1:AJ104"), "all");
product.getRange("AJ4").values = [["妙手类目ID cid"]];
product.getRange("AJ5:AJ6").values = [[29542], [29542]];
product.getRange("A1").values = [["TEMU 女士时尚吊坠项链 - 单页产品参数 v4"]];
product.getRange("A2").values = [["固定类目：服装、鞋靴和珠宝饰品 > 女士时尚 > 女士饰品 > 女士项链 > 女士时尚吊坠项链。每个产品只填写一行；SKU数量、名称、编码和图片由产品图片文件夹自动识别。长截图重叠选项已去重，字段与妙手编辑页保持对应。"]];
product.getRange("AJ4:AJ104").format.columnWidth = 16;
product.getRange("AJ1").format = { fill: "#173B56", font: { bold: true, color: "#FFFFFF" } };
product.getRange("AJ2").format = { fill: "#E8F2F7", font: { color: "#36586D" } };
product.getRange("AJ3").format = { fill: "#173B56", font: { bold: true, color: "#FFFFFF" } };
product.getRange("AJ4").format = { fill: "#4C7F8F", font: { bold: true, color: "#FFFFFF" }, wrapText: true, horizontalAlignment: "center", verticalAlignment: "center" };
product.freezePanes.freezeRows(4);
product.freezePanes.freezeColumns(1);

const optionHeaders = ["镀层", "镶嵌材质", "主体/金属材质", "风格", "佩戴场合", "适配季节", "节日", "是/否", "敏感属性", "商品类型", "SKU分类", "外包装类型", "外包装形状", "供电方式", "系列", "主题", "诞生石", "有无礼盒"];
optionSheet.getRange("A1:R180").clear({ applyTo: "contents" });
optionSheet.getRange("A1:R1").merge();
optionSheet.getRange("A1").values = [["妙手女士时尚吊坠项链类目下拉选项（长截图重叠项已去重）"]];
optionSheet.getRange("A2:R2").merge();
optionSheet.getRange("A2").values = [["仅保留妙手页面实际出现的字段和选项；Excel 中未填写的属性不会由系统猜测。"]];
optionSheet.getRange("A4:R4").values = [optionHeaders];
const maxRows = Math.max(...optionHeaders.map((h) => options[h].length));
const matrix = Array.from({ length: maxRows }, (_, r) => optionHeaders.map((h) => options[h][r] ?? null));
optionSheet.getRange(`A5:R${4 + maxRows}`).values = matrix;
optionSheet.getRange("A1:R1").format = { fill: "#173B56", font: { bold: true, color: "#FFFFFF", size: 14 } };
optionSheet.getRange("A4:R4").format = { fill: "#2B6F9F", font: { bold: true, color: "#FFFFFF" }, wrapText: true };
optionSheet.getRange("A4:R4").format.rowHeight = 34;
optionSheet.getRange("A1:R180").format.columnWidth = 18;
optionSheet.getRange("A1:R180").format.wrapText = false;
optionSheet.freezePanes.freezeRows(4);

const validationMap = {
  E: "A", F: "B", G: "C", H: "D", I: "E", J: "F", K: "G", L: "C", M: "H", N: "Q", O: "P", Q: "N", S: "R", U: "I", V: "J", W: "K", AH: "L", AI: "M",
};
for (const [productCol, optionCol] of Object.entries(validationMap)) {
  const header = optionHeaders[optionCol.charCodeAt(0) - 65];
  const last = 4 + options[header].length;
  product.getRange(`${productCol}5:${productCol}104`).dataValidation = { rule: { type: "list", formula1: `='选项表'!$${optionCol}$5:$${optionCol}$${last}` } };
}
product.getRange("AJ5:AJ104").dataValidation = { rule: { type: "whole", operator: "equal", formula1: 29542 } };

notes.getRange("A11:F13").values = [
  ["妙手类目ID", "填写固定类目 ID", 29542, "写入妙手 cid 字段", "必填", "本模板女士时尚吊坠项链类目固定为 29542"],
  ["选项去重", "下拉选项已按字段去重", "长截图重叠项只保留一次", "导入时按字段精确匹配", "系统处理", "不要把截图中的重复项再次添加"],
  ["字段边界", "只填写妙手页面对应字段", "不相关字段留空", "不会自动猜测未填写属性", "按后台要求", "包装图片仍在网页上传并二选一"],
];

await fs.mkdir(outputDir, { recursive: true });
const preview = await wb.render({ sheetName: "选项表", range: "A1:R35", scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/options-preview.png`, new Uint8Array(await preview.arrayBuffer()));
const out = await SpreadsheetFile.exportXlsx(wb);
await out.save(outputPath);

console.log((await wb.inspect({ kind: "table", sheetId: "商品参数", range: "A1:AJ6", include: "values", tableMaxRows: 6, tableMaxCols: 36, tableMaxCellChars: 100 })).ndjson);
console.log((await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 50 }, summary: "final formula error scan" })).ndjson);
console.log(outputPath);
