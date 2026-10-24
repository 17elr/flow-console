<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import {
  Box,
  Upload,
  List,
  Shop,
  DocumentChecked,
  SwitchButton,
  ArrowRight,
  Refresh,
  Search,
} from "@element-plus/icons-vue";
import { api, refreshCsrf, label } from "./api";
import ProductPanel from "./components/ProductPanel.vue";
import ImportPanel from "./components/ImportPanel.vue";
import TaskPanel from "./components/TaskPanel.vue";
import AdminPanel from "./components/AdminPanel.vue";

const user = ref(null),
  ready = ref(false),
  busy = ref(false),
  error = ref(""),
  page = ref("workbench");
const login = ref({ username: "", password: "" }),
  products = ref([]),
  selected = ref(null),
  query = ref(""),
  filter = ref(""),
  overview = ref({});
const productPanel = ref(null);
async function refresh() {
  await load();
  await productPanel.value?.refresh();
}
const menu = [
  { id: "workbench", name: "商品工作台", icon: Box },
  { id: "imports", name: "批量导入", icon: Upload },
  { id: "tasks", name: "任务与结果", icon: List },
  { id: "stores", name: "店铺配置", icon: Shop },
  { id: "users", name: "成员与审计", icon: DocumentChecked },
];
const filtered = computed(() =>
  products.value.filter(
    (p) =>
      (!query.value ||
        `${p.spu_code} ${p.title}`
          .toLowerCase()
          .includes(query.value.toLowerCase())) &&
      (!filter.value || p.status === filter.value),
  ),
);
const approved = computed(
  () => products.value.filter((p) => p.status === "APPROVED").length,
);
async function load(preferred) {
  try {
    const [items, counts] = await Promise.all([
      api("/api/products"),
      api("/api/overview"),
    ]);
    products.value = items;
    overview.value = counts;
    if (preferred) selected.value = preferred;
    else if (!selected.value && items.length) selected.value = items[0].id;
    else if (selected.value && !items.some((p) => p.id === selected.value))
      selected.value = items[0]?.id || null;
  } catch (e) {
    error.value = e.message;
  }
}
async function signIn() {
  busy.value = true;
  error.value = "";
  try {
    await refreshCsrf();
    user.value = await api("/api/auth/login", {
      method: "POST",
      body: login.value,
    });
    login.value.password = "";
    await load();
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function signOut() {
  try {
    await api("/api/auth/logout", { method: "POST" });
    user.value = null;
    products.value = [];
    selected.value = null;
    await refreshCsrf();
  } catch (e) {
    error.value = e.message;
  }
}
function expired() {
  user.value = null;
  error.value = "登录已失效，请重新登录。尚未保存的表单会保留在当前页面。";
}
async function imported(id) {
  selected.value = id || null;
  await load(id);
  page.value = "workbench";
}
onMounted(async () => {
  window.addEventListener("session-expired", expired);
  try {
    await refreshCsrf();
    user.value = await api("/api/auth/me");
    await load();
  } catch (e) {
    if (e.status !== 401) error.value = e.message;
  } finally {
    ready.value = true;
  }
});
onUnmounted(() => window.removeEventListener("session-expired", expired));
</script>

<template>
  <div v-if="!ready" class="boot" role="status">正在连接商品工作台…</div>
  <main v-else-if="!user" class="login-layout">
    <section class="login-story">
      <div class="brand">
        <el-icon><Box /></el-icon><strong>Flow Console</strong>
      </div>
      <span class="eyebrow">商品上架工作台</span>
      <h1>从商品资料，<br />到有据可查的上架。</h1>
      <p>
        整理素材，协作审核，跟踪每一次平台操作。<br />让每一步都清楚，让每个结果都真实。
      </p>
      <div class="login-stages">
        <span>01 资料与素材</span><span>02 人工审核</span
        ><span>03 草稿与核验</span>
      </div>
    </section>
    <section class="login-card">
      <span class="eyebrow">欢迎回来</span>
      <h2>登录工作台</h2>
      <p class="muted">使用管理员为你开通的团队账号</p>
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        :closable="false"
        role="alert"
      />
      <form @submit.prevent="signIn">
        <label for="username">用户名</label
        ><el-input
          id="username"
          v-model="login.username"
          autocomplete="username"
          size="large"
          required
        /><label for="password">密码</label
        ><el-input
          id="password"
          v-model="login.password"
          type="password"
          autocomplete="current-password"
          size="large"
          show-password
          required
        /><el-button
          native-type="submit"
          type="primary"
          size="large"
          :loading="busy"
          class="full"
          >登录 <el-icon><ArrowRight /></el-icon
        ></el-button>
      </form>
      <p class="login-help">
        首次使用？请由部署管理员设置初始账号，再创建运营与审核成员。
      </p>
    </section>
  </main>
  <div v-else class="shell">
    <aside class="sidebar">
      <a class="brand" href="#" @click.prevent="page = 'workbench'"
        ><el-icon><Box /></el-icon>
        <div><strong>Flow Console</strong><small>商品上架工作台</small></div></a
      ><span class="nav-label">工作空间</span>
      <nav aria-label="主导航">
        <button
          v-for="item in menu.filter(
            (m) => m.id !== 'users' || user.role === 'ADMIN',
          )"
          :key="item.id"
          :class="{ active: page === item.id }"
          :aria-current="page === item.id ? 'page' : undefined"
          @click="page = item.id"
        >
          <el-icon><component :is="item.icon" /></el-icon>{{ item.name
          }}<span v-if="item.id === 'workbench'" class="nav-count">{{
            products.length
          }}</span>
        </button>
      </nav>
      <div class="sidebar-bottom">
        <span class="session-dot"></span>
        <div>
          <strong>{{ user.username }}</strong
          ><small>{{
            { ADMIN: "管理员", OPERATOR: "运营成员", REVIEWER: "审核成员" }[
              user.role
            ]
          }}</small>
        </div>
        <el-button text aria-label="退出登录" @click="signOut"
          ><el-icon><SwitchButton /></el-icon
        ></el-button>
      </div>
    </aside>
    <div class="main-shell">
      <header class="topbar">
        <div>
          <span class="muted">工作空间</span><el-icon><ArrowRight /></el-icon
          ><strong>{{ menu.find((m) => m.id === page)?.name }}</strong>
        </div>
        <div class="topbar-actions">
          <span class="environment"><span></span>团队工作台</span
          ><el-button :icon="Refresh" @click="refresh">刷新</el-button>
        </div>
      </header>
      <main class="content">
        <el-alert
          v-if="error"
          :title="error"
          type="error"
          show-icon
          @close="error = ''"
        />
        <template v-if="page === 'workbench'"
          ><div class="page-heading">
            <div>
              <span class="eyebrow">商品运营 / 工作台</span>
              <h1>每件商品，稳步向前。</h1>
              <p>从资料整理到平台核验，在一个工作区完成。</p>
            </div>
            <el-button
              v-if="user.role !== 'REVIEWER'"
              type="primary"
              :icon="Upload"
              @click="page = 'imports'"
              >导入商品</el-button
            >
          </div>
          <div class="metrics">
            <article>
              <span>全部商品</span
              ><strong>{{ products.length }}<small>款 SPU</small></strong>
              <p>包含导入与手动创建</p>
            </article>
            <article>
              <span>等待审核</span
              ><strong
                >{{ products.length - approved }}<small>款</small></strong
              >
              <p>补齐资料后交由审核成员确认</p>
            </article>
            <article>
              <span>审核通过</span
              ><strong class="green">{{ approved }}<small>款</small></strong>
              <p>批准与当前内容版本绑定</p>
            </article>
            <article>
              <span>已确认发布</span
              ><strong
                >{{
                  overview.task_counts
                    ?.filter(
                      (t) =>
                        t.status === "SUCCEEDED" &&
                        t.target_action === "PUBLISH",
                    )
                    .reduce((a, t) => a + Number(t.count), 0) || 0
                }}<small>个任务</small></strong
              >
              <p>仅计平台权威核验结果</p>
            </article>
          </div>
          <div class="workbench">
            <section class="product-list panel">
              <div class="panel-heading">
                <h2>
                  商品列表 <span>{{ filtered.length }}</span>
                </h2>
                <el-button
                  v-if="user.role !== 'REVIEWER'"
                  text
                  @click="selected = null"
                  >新建</el-button
                >
              </div>
              <div class="list-filters">
                <el-input
                  v-model="query"
                  :prefix-icon="Search"
                  placeholder="搜索名称或货号"
                  aria-label="搜索商品"
                  clearable
                /><el-select
                  v-model="filter"
                  placeholder="全部审核状态"
                  aria-label="筛选审核状态"
                  clearable
                  ><el-option label="待审核" value="NEEDS_REVIEW" /><el-option
                    label="已通过"
                    value="APPROVED" /><el-option
                    label="已拒绝"
                    value="REJECTED"
                /></el-select>
              </div>
              <div class="product-rows">
                <button
                  v-for="p in filtered"
                  :key="p.id"
                  class="product-row"
                  :class="{ selected: selected === p.id }"
                  :aria-pressed="selected === p.id"
                  @click="selected = p.id"
                >
                  <span class="product-code">{{ p.spu_code }}</span
                  ><strong>{{ p.title }}</strong
                  ><span class="product-row-bottom"
                    ><span>{{ p.sku_count }} 个 SKU · {{ p.currency }}</span
                    ><span class="status" :class="p.status">{{
                      label(p.status)
                    }}</span></span
                  ></button
                ><el-empty
                  v-if="!filtered.length"
                  description="还没有匹配的商品"
                  :image-size="65"
                />
              </div>
              <div class="list-footer">商品 → 素材 → 文案 → 审核 → 店铺</div>
            </section>
            <ProductPanel
              ref="productPanel"
              :id="selected"
              :user="user"
              @changed="load"
              @tasks="page = 'tasks'"
            />
          </div>
        </template>
        <ImportPanel
          v-else-if="page === 'imports'"
          :user="user"
          @imported="imported"
        />
        <TaskPanel v-else-if="page === 'tasks'" :user="user" />
        <AdminPanel v-else :page="page" :user="user" @changed="load()" />
        <footer class="page-footer">
          <span>Flow Console</span
          ><span>导入包、线上草稿与正式发布，分别记录与核验。</span>
        </footer>
      </main>
    </div>
  </div>
</template>
