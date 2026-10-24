<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import {
  Refresh,
  Search,
  Timer,
  Document,
  CircleCheck,
  Warning,
} from "@element-plus/icons-vue";
import { api, label, terminalStates } from "../api";
import BatchComposer from "./BatchComposer.vue";
const props = defineProps({ user: Object });
const tasks = ref([]),
  packages = ref([]),
  error = ref(""),
  busy = ref(false),
  selected = ref(""),
  operation = ref(null),
  reason = ref(""),
  externalId = ref(""),
  attempts = ref(null),
  schedules = ref([]);
const schedule = ref({
  name: "",
  run_time: "02:00",
  timezone: "Asia/Shanghai",
  product_ids: "",
  store_ids: "",
  target_action: "CREATE_DRAFT",
  active: false,
});
const filtered = computed(() =>
  tasks.value.filter((t) => !selected.value || t.status === selected.value),
);
const counts = computed(() => ({
  draft: tasks.value.filter((t) => t.status === "DRAFT_CREATED").length,
  published: tasks.value.filter(
    (t) => t.status === "SUCCEEDED" && t.target_action === "PUBLISH",
  ).length,
  verifying: tasks.value.filter((t) => t.status === "VERIFYING").length,
  failed: tasks.value.filter((t) =>
    ["FAILED", "NEEDS_REVIEW"].includes(t.status),
  ).length,
}));
let timer,
  controller,
  stopped = false,
  sequence = 0;
