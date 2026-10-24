<script setup>
import { ref } from "vue";
import { ElMessageBox } from "element-plus";
import { api } from "../api";
defineProps({ records: Array, reviewer: Boolean });
const emit = defineEmits(["changed"]),
  busy = ref(false),
  error = ref("");
async function verify(row) {
  let reason, externalId;
  try {
    reason = (
      await ElMessageBox.prompt(
        "记录核查原因；核验只读取权威状态，不创建线上商品。",
        "核验历史记录",
        { inputValidator: (v) => Boolean(v?.trim()) || "请填写核查原因" },
      )
    ).value;
    if (!row.external_id)
      externalId = (
        await ElMessageBox.prompt(
          "填写人工核查得到的真实平台商品ID。",
          "补充历史外部ID",
          {
            inputValidator: (v) =>
              /^[a-zA-Z0-9_-]{1,160}$/.test(v || "") || "请输入有效外部ID",
          },
        )
      ).value;
  } catch {
    return;
  }
  busy.value = true;
  error.value = "";
  try {
    await api(`/api/legacy-external/${row.id}/verify`, {
      method: "POST",
      body: { reason, externalId },
    });
    emit("changed");
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <section v-if="records?.length" class="subsection">
    <h3>历史平台记录</h3>
    <p class="muted">
      保留原外部ID与原状态。历史“已发布”不自动计为已确认发布，也不会自动重放。
    </p>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
    /><el-table :data="records"
      ><el-table-column
        prop="external_id"
        label="原外部ID"
        min-width="130"
      /><el-table-column
        prop="original_status"
        label="原状态"
      /><el-table-column label="核验"
        ><template #default="s">{{
          s.row.status === "HISTORICAL_UNVERIFIED" ? "历史待核验" : s.row.status
        }}</template></el-table-column
      ><el-table-column v-if="reviewer" label="操作"
        ><template #default="s"
          ><el-button text :loading="busy" @click="verify(s.row)"
            >读取权威状态</el-button
          ></template
        ></el-table-column
      ></el-table
    >
  </section>
</template>
