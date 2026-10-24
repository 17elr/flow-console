<script setup>
import { computed, onUnmounted, ref, watch } from "vue";
import { ElMessageBox } from "element-plus";
import {
  Check,
  Upload,
  Plus,
  Delete,
  Document,
  Picture,
  ArrowRight,
} from "@element-plus/icons-vue";
import { api, mainRoles, roleLabels, label } from "../api";
import { productDrafts as drafts } from "../drafts";
import SkuComponents from "./SkuComponents.vue";
import ImageTools from "./ImageTools.vue";
import LegacyHistory from "./LegacyHistory.vue";
import PackagingLibrary from "./PackagingLibrary.vue";
import CategoryRules from "./CategoryRules.vue";
const props = defineProps({ id: Number, user: Object }),
  emit = defineEmits(["changed", "tasks"]);
const detail = ref(null),
  form = ref({}),
  tab = ref("facts"),
  error = ref(""),
  fields = ref({}),
  busy = ref(false),
  loading = ref(false);
const copies = ref({
    TEMU: { title: "", description: "", bullet_points: "" },
    ALIEXPRESS: { title: "", description: "", bullet_points: "" },
  }),
  platform = ref("TEMU"),
  platformJson = ref("{}");
const reviewNote = ref(""),
  stores = ref([]),
  chosenStores = ref([]),
  action = ref("CREATE_DRAFT"),
  batch = ref(null),
  readiness = ref([]),
  library = ref([]),
  reused = ref(null),
  documentKind = ref("reach");
const transform = ref({
  asset: null,
  operation: "RESIZE",
  size: 1200,
  role: "SPU_WHITE_MAIN",
  x: 0,
  y: 0,
  width: 400,
  height: 400,
});
const editable = computed(() => props.user.role !== "REVIEWER"),
  reviewer = computed(() => ["ADMIN", "REVIEWER"].includes(props.user.role));
const currentCopy = computed(() => copies.value[platform.value]),
  allAssets = computed(() => detail.value?.assets || []);
const documents = computed(() =>
  allAssets.value.filter((a) => a.source === "COMPLIANCE"),
);
const slots = computed(() => [
  ...mainRoles.map((role) => ({ role, name: roleLabels[role] })),
  ...(detail.value?.skus || []).map((s) => ({
    role: "SKU_IMAGE",
    sku: s.id,
    name: `SKU · ${s.sku_code}`,
  })),
]);
function latest(slot) {
  return allAssets.value
    .filter(
      (a) => a.role === slot.role && (a.sku_id || null) === (slot.sku || null),
    )
    .at(-1);
}
let controller,
  sequence = 0;
