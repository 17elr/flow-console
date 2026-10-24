<script setup>
import { onMounted, ref } from "vue";
import { api } from "../api";
const props = defineProps({ id: Number, editable: Boolean }),
  emit = defineEmits(["changed"]);
const presets = ref([]),
  selected = ref(null),
  slot = ref(1),
  error = ref(""),
  busy = ref(false);
async function load() {
  try {
    presets.value = await api("/api/packaging-presets");
  } catch (e) {
    error.value = e.message;
  }
}
async function upload(event) {
  const file = event.target.files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  busy.value = true;
  error.value = "";
  try {
    await api(`/api/packaging-presets/${slot.value}`, {
      method: "PUT",
      body: form,
    });
    await load();
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
    event.target.value = "";
  }
}
async function select() {
  busy.value = true;
  error.value = "";
  try {
    await api(`/api/products/${props.id}/packaging-selection`, {
      method: "PUT",
      body: { preset_id: selected.value },
    });
    emit("changed");
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <el-collapse class="subsection"
    ><el-collapse-item title="团队包装预设" name="packaging"
      ><p class="muted">
        预设变更保留版本，商品选择时复制指定版本，不影响已批准的历史素材。
      </p>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <div class="packaging-preset-grid">
        <article v-for="p in presets" :key="p.id">
          <img
            :src="`/api/packaging-presets/${p.slot}/content`"
            :alt="`包装预设${p.slot}版本${p.version}`"
          /><span>预设 {{ p.slot }} · v{{ p.version }}</span>
        </article>
      </div>
      <div class="inline-controls">
        <el-select
          v-model="selected"
          placeholder="选择团队包装预设"
          aria-label="选择包装预设"
          ><el-option
            v-for="p in presets"
            :key="p.id"
            :value="p.id"
            :label="`预设 ${p.slot} · v${p.version}`" /></el-select
        ><el-button
          :loading="busy"
          :disabled="!editable || !selected"
          @click="select"
          >应用到当前商品</el-button
        >
      </div>
      <div v-if="editable" class="inline-controls">
        <label
          >预设槽位<el-input-number v-model="slot" :min="1" :max="20" /></label
        ><label class="file-button"
          >上传包装预设<input
            type="file"
            accept="image/png,image/jpeg"
            aria-label="上传团队包装预设"
            :disabled="busy"
            @change="upload"
        /></label></div></el-collapse-item
  ></el-collapse>
</template>
