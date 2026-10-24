<script setup>
import { onMounted, ref } from "vue";
import { api } from "../api";
defineProps({ user: Object });
const emit = defineEmits(["created"]),
  products = ref([]),
  stores = ref([]),
  chosenProducts = ref([]),
  chosenStores = ref([]),
  action = ref("CREATE_DRAFT"),
  error = ref(""),
  result = ref(null),
  busy = ref(false);
let requestKey = crypto.randomUUID();
async function load() {
  try {
    [products.value, stores.value] = await Promise.all([
      api("/api/products"),
      api("/api/stores"),
    ]);
  } catch (e) {
    error.value = e.message;
  }
}
async function submit() {
  busy.value = true;
  error.value = "";
  result.value = null;
  try {
    result.value = await api("/api/publish-batches", {
      method: "POST",
      body: {
        productIds: chosenProducts.value,
        storeIds: chosenStores.value,
        targetAction: action.value,
        requestKey,
      },
    });
    requestKey = crypto.randomUUID();
    emit("created");
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <section class="panel padded">
    <el-collapse
      ><el-collapse-item title="创建批量任务" name="create"
        ><p class="muted">
          选择已批准商品与店铺，每个商品×店铺生成一个独立任务。重复提交会复用已有任务。
        </p>
        <el-alert
          v-if="error"
          :title="error"
          type="error"
          :closable="false"
        /><el-alert
          v-if="result"
          :title="`批次 #${result.id} 已创建，含 ${result.total_tasks} 个任务`"
          type="success"
          :closable="false"
        /><el-form label-position="top" @submit.prevent="submit"
          ><el-form-item label="已批准商品"
            ><el-select
              v-model="chosenProducts"
              multiple
              filterable
              placeholder="选择商品"
              aria-label="批量任务商品"
              :disabled="user.role === 'REVIEWER'"
              ><el-option
                v-for="p in products"
                :key="p.id"
                :value="p.id"
                :disabled="p.status !== 'APPROVED'"
                :label="`${p.spu_code} · ${p.title}${p.status !== 'APPROVED' ? '（需要审核）' : ''}`" /></el-select></el-form-item
          ><el-form-item label="目标店铺"
            ><el-select
              v-model="chosenStores"
              multiple
              filterable
              placeholder="选择店铺"
              aria-label="批量任务店铺"
              :disabled="user.role === 'REVIEWER'"
              ><el-option
                v-for="s in stores.filter((s) => s.active)"
                :key="s.id"
                :value="s.id"
                :label="`${s.name} · ${s.platform}`" /></el-select></el-form-item
          ><el-radio-group v-model="action"
            ><el-radio value="CREATE_DRAFT">创建线上草稿</el-radio
            ><el-radio value="PUBLISH"
              >TEMU 发布并核验</el-radio
            ></el-radio-group
          >
          <div class="form-actions">
            <span class="muted"
              >分母：{{
                chosenProducts.length * chosenStores.length
              }}
              个商品×店铺任务</span
            ><el-button
              type="primary"
              native-type="submit"
              :loading="busy"
              :disabled="
                user.role === 'REVIEWER' ||
                !chosenProducts.length ||
                !chosenStores.length
              "
              >提交批次</el-button
            >
          </div></el-form
        ></el-collapse-item
      ></el-collapse
    >
  </section>
</template>