const draftKey = (id) => `${props.user.id}:${id || "new"}`;
function remember(id) {
  if (Object.keys(form.value).length)
    drafts.set(draftKey(id), {
      form: JSON.parse(JSON.stringify(form.value)),
      platformJson: platformJson.value,
      copies: JSON.parse(JSON.stringify(copies.value)),
    });
}
function blank() {
  return {
    spu_code: "",
    title: "",
    category: "",
    material: "",
    color: "",
    dimensions: "",
    weight_g: "",
    price: "",
    cost: "",
    currency: "USD",
    stock: 0,
    image_rights: "UNKNOWN",
    skus: [
      {
        sku_code: "",
        name: "",
        size: "",
        color: "",
        quantity: "",
        price: "",
        stock: "",
      },
    ],
  };
}
async function load(id = props.id, preserve = false) {
  controller?.abort();
  controller = new AbortController();
  const version = ++sequence;
  loading.value = true;
  error.value = "";
  fields.value = {};
  batch.value = null;
  try {
    const [data, storeList, files] = await Promise.all([
      id
        ? api(`/api/products/${id}/workflow`, { signal: controller.signal })
        : null,
      api("/api/stores", { signal: controller.signal }),
      api("/api/compliance-library", { signal: controller.signal }),
    ]);
    if (version !== sequence) return;
    detail.value = data?.product || null;
    readiness.value = data?.blockers || [];
    stores.value = storeList;
    library.value = files;
    if (!preserve) {
      const draft = drafts.get(draftKey(id));
      form.value =
        draft?.form || (data ? structuredClone(data.product) : blank());
      platformJson.value =
        draft?.platformJson ||
        JSON.stringify(data?.product.platform_payload || {}, null, 2);
      for (const name of ["TEMU", "ALIEXPRESS"]) {
        const copy = data?.product.listing_copies.find(
          (c) => c.platform === name,
        );
        copies.value[name] = {
          title: copy?.title || "",
          description: copy?.description || "",
          bullet_points: copy
            ? JSON.parse(copy.bullet_points_json).join("\n")
            : "",
        };
      }
      if (draft?.copies) copies.value = draft.copies;
    }
  } catch (e) {
    if (e.name !== "AbortError" && version === sequence)
      error.value = e.message;
  } finally {
    if (version === sequence) loading.value = false;
  }
}
watch(
  () => props.id,
  (id, old) => {
    remember(old);
    tab.value = "facts";
    chosenStores.value = [];
    load(id);
  },
  { immediate: true },
);
onUnmounted(() => {
  remember(props.id);
  controller?.abort();
  sequence++;
});
defineExpose({ refresh: () => load(props.id) });
async function run(fn, { reload = true } = {}) {
  busy.value = true;
  error.value = "";
  fields.value = {};
  try {
    const result = await fn();
    if (reload) {
      drafts.delete(draftKey(props.id));
      await load();
      emit("changed");
    }
    return result;
  } catch (e) {
    error.value = `${e.message}${e.requestId ? `（请求 ${e.requestId.slice(0, 8)}）` : ""}`;
    fields.value = e.fields || {};
  } finally {
    busy.value = false;
  }
}
async function save() {
  let payload;
  try {
    payload = JSON.parse(platformJson.value);
  } catch {
    error.value = "平台参数必须是有效JSON对象";
    fields.value.platform_payload = error.value;
    return;
  }
  if (!payload || Array.isArray(payload) || typeof payload !== "object") {
    error.value = "平台参数必须是JSON对象";
    return;
  }
  const result = await run(
    () =>
      api(props.id ? `/api/products/${props.id}` : "/api/products", {
        method: props.id ? "PATCH" : "POST",
        body: { ...form.value, platform_payload: payload },
      }),
    { reload: false },
  );
  if (result) {
    drafts.delete(draftKey(props.id));
    if (props.id) await load();
    emit("changed", result.id);
  }
}
function addSku() {
  form.value.skus.push({
    sku_code: "",
    name: "",
    color: "",
    size: "",
    quantity: "",
    price: "",
    stock: "",
  });
}
async function upload(event, slot, source = "FINISHED") {
  const file = event.target.files[0];
  if (!file || !props.id) return;
  const body = new FormData();
  body.append("file", file);
  body.append("product_id", props.id);
  body.append("role", slot.role);
  body.append("source", source);
  if (slot.sku) body.append("sku_id", slot.sku);
  await run(() => api("/api/source-assets", { method: "POST", body }), {
    reload: false,
  });
  await load(props.id, true);
  emit("changed");
  event.target.value = "";
}
async function copySave(generate = false) {
  const value = currentCopy.value;
  const result = await run(
    () =>
      api(`/api/products/${props.id}/listing-copies`, {
        method: "POST",
        body: generate
          ? { platform: platform.value }
          : {
              platform: platform.value,
              ...value,
              bullet_points: value.bullet_points
                .split("\n")
                .map((v) => v.trim())
                .filter(Boolean),
            },
      }),
    { reload: false },
  );
  if (!result) return;
  await load(props.id, true);
  const stored = detail.value?.listing_copies.find(
    (c) => c.platform === platform.value,
  );
  if (stored && !error.value)
    copies.value[platform.value] = {
      title: stored.title,
      description: stored.description,
      bullet_points: JSON.parse(stored.bullet_points_json).join("\n"),
    };
  emit("changed");
}
async function decide(decision) {
  try {
    await ElMessageBox.confirm(
      decision === "APPROVED"
        ? "确认已检查本版本的商品事实、SKU、成品图、文案及平台参数？后续改动会使本次批准失效。"
        : "确认拒绝当前版本？请在备注中写明需要补充的内容。",
      "人工审核",
      {
        confirmButtonText: decision === "APPROVED" ? "确认批准" : "确认拒绝",
        cancelButtonText: "继续检查",
      },
    );
  } catch {
    return;
  }
  await run(() =>
    api(`/api/products/${props.id}/review`, {
      method: "PUT",
      body: {
        decision,
        note: reviewNote.value,
        content_version: detail.value.content_version,
      },
    }),
  );
}
async function createBatch() {
  const result = await run(
    () =>
      api("/api/publish-batches", {
        method: "POST",
        body: {
          productIds: [props.id],
          storeIds: chosenStores.value,
          targetAction: action.value,
          requestKey: crypto.randomUUID(),
        },
      }),
    { reload: false },
  );
  if (result) batch.value = result;
}
async function downloadPackage() {
  const result = await run(
    () =>
      api(`/api/products/${props.id}/aliexpress-import-package`, {
        method: "POST",
        body: { store_id: chosenStores.value[0] },
      }),
    { reload: false },
  );
  if (result) window.location.assign(result.download_url);
}
async function uploadDocument(event) {
  const file = event.target.files[0];
  if (!file) return;
  const body = new FormData();
  body.append("file", file);
  body.append("kind", documentKind.value);
  await run(
    () => api(`/api/products/${props.id}/compliance`, { method: "POST", body }),
    { reload: false },
  );
  await load(props.id, true);
  event.target.value = "";
}
async function archive() {
  try {
    await ElMessageBox.confirm(
      "归档后商品将从工作列表隐藏，历史记录与素材继续保留。",
      "归档商品",
      { type: "warning" },
    );
    await run(() => api(`/api/products/${props.id}`, { method: "DELETE" }));
    emit("changed");
  } catch {
    /* User cancelled. */
  }
}
</script>

