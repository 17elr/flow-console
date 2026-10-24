<script setup>
import { ref } from "vue";
import { ElMessageBox } from "element-plus";
import { api } from "../api";
defineProps({ skus: Array, editable: Boolean });
const emit = defineEmits(["changed"]),
  drafts = ref({}),
  error = ref(""),
  busy = ref(false);
function draft(id) {
  return (drafts.value[id] ||= {
    component_code: "",
    component_name: "",
    quantity: "",
  });
}
async function add(id) {
  busy.value = true;
  error.value = "";
  try {
    await api(`/api/skus/${id}/components`, {
      method: "POST",
      body: draft(id),
    });
    drafts.value[id] = { component_code: "", component_name: "", quantity: "" };
    emit("changed");
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function remove(component) {
  try {
    await ElMessageBox.confirm(
      `从当前SKU移除组件“${component.component_name}”？商品需要重新审核。`,
      "移除套装组件",
    );
  } catch {
    return;
  }
  try {
    await api(`/api/components/${component.id}`, { method: "DELETE" });
    emit("changed");
  } catch (e) {
    error.value = e.message;
  }
}
</script>
<template>
  <el-collapse v-if="skus?.length" class="subsection"
    ><el-collapse-item title="套装组件管理" name="components"
      ><el-alert v-if="error" :title="error" type="error" :closable="false" />
      <section v-for="sku in skus" :key="sku.id" class="component-editor">
        <h3>{{ sku.sku_code }}</h3>
        <div v-for="c in sku.components" :key="c.id" class="component-line">
          <span
            >{{ c.component_name }} · {{ c.component_code }} ×
            {{ c.quantity }}</span
          ><el-button v-if="editable" text type="danger" @click="remove(c)"
            >移除</el-button
          >
        </div>
        <form
          v-if="editable"
          class="inline-controls"
          @submit.prevent="add(sku.id)"
        >
          <el-input
            v-model="draft(sku.id).component_code"
            aria-label="组件编码"
            placeholder="组件编码"
            required
          /><el-input
            v-model="draft(sku.id).component_name"
            aria-label="组件名称"
            placeholder="组件名称"
            required
          /><el-input
            v-model="draft(sku.id).quantity"
            aria-label="组件数量"
            placeholder="真实数量"
            inputmode="numeric"
            required
          /><el-button type="primary" native-type="submit" :loading="busy"
            >添加组件</el-button
          >
        </form>
      </section></el-collapse-item
    ></el-collapse
  >
</template>
