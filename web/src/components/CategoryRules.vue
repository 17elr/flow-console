<script setup>
import { ref } from "vue";
import { api } from "../api";
const cid = ref(""),
  result = ref(null),
  error = ref(""),
  busy = ref(false);
async function lookup() {
  busy.value = true;
  error.value = "";
  result.value = null;
  try {
    result.value = await api(
      `/api/miaoshou/category-rules/${encodeURIComponent(cid.value)}`,
    );
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <section class="subsection">
    <h3>查询TEMU真实类目规则</h3>
    <p class="muted">
      仅查询已有类目ID的当前属性规则，不自动猜测或替换商品属性。
    </p>
    <div class="inline-controls">
      <el-input
        v-model="cid"
        aria-label="TEMU类目ID"
        placeholder="输入真实末级类目ID"
        inputmode="numeric"
      /><el-button :loading="busy" :disabled="!cid.trim()" @click="lookup"
        >读取类目规则</el-button
      >
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <pre v-if="result">{{ JSON.stringify(result, null, 2) }}</pre>
  </section>
</template>