<template>
  <section class="product-detail panel" v-loading="loading">
    <div class="detail-title">
      <div>
        <span class="eyebrow"
          >{{ detail?.spu_code || "新商品" }}
          <span v-if="detail"
            >/ 内容版本 {{ detail.content_version }}</span
          ></span
        >
        <h2>{{ detail?.title || "创建商品资料" }}</h2>
      </div>
      <span v-if="detail" class="status" :class="detail.status">{{
        label(detail.status)
      }}</span>
    </div>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
      role="alert"
    />
    <el-tabs v-model="tab" class="workflow-tabs"
      ><el-tab-pane label="商品资料" name="facts" /><el-tab-pane
        label="图片与素材"
        name="images"
        :disabled="!id" /><el-tab-pane
        label="平台文案"
        name="copies"
        :disabled="!id" /><el-tab-pane
        label="人工审核"
        name="review"
        :disabled="!id" /><el-tab-pane
        label="店铺与上架"
        name="publish"
        :disabled="!id" /><el-tab-pane
        label="合规文件"
        name="compliance"
        :disabled="!id"
    /></el-tabs>
    <div v-if="tab === 'facts'" class="tab-content">
      <div class="section-heading">
        <div>
          <h3>商品事实</h3>
          <p class="muted">只填写真实信息。金额保留输入精度。</p>
        </div>
        <el-button v-if="id && editable" text type="danger" @click="archive"
          >归档商品</el-button
        >
      </div>
      <el-form label-position="top" @submit.prevent="save"
        ><div class="form-grid">
          <el-form-item
            v-for="field in [
              { key: 'spu_code', name: '商品货号 / SPU', required: true },
              { key: 'title', name: '商品名称', required: true },
              { key: 'category', name: '商品类目' },
              { key: 'material', name: '真实材质' },
              { key: 'color', name: '颜色' },
              { key: 'dimensions', name: '真实尺寸' },
              { key: 'weight_g', name: '重量（g）' },
              { key: 'price', name: '销售价格' },
              { key: 'cost', name: '成本' },
              { key: 'currency', name: '币种' },
              { key: 'stock', name: '库存' },
            ]"
            :key="field.key"
            :label="field.name"
            :error="fields[field.key]"
            :required="field.required"
            ><el-input
              v-model="form[field.key]"
              :aria-label="field.name"
              :disabled="!editable"
              :inputmode="
                ['price', 'cost', 'weight_g', 'stock'].includes(field.key)
                  ? 'decimal'
                  : 'text'
              " /></el-form-item
          ><el-form-item label="图片使用权" :error="fields.image_rights"
            ><el-select
              v-model="form.image_rights"
              aria-label="图片使用权"
              :disabled="!editable"
              ><el-option label="尚未确认" value="UNKNOWN" /><el-option
                label="自主拍摄 / 自有"
                value="OWNED" /><el-option
                label="已取得授权"
                value="AUTHORIZED" /></el-select
          ></el-form-item>
        </div>
        <div class="section-heading">
          <div>
            <h3>SKU 规格</h3>
            <p class="muted">每个SKU单独填写价格、库存和商品数量。</p>
          </div>
          <el-button v-if="editable" :icon="Plus" @click="addSku"
            >添加规格</el-button
          >
        </div>
        <p v-if="fields.sku_code || fields.quantity" class="field-error">
          {{ fields.sku_code || fields.quantity }}
        </p>
        <div
          v-for="(sku, index) in form.skus"
          :key="sku.id || index"
          class="sku-editor"
        >
          <el-form-item
            v-for="field in [
              { key: 'sku_code', label: 'SKU编码' },
              { key: 'size', label: '规格尺寸' },
              { key: 'color', label: '颜色' },
              { key: 'quantity', label: '件数' },
              { key: 'price', label: '售价' },
              { key: 'stock', label: '库存' },
            ]"
            :key="field.key"
            :label="field.label"
            :error="fields[field.key]"
            ><el-input
              v-model="sku[field.key]"
              :aria-label="`${field.label} ${index + 1}`"
              :disabled="
                !editable || (field.key === 'sku_code' && Boolean(sku.id))
              "
          /></el-form-item>
          <p v-if="sku.components?.length" class="component-summary">
            套装组件：{{
              sku.components
                .map((c) => `${c.component_name} × ${c.quantity}`)
                .join("、")
            }}
          </p>
        </div>
        <el-collapse
          ><el-collapse-item
            title="平台发布参数（经核对的接口参数）"
            name="platform"
            ><p class="muted">
              保留真实类目、属性ID、包装及SKU映射。缺少完整契约时系统会阻止外部请求。
            </p>
            <el-form-item :error="fields.platform_payload"
              ><el-input
                v-model="platformJson"
                type="textarea"
                :rows="9"
                aria-label="平台发布参数JSON"
                :disabled="!editable" /></el-form-item
            ><CategoryRules /></el-collapse-item
        ></el-collapse>
        <div class="form-actions">
          <span class="muted">保存修改后，当前批准将失效。</span
          ><el-button
            v-if="editable"
            type="primary"
            native-type="submit"
            :loading="busy"
            >保存商品资料</el-button
          >
        </div></el-form
      ><SkuComponents
        :skus="detail?.skus || []"
        :editable="editable"
        @changed="
          load(id, true);
          emit('changed');
        "
      />
    </div>
    <div v-else-if="tab === 'images'" class="tab-content">
      <div class="section-heading">
        <div>
          <h3>六张主图与SKU独立图</h3>
          <p class="muted">按顺序上传真实成品图，替换会保留历史版本。</p>
        </div>
      </div>
      <div class="asset-grid">
        <article v-for="slot in slots" :key="slot.name" class="asset-card">
          <a
            v-if="latest(slot)"
            :href="`/api/assets/${latest(slot).id}/content`"
            target="_blank"
            rel="noopener"
            ><img
              :src="`/api/assets/${latest(slot).id}/content`"
              :alt="slot.name"
          /></a>
          <div v-else class="asset-empty">
            <el-icon :size="30"><Picture /></el-icon><span>等待上传</span>
          </div>
          <div class="asset-meta">
            <strong>{{ slot.name }}</strong
            ><small v-if="latest(slot)"
              >版本 {{ latest(slot).version }} · {{ latest(slot).source
              }}<br />{{ latest(slot).width }} ×
              {{ latest(slot).height }} px</small
            ><label v-if="editable" class="file-button"
              >{{ latest(slot) ? "上传新版本" : "选择图片"
              }}<input
                type="file"
                accept="image/png,image/jpeg"
                :aria-label="`上传${slot.name}`"
                :disabled="busy"
                @change="upload($event, slot)"
            /></label>
          </div>
        </article>
      </div>
      <div class="subsection">
        <h3>原始素材与基础处理</h3>
        <label v-if="editable" class="file-button"
          ><el-icon><Upload /></el-icon>上传原始图片<input
            type="file"
            accept="image/png,image/jpeg"
            aria-label="上传原始图片"
            @change="upload($event, { role: 'SOURCE_MAIN' }, 'SOURCE')"
        /></label>
        <div class="inline-controls">
          <el-select
            v-model="transform.asset"
            placeholder="选择原图或历史素材"
            aria-label="处理输入图片"
            ><el-option
              v-for="a in allAssets.filter((a) =>
                a.mime_type.startsWith('image/'),
              )"
              :key="a.id"
              :value="a.id"
              :label="`${roleLabels[a.role] || a.role} · v${a.version} #${a.id}`" /></el-select
          ><el-select v-model="transform.operation" aria-label="图片处理操作"
            ><el-option label="缩放至画布" value="RESIZE" /><el-option
              label="裁剪指定区域"
              value="CROP" /><el-option
              label="添加真实尺寸信息"
              value="SIZE_CARD" /></el-select
          ><el-select v-model="transform.role" aria-label="输出槽位"
            ><el-option
              v-for="role in mainRoles"
              :key="role"
              :value="role"
              :label="roleLabels[role]"
          /></el-select>
        </div>
        <div class="inline-controls">
          <label
            >输出大小<el-input-number
              v-model="transform.size"
              :min="64"
              :max="2400" /></label
          ><template v-if="transform.operation === 'CROP'"
            ><label v-for="key in ['x', 'y', 'width', 'height']" :key="key"
              >{{ key
              }}<el-input-number
                v-model="transform[key]"
                :min="key === 'x' || key === 'y' ? 0 : 1" /></label></template
          ><el-button
            type="primary"
            :loading="busy"
            :disabled="!transform.asset || !editable"
            @click="
              run(() =>
                api(`/api/assets/${transform.asset}/transform`, {
                  method: 'POST',
                  body: transform,
                }),
              )
            "
            >执行基础处理</el-button
          >
        </div>
        <el-alert
          title="基础处理提供裁剪、缩放与尺寸标注。模特、场景、OCR和抠图能力需单独配置，不会用替代图片冒充生成结果。"
          type="info"
          :closable="false"
        />
      </div>
      <ImageTools
        :assets="allAssets"
        :editable="editable"
        @changed="
          load(id, true);
          emit('changed');
        "
      />
    </div>
    <div v-else-if="tab === 'copies'" class="tab-content">
      <div class="section-heading">
        <div>
          <h3>平台英文文案</h3>
          <p class="muted">
            按商品事实与规则模板起草，请人工检查英文与平台要求。
          </p>
        </div>
        <el-segmented v-model="platform" :options="['TEMU', 'ALIEXPRESS']" />
      </div>
      <el-form label-position="top" @submit.prevent="copySave()"
        ><el-form-item label="英文标题" :error="fields.title"
          ><el-input
            v-model="currentCopy.title"
            :disabled="!editable" /></el-form-item
        ><el-form-item label="商品要点（每行一条）"
          ><el-input
            v-model="currentCopy.bullet_points"
            type="textarea"
            :rows="4"
            :disabled="!editable" /></el-form-item
        ><el-form-item label="英文描述"
          ><el-input
            v-model="currentCopy.description"
            type="textarea"
            :rows="7"
            :disabled="!editable"
        /></el-form-item>
        <div v-if="editable" class="form-actions">
          <el-button :loading="busy" @click="copySave(true)"
            >按事实生成模板</el-button
          ><el-button type="primary" native-type="submit" :loading="busy"
            >保存文案</el-button
          >
        </div></el-form
      >
      <p class="muted">当前文案由确定性规则模板生成，未使用文本大模型。</p>
    </div>
    <div v-else-if="tab === 'review'" class="tab-content">
      <div class="section-heading">
        <div>
          <h3>人工审核 · 版本 {{ detail.content_version }}</h3>
          <p class="muted">批准绑定本版本商品、素材、文案和店铺配置。</p>
        </div>
        <span class="status" :class="detail.status">{{
          label(detail.status)
        }}</span>
      </div>
      <el-alert
        v-if="readiness.length"
        title="以下项目需要补齐"
        type="warning"
        :closable="false"
        ><ul class="blocker-list">
          <li v-for="item in readiness" :key="item">{{ item }}</li>
        </ul></el-alert
      ><el-alert
        v-else
        title="资料检查已通过，请继续核对图片、文案与平台参数的真实性。"
        type="success"
        :closable="false"
      />
      <p v-if="!reviewer" class="permission-note">
        运营成员可整理资料，请交由审核成员或管理员批准。最后修改人不能批准自己的修改。
      </p>
      <el-form-item label="审核备注"
        ><el-input
          v-model="reviewNote"
          type="textarea"
          :rows="3"
          placeholder="填写拒绝原因或核对说明"
          :disabled="!reviewer"
      /></el-form-item>
      <div class="form-actions">
        <el-button
          type="danger"
          plain
          :disabled="!reviewer"
          :loading="busy"
          @click="decide('REJECTED')"
          >拒绝并退回</el-button
        ><el-button
          type="primary"
          :icon="Check"
          :disabled="!reviewer || readiness.length > 0"
          :loading="busy"
          @click="decide('APPROVED')"
          >批准当前版本</el-button
        >
      </div>
      <h3>审核记录</h3>
      <div
        v-for="review in [...detail.reviews].reverse()"
        :key="review.id"
        class="review-record"
      >
        <span class="status" :class="review.decision">{{
          label(review.decision)
        }}</span
        ><strong>版本 {{ review.approved_version }}</strong
        ><span>{{
          review.reviewer_id
            ? `审核人 #${review.reviewer_id}`
            : "历史记录 · 无已验证审核人"
        }}</span>
        <p>{{ review.note || "无备注" }}</p>
        <small>{{ review.created_at }}</small>
      </div>
      <el-empty
        v-if="!detail.reviews.length"
        description="尚无审核记录"
        :image-size="65"
      />
    </div>
    <div v-else-if="tab === 'publish'" class="tab-content">
      <h3>选择目标店铺与操作</h3>
      <p class="muted">
        创建后返回任务编号；平台执行与权威状态核验在后台进行。
      </p>
      <el-alert
        v-if="detail.status !== 'APPROVED'"
        title="当前内容尚未批准，请先完成人工审核。"
        type="warning"
        :closable="false"
      /><el-checkbox-group v-model="chosenStores" class="store-choices"
        ><el-checkbox
          v-for="store in stores.filter((s) => s.active)"
          :key="store.id"
          :value="store.id"
          border
          ><strong>{{ store.name }}</strong
          ><span>{{ store.platform }} · {{ store.mode }}</span></el-checkbox
        ></el-checkbox-group
      ><el-empty
        v-if="!stores.length"
        description="尚未配置店铺，请联系管理员"
        :image-size="65"
      /><el-radio-group v-model="action"
        ><el-radio value="CREATE_DRAFT">只创建线上草稿</el-radio
        ><el-radio value="PUBLISH"
          >TEMU 提交发布并核验</el-radio
        ></el-radio-group
      >
      <div class="form-actions">
        <el-button
          type="primary"
          :disabled="
            !editable || !chosenStores.length || detail.status !== 'APPROVED'
          "
          :loading="busy"
          @click="createBatch"
          >创建后台任务 <el-icon><ArrowRight /></el-icon
        ></el-button>
      </div>
      <el-alert
        v-if="batch"
        :title="`批次 #${batch.id} 已创建 · ${batch.total_tasks} 个任务`"
        type="success"
        :closable="false"
        ><el-button text @click="emit('tasks')"
          >查看任务进度</el-button
        ></el-alert
      >
      <div class="subsection">
        <h3>AliExpress 本地导入包</h3>
        <p class="muted">
          生成可下载文件，状态为 PACKAGE_READY，不代表已创建线上草稿或已发布。
        </p>
        <el-button
          :disabled="!editable || detail.status !== 'APPROVED'"
          :loading="busy"
          @click="downloadPackage"
          >生成并下载本地包</el-button
        >
      </div>
      <LegacyHistory
        :records="detail.legacy_results"
        :reviewer="reviewer"
        @changed="load(id, true)"
      />
    </div>
    <div v-else-if="tab === 'compliance'" class="tab-content">
      <h3>合规材料与包装</h3>
      <p class="muted">文件只作资料保存与文本提取，上传不代表获得认证。</p>
      <div class="inline-controls">
        <el-select v-model="documentKind" aria-label="合规文件类型"
          ><el-option label="REACH 检测报告" value="reach" /><el-option
            label="标签或包装图"
            value="label" /><el-option
            label="其他资质"
            value="other" /></el-select
        ><label v-if="editable" class="file-button"
          ><el-icon><Upload /></el-icon>上传合规文件<input
            type="file"
            accept=".pdf,.pptx,.png,.jpg,.jpeg"
            aria-label="上传合规文件"
            @change="uploadDocument"
        /></label>
      </div>
      <div v-for="doc in documents" :key="doc.id" class="document-row">
        <el-icon><Document /></el-icon>
        <div>
          <strong>{{ doc.original_filename }}</strong
          ><small
            >{{ roleLabels[doc.role] }} ·
            {{ Math.ceil(doc.byte_size / 1024) }} KB</small
          >
          <details v-if="JSON.parse(doc.metadata_json).extracted_text">
            <summary>查看提取文本</summary>
            <pre>{{ JSON.parse(doc.metadata_json).extracted_text }}</pre>
          </details>
        </div>
        <a :href="`/api/assets/${doc.id}/content`">下载</a>
      </div>
      <el-empty
        v-if="!documents.length"
        description="尚无合规材料"
        :image-size="65"
      />
      <div class="inline-controls">
        <el-select
          v-model="reused"
          placeholder="从团队资料库选择已有文件"
          aria-label="复用合规文件"
          ><el-option
            v-for="doc in library"
            :key="doc.id"
            :value="doc.id"
            :label="`#${doc.id} ${doc.original_filename}`" /></el-select
        ><el-button
          :disabled="!reused || !editable"
          :loading="busy"
          @click="
            run(() =>
              api(`/api/products/${id}/compliance/${reused}/reuse`, {
                method: 'POST',
              }),
            )
          "
          >复用文件</el-button
        >
      </div>
      <div class="subsection">
        <h3>包装素材</h3>
        <label v-if="editable" class="file-button"
          >上传包装图<input
            type="file"
            accept="image/png,image/jpeg"
            aria-label="上传包装图"
            @change="upload($event, { role: 'PACKAGING' }, 'PACKAGING')"
        /></label>
        <PackagingLibrary
          :id="id"
          :editable="editable"
          @changed="
            load(id, true);
            emit('changed');
          "
        />
        <div class="packaging-images">
          <img
            v-for="a in allAssets.filter((a) => a.source === 'PACKAGING')"
            :key="a.id"
            :src="`/api/assets/${a.id}/content`"
            :alt="`包装素材版本${a.version}`"
          />
        </div>
      </div>
    </div>
  </section>
</template>