function schedulePoll() {
  clearTimeout(timer);
  if (
    !stopped &&
    !document.hidden &&
    tasks.value.some((t) => !terminalStates.has(t.status))
  )
    timer = setTimeout(load, 4000);
}
async function load() {
  clearTimeout(timer);
  controller?.abort();
  controller = new AbortController();
  const version = ++sequence;
  try {
    const [rows, files, configs] = await Promise.all([
      api("/api/publish-tasks", { signal: controller.signal }),
      api("/api/local-packages", { signal: controller.signal }),
      api("/api/automation/schedules", { signal: controller.signal }),
    ]);
    if (version !== sequence || stopped) return;
    tasks.value = rows;
    packages.value = files;
    schedules.value = configs;
    error.value = "";
  } catch (e) {
    if (e.name !== "AbortError") error.value = e.message;
  } finally {
    if (version === sequence) schedulePoll();
  }
}
function visibility() {
  clearTimeout(timer);
  if (document.hidden) {
    controller?.abort();
    sequence++;
  } else load();
}
async function act() {
  if (!reason.value.trim()) return;
  busy.value = true;
  try {
    await api(
      `/api/publish-tasks/${operation.value.id}/${operation.value.action}`,
      {
        method: "POST",
        body: { reason: reason.value, externalId: externalId.value },
      },
    );
    operation.value = null;
    await load();
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function viewAttempts(id) {
  try {
    attempts.value = await api(`/api/publish-tasks/${id}/attempts`);
  } catch (e) {
    error.value = e.message;
  }
}
async function saveSchedule() {
  busy.value = true;
  try {
    const body = {
      ...schedule.value,
      product_ids: schedule.value.product_ids
        .split(",")
        .map((v) => Number(v.trim()))
        .filter(Boolean),
      store_ids: schedule.value.store_ids
        .split(",")
        .map((v) => Number(v.trim()))
        .filter(Boolean),
    };
    await api("/api/automation/schedules", { method: "POST", body });
    await load();
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function toggle(s) {
  try {
    await api(`/api/automation/schedules/${s.id}`, {
      method: "PATCH",
      body: { active: !s.active },
    });
    await load();
  } catch (e) {
    error.value = e.message;
  }
}
onMounted(() => {
  load();
  document.addEventListener("visibilitychange", visibility);
});
onUnmounted(() => {
  stopped = true;
  clearTimeout(timer);
  controller?.abort();
  sequence++;
  document.removeEventListener("visibilitychange", visibility);
});
</script>
<template>
  <div class="page-heading">
    <div>
      <span class="eyebrow">执行与追踪</span>
      <h1>每一次操作，都有去向。</h1>
      <p>仅页面可见且存在未完成任务时自动刷新。</p>
    </div>
    <el-button :icon="Refresh" @click="load">刷新结果</el-button>
  </div>
  <el-alert
    v-if="error"
    :title="error"
    type="error"
    show-icon
    @close="error = ''"
  />
  <div class="metrics">
    <article>
      <span
        ><el-icon><Document /></el-icon>线上草稿</span
      ><strong>{{ counts.draft }}</strong>
      <p>平台返回真实草稿ID</p>
    </article>
    <article>
      <span
        ><el-icon><CircleCheck /></el-icon>已确认发布</span
      ><strong class="green">{{ counts.published }}</strong>
      <p>仅 PUBLISH 目标的权威确认</p>
    </article>
    <article>
      <span
        ><el-icon><Search /></el-icon>待核验</span
      ><strong>{{ counts.verifying }}</strong>
      <p>外部结果未知，先核验</p>
    </article>
    <article>
      <span
        ><el-icon><Warning /></el-icon>失败 / 需要处理</span
      ><strong>{{ counts.failed }}</strong>
      <p>根据错误提示修正或人工处理</p>
    </article>
  </div>
  <BatchComposer :user="user" @created="load" />
  <section class="panel padded">
    <div class="section-heading">
      <div>
        <h2>后台任务</h2>
        <p class="muted">展示最近300个商品×店铺任务；上方统计基于此列表。</p>
      </div>
      <el-select
        v-model="selected"
        clearable
        placeholder="全部任务状态"
        aria-label="筛选任务状态"
        class="compact-select"
        ><el-option
          v-for="s in [
            'PENDING',
            'RUNNING',
            'RETRY_WAIT',
            'DRAFT_CREATED',
            'VERIFYING',
            'SUCCEEDED',
            'NEEDS_REVIEW',
            'FAILED',
            'CANCELLED',
          ]"
          :key="s"
          :label="label(s)"
          :value="s"
      /></el-select>
    </div>
    <el-table :data="filtered" row-key="id"
      ><el-table-column label="任务 / 商品" min-width="190"
        ><template #default="s"
          ><strong>#{{ s.row.id }} · {{ s.row.spu_code }}</strong
          ><small class="cell-sub">{{ s.row.title }}</small></template
        ></el-table-column
      ><el-table-column label="店铺 / 目标" min-width="160"
        ><template #default="s"
          >{{ s.row.store_name
          }}<small class="cell-sub"
            >{{ s.row.platform }} ·
            {{
              s.row.target_action === "PUBLISH" ? "正式发布" : "创建草稿"
            }}</small
          ></template
        ></el-table-column
      ><el-table-column label="状态" min-width="135"
        ><template #default="s"
          ><span class="status" :class="s.row.status">{{
            label(s.row.status)
          }}</span
          ><small v-if="s.row.external_status" class="cell-sub"
            >外部：{{ s.row.external_status }}</small
          ></template
        ></el-table-column
      ><el-table-column
        prop="external_id"
        label="外部ID"
        min-width="130"
      /><el-table-column label="进度与问题" min-width="200"
        ><template #default="s"
          ><span>{{ s.row.stage }} · 重试 {{ s.row.attempt }} 次</span
          ><small v-if="s.row.last_error" class="cell-sub error-text">{{
            s.row.last_error
          }}</small></template
        ></el-table-column
      ><el-table-column label="操作" min-width="180"
        ><template #default="s"
          ><el-button text @click="viewAttempts(s.row.id)">详情</el-button
          ><template v-if="['ADMIN', 'REVIEWER'].includes(user.role)"
            ><el-button
              v-if="
                [
                  'VERIFYING',
                  'NEEDS_REVIEW',
                  'DRAFT_CREATED',
                  'SUCCEEDED',
                ].includes(s.row.status) && s.row.external_id
              "
              text
              @click="
                operation = { id: s.row.id, action: 'verify' };
                reason = '';
              "
              >重新核验</el-button
            ><el-button
              v-if="s.row.status === 'NEEDS_REVIEW' &amp;&amp; !s.row.external_id"
              text
              @click="
                operation = { id: s.row.id, action: 'resolve' };
                reason = '';
                externalId = '';
              "
              >补充核查ID</el-button
            ><el-button
              v-if="s.row.status === 'FAILED'"
              text
              @click="
                operation = { id: s.row.id, action: 'retry' };
                reason = '';
              "
              >重试</el-button
            ><el-button
              v-if="['PENDING', 'RETRY_WAIT'].includes(s.row.status)"
              text
              type="danger"
              @click="
                operation = { id: s.row.id, action: 'cancel' };
                reason = '';
              "
              >取消</el-button
            ></template
          ></template
        ></el-table-column
      ></el-table
    ><el-empty
      v-if="!tasks.length"
      description="暂时没有任务。请先审核商品，再选择店铺创建任务。"
      :image-size="75"
    />
  </section>
  <section class="panel padded">
    <h2>AliExpress 本地导入包</h2>
    <p class="muted">
      PACKAGE_READY 仅表示文件就绪，不计入线上草稿或发布数量。
    </p>
    <el-table :data="packages"
      ><el-table-column prop="id" label="编号" width="90" /><el-table-column
        prop="product_id"
        label="商品ID"
      /><el-table-column label="状态"
        ><template #default>本地包已生成</template></el-table-column
      ><el-table-column
        prop="created_at"
        label="生成时间"
        min-width="170"
      /><el-table-column label="文件"
        ><template #default="s"
          ><a :href="`/api/local-packages/${s.row.id}/content`"
            >下载导入包</a
          ></template
        ></el-table-column
      ></el-table
    >
  </section>
  <section class="panel padded">
    <h2>
      <el-icon><Timer /></el-icon>定时任务
    </h2>
    <p class="muted">
      只对已批准的指定商品创建任务，按指定时区执行。新建配置默认关闭。
    </p>
    <el-table :data="schedules"
      ><el-table-column prop="name" label="计划" /><el-table-column
        prop="run_time"
        label="每日时间"
      /><el-table-column prop="timezone" label="时区" /><el-table-column
        label="状态"
        ><template #default="s">{{
          s.row.active ? "已启用" : "已停用"
        }}</template></el-table-column
      ><el-table-column v-if="user.role === 'ADMIN'" label="操作"
        ><template #default="s"
          ><el-button text @click="toggle(s.row)">{{
            s.row.active ? "停用" : "启用"
          }}</el-button></template
        ></el-table-column
      ></el-table
    ><el-collapse v-if="user.role === 'ADMIN'"
      ><el-collapse-item title="新建每日计划"
        ><el-form label-position="top" @submit.prevent="saveSchedule"
          ><div class="form-grid">
            <el-form-item label="计划名称"
              ><el-input v-model="schedule.name" required /></el-form-item
            ><el-form-item label="时间（HH:mm）"
              ><el-input v-model="schedule.run_time" required /></el-form-item
            ><el-form-item label="IANA时区"
              ><el-input v-model="schedule.timezone" required /></el-form-item
            ><el-form-item label="商品ID（逗号分隔）"
              ><el-input
                v-model="schedule.product_ids"
                required /></el-form-item
            ><el-form-item label="店铺ID（逗号分隔）"
              ><el-input v-model="schedule.store_ids" required /></el-form-item
            ><el-form-item label="目标动作"
              ><el-select v-model="schedule.target_action"
                ><el-option label="创建草稿" value="CREATE_DRAFT" /><el-option
                  label="TEMU 发布并核验"
                  value="PUBLISH" /></el-select
            ></el-form-item>
          </div>
          <el-button type="primary" native-type="submit" :loading="busy"
            >保存为停用计划</el-button
          ></el-form
        ></el-collapse-item
      ></el-collapse
    >
  </section>
  <el-dialog
    :model-value="Boolean(operation)"
    title="填写操作原因"
    width="min(480px, 94vw)"
    @close="operation = null"
    ><el-form @submit.prevent="act"
      ><el-form-item
        v-if="operation?.action === 'resolve'"
        label="人工核查得到的真实外部ID"
        ><el-input v-model="externalId" required /></el-form-item
      ><el-form-item label="原因"
        ><el-input
          v-model="reason"
          type="textarea"
          :rows="3"
          maxlength="500"
          required
      /></el-form-item>
      <p class="muted">重试不会绕过审核、目标唯一约束或未知结果核验。</p>
      <el-button
        type="primary"
        native-type="submit"
        :loading="busy"
        :disabled="!reason.trim()"
        >确认操作</el-button
      ></el-form
    ></el-dialog
  >
  <el-dialog
    :model-value="attempts !== null"
    title="执行证据与尝试记录"
    width="min(800px, 94vw)"
    @close="attempts = null"
    ><div v-for="item in attempts" :key="item.id" class="attempt-record">
      <strong
        >{{ item.stage }} · HTTP {{ item.http_code || "未收到响应" }}</strong
      >
      <p>{{ item.error }}</p>
      <small>{{ item.started_at }} → {{ item.finished_at }}</small>
      <details>
        <summary>查看脱敏响应</summary>
        <pre>{{ item.response_json }}</pre>
      </details>
    </div>
    <el-empty
      v-if="!attempts?.length"
      description="尚未开始外部请求"
      :image-size="65"
  /></el-dialog>
</template>
