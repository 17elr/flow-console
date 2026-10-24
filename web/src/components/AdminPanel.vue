<script setup>
import { onMounted, ref, watch } from "vue";
import { api } from "../api";
const props = defineProps({ page: String, user: Object }),
  emit = defineEmits(["changed"]);
const stores = ref([]),
  users = ref([]),
  audits = ref([]),
  status = ref({}),
  error = ref(""),
  fields = ref({}),
  busy = ref(false);
const store = ref({
  name: "",
  platform: "TEMU",
  mode: "SEMI",
  external_shop_id: "",
  currency: "USD",
  account_key: "",
  active: true,
});
const member = ref({ username: "", password: "", role: "OPERATOR" });
async function load() {
  error.value = "";
  try {
    if (props.page === "stores")
      [stores.value, status.value] = await Promise.all([
        api("/api/stores"),
        api("/api/miaoshou/status"),
      ]);
    else
      [users.value, audits.value] = await Promise.all([
        api("/api/users"),
        api("/api/audit"),
      ]);
  } catch (e) {
    error.value = e.message;
  }
}
async function saveStore() {
  busy.value = true;
  error.value = "";
  fields.value = {};
  try {
    await api(
      store.value.id ? `/api/stores/${store.value.id}` : "/api/stores",
      { method: store.value.id ? "PUT" : "POST", body: store.value },
    );
    store.value = {
      name: "",
      platform: "TEMU",
      mode: "SEMI",
      external_shop_id: "",
      currency: "USD",
      account_key: "",
      active: true,
    };
    await load();
    emit("changed");
  } catch (e) {
    error.value = e.message;
    fields.value = e.fields || {};
  } finally {
    busy.value = false;
  }
}
async function createMember() {
  busy.value = true;
  error.value = "";
  fields.value = {};
  try {
    await api("/api/users", { method: "POST", body: member.value });
    member.value = { username: "", password: "", role: "OPERATOR" };
    await load();
  } catch (e) {
    error.value = e.message;
    fields.value = e.fields || {};
  } finally {
    busy.value = false;
  }
}
async function changeUser(user) {
  try {
    await api(`/api/users/${user.id}`, {
      method: "PATCH",
      body: { active: !user.active },
    });
    await load();
  } catch (e) {
    error.value = e.message;
  }
}
function editStore(value) {
  store.value = JSON.parse(JSON.stringify(value));
}
watch(() => props.page, load);
onMounted(load);
</script>
<template>
  <div class="page-heading">
    <div>
      <span class="eyebrow">团队管理</span>
      <h1>
        {{
          page === "stores" ? "店铺配置，清晰可控。" : "各司其职，留下记录。"
        }}
      </h1>
      <p>
        {{
          page === "stores"
            ? "平台授权与共享账号配置，变更后需要重新审核商品。"
            : "运营整理资料，审核成员确认，管理员维护配置。"
        }}
      </p>
    </div>
  </div>
  <el-alert
    v-if="error"
    :title="error"
    type="error"
    show-icon
    :closable="false"
  />
  <template v-if="page === 'stores'"
    ><div class="config-banner">
      <span
        class="status"
        :class="status.enabled ? 'APPROVED' : 'NEEDS_REVIEW'"
        >{{
          status.enabled ? "外部平台操作已启用" : "外部平台操作已关闭"
        }}</span
      >
      <p>
        密钥配置：{{ status.configured ? "已配置" : "未配置" }} ·
        AliExpress在线草稿：{{
          status.aliexpress_draft_configured ? "已配置契约" : "未配置契约"
        }}
      </p>
      <small>密钥仅保存在服务端环境中，浏览器不会接收密钥。</small>
    </div>
    <div class="admin-layout">
      <section class="panel padded">
        <h2>已配置店铺</h2>
        <div v-for="s in stores" :key="s.id" class="store-card">
          <div>
            <strong>{{ s.name }}</strong>
            <p>
              {{ s.platform }} · {{ s.mode }} · {{ s.active ? "启用" : "停用" }}
            </p>
            <small
              >授权ID {{ s.external_shop_id || "未配置" }} · 配置版本
              {{ s.config_version }}</small
            >
          </div>
          <el-button v-if="user.role === 'ADMIN'" @click="editStore(s)"
            >编辑</el-button
          >
        </div>
        <el-empty
          v-if="!stores.length"
          description="还没有配置店铺"
          :image-size="70"
        />
      </section>
      <section class="panel padded">
        <h2>{{ store.id ? "编辑店铺" : "添加店铺" }}</h2>
        <p v-if="user.role !== 'ADMIN'" class="permission-note">
          请联系管理员修改店铺配置。
        </p>
        <el-form label-position="top" @submit.prevent="saveStore"
          ><el-form-item label="店铺名称" :error="fields.name"
            ><el-input
              v-model="store.name"
              :disabled="user.role !== 'ADMIN'"
              required
          /></el-form-item>
          <div class="form-grid">
            <el-form-item label="平台"
              ><el-select
                v-model="store.platform"
                :disabled="user.role !== 'ADMIN'"
                @change="
                  store.mode =
                    store.platform === 'ALIEXPRESS' ? 'ALIEXPRESS' : 'SEMI'
                "
                ><el-option label="TEMU" value="TEMU" /><el-option
                  label="AliExpress"
                  value="ALIEXPRESS" /></el-select></el-form-item
            ><el-form-item label="模式"
              ><el-select v-model="store.mode" :disabled="user.role !== 'ADMIN'"
                ><el-option
                  v-if="store.platform === 'TEMU'"
                  label="半托管"
                  value="SEMI" /><el-option
                  v-if="store.platform === 'TEMU'"
                  label="全托管"
                  value="FULL" /><el-option
                  v-else
                  label="AliExpress"
                  value="ALIEXPRESS" /></el-select
            ></el-form-item>
          </div>
          <el-form-item label="真实平台授权ID" :error="fields.external_shop_id"
            ><el-input
              v-model="store.external_shop_id"
              :disabled="user.role !== 'ADMIN'" /></el-form-item
          ><el-form-item label="共享平台账号标识" :error="fields.account_key"
            ><el-input
              v-model="store.account_key"
              :disabled="user.role !== 'ADMIN'"
              placeholder="同一平台账号的店铺必须填写相同标识"
              required /></el-form-item
          ><el-form-item label="币种"
            ><el-input
              v-model="store.currency"
              :disabled="user.role !== 'ADMIN'" /></el-form-item
          ><el-checkbox v-model="store.active" :disabled="user.role !== 'ADMIN'"
            >启用店铺</el-checkbox
          >
          <div class="form-actions">
            <el-button
              v-if="store.id"
              @click="
                store = {
                  name: '',
                  platform: 'TEMU',
                  mode: 'SEMI',
                  external_shop_id: '',
                  currency: 'USD',
                  account_key: '',
                  active: true,
                }
              "
              >取消编辑</el-button
            ><el-button
              type="primary"
              native-type="submit"
              :loading="busy"
              :disabled="user.role !== 'ADMIN'"
              >保存配置</el-button
            >
          </div></el-form
        >
      </section>
    </div></template
  >
  <template v-else
    ><div class="admin-layout">
      <section class="panel padded">
        <h2>团队成员</h2>
        <el-table :data="users"
          ><el-table-column prop="username" label="用户名" /><el-table-column
            prop="role"
            label="角色"
          /><el-table-column label="状态"
            ><template #default="s">{{
              s.row.active ? "启用" : "停用"
            }}</template></el-table-column
          ><el-table-column label="操作"
            ><template #default="s"
              ><el-button
                text
                :disabled="s.row.id === user.id"
                @click="changeUser(s.row)"
                >{{ s.row.active ? "停用" : "启用" }}</el-button
              ></template
            ></el-table-column
          ></el-table
        >
      </section>
      <section class="panel padded">
        <h2>开通账号</h2>
        <el-form label-position="top" @submit.prevent="createMember"
          ><el-form-item label="用户名" :error="fields.username"
            ><el-input
              v-model="member.username"
              autocomplete="off"
              required /></el-form-item
          ><el-form-item label="初始密码（至少12字符）" :error="fields.password"
            ><el-input
              v-model="member.password"
              type="password"
              show-password
              autocomplete="new-password"
              required /></el-form-item
          ><el-form-item label="角色" :error="fields.role"
            ><el-select v-model="member.role"
              ><el-option label="运营成员" value="OPERATOR" /><el-option
                label="审核成员"
                value="REVIEWER" /><el-option
                label="管理员"
                value="ADMIN" /></el-select></el-form-item
          ><el-button type="primary" native-type="submit" :loading="busy"
            >创建成员</el-button
          ></el-form
        >
      </section>
    </div>
    <section class="panel padded">
      <h2>操作审计</h2>
      <el-table :data="audits"
        ><el-table-column
          prop="created_at"
          label="时间"
          min-width="180" /><el-table-column
          prop="user_id"
          label="操作人ID" /><el-table-column
          prop="action"
          label="操作"
          min-width="180" /><el-table-column
          prop="subject_id"
          label="对象ID" /><el-table-column
          prop="detail"
          label="说明"
          min-width="200"
      /></el-table></section
  ></template>
</template>
