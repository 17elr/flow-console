<script setup>
import { onMounted, ref } from "vue";
import { UploadFilled, Download } from "@element-plus/icons-vue";
import { api, label } from "../api";
defineProps({ user: Object });
const emit = defineEmits(["imported"]);
const workbook = ref(null),
  folder = ref([]),
  mode = ref("excel"),
  history = ref([]),
  result = ref(null),
  error = ref(""),
  busy = ref(false);
async function load() {
  try {
    history.value = await api("/api/imports");
  } catch (e) {
    error.value = e.message;
  }
}
async function submit() {
  if (!workbook.value) {
    error.value = "请选择工作簿或ZIP文件";
    return;
  }
  busy.value = true;
  error.value = "";
  result.value = null;
  const form = new FormData();
  form.append("file", workbook.value);
  if (mode.value === "finished-images")
    for (const file of folder.value) {
      form.append("files", file);
      form.append("paths", file.webkitRelativePath || file.name);
    }
  try {
    result.value = await api(`/api/imports/${mode.value}`, {
      method: "POST",
      body: form,
    });
    await load();
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div class="page-heading">
    <div>
      <span class="eyebrow">资料入口</span>
      <h1>批量导入，逐项有回音。</h1>
      <p>按 SPU 整体校验，失败项可修正后重新导入。</p>
    </div>
    <el-button tag="a" href="/api/imports/template" :icon="Download"
      >下载导入模板</el-button
    >
  </div>
  <div class="import-layout">
    <section class="panel padded">
      <h2>导入商品资料</h2>
      <el-segmented
        v-model="mode"
        :options="[
          { label: 'Excel 工作簿', value: 'excel' },
          { label: '成品图 + 资料', value: 'finished-images' },
          { label: 'ZIP 素材包', value: 'package' },
        ]"
      /><el-alert v-if="error" :title="error" type="error" :closable="false" />
      <form @submit.prevent="submit">
        <label class="upload-zone"
          ><el-icon :size="34"><UploadFilled /></el-icon
          ><strong>{{
            workbook?.name ||
            (mode === "package" ? "选择 ZIP 商品素材包" : "选择 Excel 工作簿")
          }}</strong
          ><span>点击选择，单文件最多30MB</span
          ><input
            :key="mode"
            type="file"
            :accept="mode === 'package' ? '.zip' : '.xlsx'"
            aria-label="选择导入文件"
            required
            @change="workbook = $event.target.files[0]" /></label
        ><label v-if="mode === 'finished-images'" class="folder-picker"
          >成品图文件夹<input
            type="file"
            webkitdirectory
            multiple
            aria-label="选择成品图文件夹"
            @change="folder = [...$event.target.files]"
          /><small
            >已选 {{ folder.length }} 个文件。每个 SPU
            一个文件夹，主图命名01至06，SKU图以SKU编码命名。</small
          ></label
        ><el-button
          type="primary"
          native-type="submit"
          :loading="busy"
          :disabled="user.role === 'REVIEWER'"
          size="large"
          >校验并导入</el-button
        >
      </form>
      <el-alert
        title="导入后需要人工审核，系统不会自动批准图片、文案或商品。"
        type="info"
        :closable="false"
      />
    </section>
    <aside class="panel padded import-guide">
      <span class="eyebrow">准备清单</span>
      <h2>让资料一次对齐</h2>
      <ol>
        <li>
          <strong>确认商品关系</strong>
          <p>填写SPU与SKU编码，SKU不能跨SPU重复归属。</p>
        </li>
        <li>
          <strong>保留真实数值</strong>
          <p>价格、数量与规格缺失会返回明确错误，不自动补写。</p>
        </li>
        <li>
          <strong>匹配图片槽位</strong>
          <p>六张主图按顺序，SKU图片独立绑定。原图与成品图分别记录。</p>
        </li>
        <li>
          <strong>交给审核成员</strong>
          <p>导入成功后先补齐资料，审核通过才能创建平台任务。</p>
        </li>
      </ol>
    </aside>
  </div>
  <section v-if="result" class="panel padded">
    <div class="section-heading">
      <h2>本次导入：{{ label(result.status) }}</h2>
      <el-button
        v-if="result.product_ids?.length"
        type="primary"
        @click="emit('imported', result.product_ids[0])"
        >查看已导入商品</el-button
      >
    </div>
    <p>
      总行数 {{ result.total_rows }} · 有效 {{ result.valid_rows }} · 出错行
      {{ result.issue_rows }} · 错误项 {{ result.error_count }}
    </p>
    <el-table
      v-if="result.issues?.length"
      :data="result.issues"
      max-height="360"
      ><el-table-column prop="sheet" label="工作表" /><el-table-column
        prop="row_number"
        label="行号"
        width="80" /><el-table-column
        prop="identifier"
        label="SPU" /><el-table-column
        prop="field"
        label="字段" /><el-table-column
        prop="message"
        label="修正提示"
        min-width="240"
    /></el-table>
  </section>
  <section class="panel padded">
    <h2>导入记录</h2>
    <el-table :data="history"
      ><el-table-column
        prop="filename"
        label="文件"
        min-width="180"
      /><el-table-column label="状态"
        ><template #default="s">{{
          label(s.row.status)
        }}</template></el-table-column
      ><el-table-column prop="valid_rows" label="有效行" /><el-table-column
        prop="issue_rows"
        label="出错行"
      /><el-table-column prop="error_count" label="错误项" /><el-table-column
        label="详情"
        ><template #default="s"
          ><el-button text @click="result = s.row"
            >查看问题</el-button
          ></template
        ></el-table-column
      ></el-table
    >
  </section>
</template>
