<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { api, mainRoles, roleLabels, label } from "../api";
const props = defineProps({ assets: Array, editable: Boolean }),
  emit = defineEmits(["changed"]);
const provider = ref({}),
  input = ref(null),
  operation = ref("MODEL"),
  role = ref("SPU_WHITE_MAIN"),
  prompt = ref(""),
  error = ref(""),
  busy = ref(false),
  jobs = ref([]);
let jobId = crypto.randomUUID(),
  controller;
const current = computed(() =>
  jobs.value.filter((j) => props.assets.some((a) => a.id === j.input_asset_id)),
);
async function load() {
  try {
    [provider.value, jobs.value] = await Promise.all([
      api("/api/image-provider/status"),
      api("/api/image-operations"),
    ]);
  } catch (e) {
    error.value = e.message;
  }
}
async function execute() {
  if (!input.value) return;
  busy.value = true;
  error.value = "";
  controller = new AbortController();
  try {
    await api(`/api/assets/${input.value}/operations/${jobId}`, {
      method: "POST",
      signal: controller.signal,
      body: {
        operation: operation.value,
        role: role.value,
        ...(operation.value === "MODEL" ? { prompt: prompt.value } : {}),
      },
    });
    jobId = crypto.randomUUID();
    emit("changed");
  } catch (e) {
    if (e.name !== "AbortError") error.value = e.message;
  } finally {
    busy.value = false;
    await load();
  }
}
onMounted(load);
onUnmounted(() => controller?.abort());
</script>
<template>
  <el-collapse class="subsection"
    ><el-collapse-item title="可选图像模型与算法" name="compute"
      ><p class="muted">
        图像模型：{{ provider.configured ? "已启用" : "未配置 / 未启用" }} ·
        算法适配器：{{ provider.compute_configured ? "已配置" : "未配置" }}
      </p>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <div class="inline-controls">
        <el-select
          v-model="input"
          placeholder="选择输入素材"
          aria-label="算法输入素材"
          ><el-option
            v-for="a in assets.filter((a) => a.mime_type.startsWith('image/'))"
            :key="a.id"
            :value="a.id"
            :label="`${roleLabels[a.role] || a.role} · v${a.version}`" /></el-select
        ><el-select v-model="operation" aria-label="可选算法操作"
          ><el-option label="图像模型编辑 / 场景生成" value="MODEL" /><el-option
            label="真实OCR识别"
            value="OCR" /><el-option
            label="BiRefNet抠图"
            value="REMOVE_BACKGROUND" /></el-select
        ><el-select v-model="role" aria-label="模型输出槽位"
          ><el-option
            v-for="name in mainRoles"
            :key="name"
            :value="name"
            :label="roleLabels[name]"
        /></el-select>
      </div>
      <el-input
        v-if="operation === 'MODEL'"
        v-model="prompt"
        type="textarea"
        :rows="3"
        aria-label="图像模型提示词"
        placeholder="明确说明保留哪些商品事实、构图与场景要求"
        maxlength="6000" />
      <div class="form-actions">
        <span class="muted">只保存实际返回结果；不确定的收费请求请先核查。</span
        ><el-button
          type="primary"
          :loading="busy"
          :disabled="
            !editable ||
            !input ||
            (operation === 'MODEL'
              ? !provider.configured || !prompt.trim()
              : !provider.compute_configured)
          "
          @click="execute"
          >执行所选处理</el-button
        >
      </div>
      <el-table :data="current"
        ><el-table-column prop="operation" label="操作" /><el-table-column
          label="状态"
          ><template #default="s">{{
            label(s.row.status)
          }}</template></el-table-column
        ><el-table-column
          prop="created_at"
          label="时间"
          min-width="150" /><el-table-column
          prop="result_asset_id"
          label="产物ID" /></el-table></el-collapse-item
  ></el-collapse>
</template>
