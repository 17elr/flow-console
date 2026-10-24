let csrf = "";
export async function refreshCsrf() {
  const response = await fetch("/api/auth/csrf", {
    credentials: "same-origin",
  });
  if (!response.ok) throw new Error("无法连接工作台服务，请检查API是否启动");
  csrf = (await response.json()).token;
}
export async function api(path, { method = "GET", body, signal } = {}) {
  const headers = {};
  if (!["GET", "HEAD"].includes(method)) headers["X-CSRF-Token"] = csrf;
  if (body !== undefined && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }
  const response = await fetch(path, {
    method,
    headers,
    body,
    signal,
    credentials: "same-origin",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const error = Object.assign(
      new Error(payload.message || `请求失败 (${response.status})`),
      {
        fields: payload.fieldErrors || {},
        code: payload.code,
        status: response.status,
        requestId: payload.requestId,
      },
    );
    let expired = response.status === 401;
    if (
      response.status === 403 &&
      payload.code === "CSRF" &&
      path !== "/api/auth/login"
    ) {
      const session = await fetch("/api/auth/me", {
        credentials: "same-origin",
      }).catch(() => null);
      expired = session?.status === 401;
      if (session?.ok) await refreshCsrf();
    }
    if (expired && path !== "/api/auth/login")
      window.dispatchEvent(new Event("session-expired"));
    throw error;
  }
  return response.status === 204 ? null : response.json();
}
export const mainRoles = [
  "SPU_WHITE_MAIN",
  "SPU_DETAIL_1",
  "SPU_DETAIL_2",
  "SPU_SIZE_INFO",
  "SCENE_MODEL_WEAR",
  "SCENE_LIFESTYLE",
];
export const roleLabels = {
  SPU_WHITE_MAIN: "01 白底主图",
  SPU_DETAIL_1: "02 细节图一",
  SPU_DETAIL_2: "03 细节图二",
  SPU_SIZE_INFO: "04 尺寸信息",
  SCENE_MODEL_WEAR: "05 模特佩戴",
  SCENE_LIFESTYLE: "06 生活场景",
  SKU_IMAGE: "SKU 独立图",
  SOURCE_MAIN: "商品原图",
  PACKAGING: "包装图",
  label: "标签图",
  reach: "REACH 报告",
  other: "其他资质",
};
export const statusLabels = {
  APPROVED: "审核通过",
  REJECTED: "审核拒绝",
  NEEDS_REVIEW: "需要审核",
  LEGACY_AUTO_APPROVED: "历史自动确认 · 待重审",
  PENDING: "等待执行",
  RUNNING: "执行中",
  RETRY_WAIT: "等待重试",
  DRAFT_CREATED: "草稿已创建",
  VERIFYING: "待核验",
  SUCCEEDED: "发布已确认",
  FAILED: "失败",
  CANCELLED: "已取消",
  PACKAGE_READY: "本地包已生成",
  PARTIAL: "部分成功",
  COMPLETED: "已完成",
};
export const label = (value) => statusLabels[value] || value;
export const terminalStates = new Set([
  "DRAFT_CREATED",
  "SUCCEEDED",
  "FAILED",
  "NEEDS_REVIEW",
  "CANCELLED",
]);
