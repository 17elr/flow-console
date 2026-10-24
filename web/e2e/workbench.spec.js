import { test, expect, request } from "@playwright/test";
import { randomUUID } from "node:crypto";

const suffix = randomUUID().slice(0, 8);
const operatorName = `browser-op-${suffix}`,
  reviewerName = `browser-review-${suffix}`;
let productId,
  storeId,
  apiAdmin,
  token,
  operatorToken,
  apiOperator,
  apiReviewer,
  reviewerToken;
const pixel = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jD1sAAAAASUVORK5CYII=",
  "base64",
);
async function authenticate(context, username, password) {
  const csrf = await context.get("/api/auth/csrf");
  const token = (await csrf.json()).token;
  const result = await context.post("/api/auth/login", {
    headers: { "X-CSRF-Token": token },
    data: { username, password },
  });
  expect(result.ok()).toBeTruthy();
  return token;
}
async function login(
  page,
  username = "admin",
  password = "integration-admin-pass",
) {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill(username);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "每件商品，稳步向前。" }),
  ).toBeVisible();
}
test.beforeAll(async () => {
  apiAdmin = await request.newContext({ baseURL: "http://127.0.0.1:8000" });
  await expect
    .poll(
      async () => {
        try {
          return (await apiAdmin.get("/health")).ok();
        } catch {
          return false;
        }
      },
      { timeout: 30000 },
    )
    .toBeTruthy();
  token = await authenticate(apiAdmin, "admin", "integration-admin-pass");
  for (const [username, role] of [
    [operatorName, "OPERATOR"],
    [reviewerName, "REVIEWER"],
  ]) {
    const result = await apiAdmin.post("/api/users", {
      headers: { "X-CSRF-Token": token },
      data: { username, password: "browser-password-123", role },
    });
    expect(result.ok()).toBeTruthy();
  }
  const store = (await (await apiAdmin.get("/api/stores")).json()).find(
    (s) => s.name === "合成验收店铺",
  );
  expect(store).toBeTruthy();
  storeId = store.id;
  apiOperator = await request.newContext({ baseURL: "http://127.0.0.1:8000" });
  operatorToken = await authenticate(
    apiOperator,
    operatorName,
    "browser-password-123",
  );
  apiReviewer = await request.newContext({ baseURL: "http://127.0.0.1:8000" });
  reviewerToken = await authenticate(
    apiReviewer,
    reviewerName,
    "browser-password-123",
  );
  const code = `BROWSER-${suffix}`;
  const result = await apiOperator.post("/api/products", {
    headers: { "X-CSRF-Token": operatorToken },
    data: {
      spu_code: code,
      title: "合成演示商品 · 不代表真实店铺发布",
      material: "Stainless steel",
      dimensions: "45 cm",
      weight_g: "12.5",
      price: "12.12345678",
      currency: "USD",
      image_rights: "OWNED",
      skus: [
        {
          sku_code: `${code}-S`,
          color: "Silver",
          size: "45 cm",
          price: "12.12345678",
          stock: 8,
          quantity: 1,
        },
      ],
    },
  });
  expect(result.ok()).toBeTruthy();
  const product = await result.json();
  productId = product.id;
  const roles = [
    "SPU_WHITE_MAIN",
    "SPU_DETAIL_1",
    "SPU_DETAIL_2",
    "SPU_SIZE_INFO",
    "SCENE_MODEL_WEAR",
    "SCENE_LIFESTYLE",
    "SKU_IMAGE",
  ];
  for (const role of roles) {
    const response = await apiOperator.post("/api/source-assets", {
      headers: { "X-CSRF-Token": operatorToken },
      multipart: {
        product_id: String(productId),
        role,
        source: "FINISHED",
        ...(role === "SKU_IMAGE" ? { sku_id: String(product.skus[0].id) } : {}),
        file: { name: "fixture.png", mimeType: "image/png", buffer: pixel },
      },
    });
    expect(response.ok(), await response.text()).toBeTruthy();
  }
  const copy = await apiOperator.post(
    `/api/products/${productId}/listing-copies`,
    {
      headers: { "X-CSRF-Token": operatorToken },
      data: {
        platform: "TEMU",
        title: "Synthetic test necklace",
        description: "Synthetic fixture, no external store calls.",
      },
    },
  );
  expect(copy.ok()).toBeTruthy();
});
test.afterAll(async () => {
  await Promise.all([
    apiAdmin?.dispose(),
    apiOperator?.dispose(),
    apiReviewer?.dispose(),
  ]);
});

test("login, precise amounts, validation failure and form retention", async ({
  page,
}) => {
  await login(page, operatorName, "browser-password-123");
  await page.getByPlaceholder("搜索名称或货号").fill(`BROWSER-${suffix}`);
  await page
    .getByRole("button", { name: new RegExp(`BROWSER-${suffix}`) })
    .click();
  await expect(page.getByLabel("销售价格", { exact: true })).toHaveValue(
    "12.12345678",
  );
  await page.getByLabel("销售价格", { exact: true }).fill("-1");
  await page.getByRole("button", { name: "保存商品资料" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "金额需非负数" }),
  ).toBeVisible();
  await expect(page.getByLabel("销售价格", { exact: true })).toHaveValue("-1");
  await page.getByLabel("销售价格", { exact: true }).fill("12.12345678");
  await page.getByRole("button", { name: "保存商品资料" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "金额需非负数" }),
  ).toHaveCount(0);
  await page.getByRole("tab", { name: "人工审核" }).click();
  await expect(
    page.getByRole("button", { name: "批准当前版本" }),
  ).toBeDisabled();
});

test("reviewer can approve and replacement image invalidates approval", async ({
  page,
}) => {
  await login(page, reviewerName, "browser-password-123");
  await page.getByPlaceholder("搜索名称或货号").fill(`BROWSER-${suffix}`);
  await page
    .getByRole("button", { name: new RegExp(`BROWSER-${suffix}`) })
    .click();
  await page.getByRole("tab", { name: "人工审核" }).click();
  await page.getByRole("button", { name: "批准当前版本" }).click();
  await page.getByRole("button", { name: "确认批准", exact: true }).click();
  await expect(page.locator(".detail-title .status")).toHaveText("审核通过");
  await page.getByRole("button", { name: "退出登录" }).click();
  await login(page, operatorName, "browser-password-123");
  await page.getByPlaceholder("搜索名称或货号").fill(`BROWSER-${suffix}`);
  await page
    .getByRole("button", { name: new RegExp(`BROWSER-${suffix}`) })
    .click();
  await page.getByRole("tab", { name: "图片与素材" }).click();
  await page
    .getByLabel("上传01 白底主图", { exact: true })
    .setInputFiles({
      name: "replacement.png",
      mimeType: "image/png",
      buffer: pixel,
    });
  await expect(page.locator(".detail-title .status")).toHaveText("需要审核");
  await expect(
    page.getByRole("img", { name: "01 白底主图", exact: true }),
  ).toBeVisible();
});

test("explicit rejection, missing configuration and task polling cleanup", async ({
  page,
}) => {
  const current = await (
    await apiOperator.get(`/api/products/${productId}`)
  ).json();
  await apiReviewer.put(`/api/products/${productId}/review`, {
    headers: { "X-CSRF-Token": reviewerToken },
    data: {
      content_version: current.content_version,
      decision: "REJECTED",
      note: "合成验收：请核对尺寸",
    },
  });
  await login(page, operatorName, "browser-password-123");
  await page.getByPlaceholder("搜索名称或货号").fill(`BROWSER-${suffix}`);
  await page
    .getByRole("button", { name: new RegExp(`BROWSER-${suffix}`) })
    .click();
  await page.getByRole("tab", { name: "人工审核" }).click();
  await expect(page.locator(".detail-title .status")).toHaveText("审核拒绝");
  await expect(page.getByText("合成验收：请核对尺寸")).toBeVisible();
  await apiReviewer.put(`/api/products/${productId}/review`, {
    headers: { "X-CSRF-Token": reviewerToken },
    data: {
      content_version: current.content_version,
      decision: "APPROVED",
      note: "合成验收通过",
    },
  });
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await page
    .getByRole("button", { name: new RegExp(`BROWSER-${suffix}`) })
    .click();
  await page.getByRole("tab", { name: "店铺与上架" }).click();
  await page.getByText("合成验收店铺", { exact: true }).click();
  await page.getByRole("button", { name: /创建后台任务/ }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "外部平台操作默认关闭" }),
  ).toBeVisible();
  await expect(
    page.getByRole("checkbox", { name: /^合成验收店铺 TEMU/ }),
  ).toBeChecked();
  let requests = 0;
  page.on("request", (r) => {
    if (r.url().endsWith("/api/publish-tasks")) requests++;
  });
  await page.getByRole("button", { name: "任务与结果", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "后台任务", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "商品工作台", exact: false }).click();
  const before = requests;
  await page.waitForTimeout(4500);
  expect(requests).toBe(before);
});

test("responsive workbench and screenshot evidence", async ({ page }) => {
  await login(page);
  await page.getByPlaceholder("搜索名称或货号").fill(`BROWSER-${suffix}`);
  await page
    .getByRole("button", { name: new RegExp(`BROWSER-${suffix}`) })
    .click();
  for (const width of [375, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      )
      .toBeTruthy();
  }
  await page.screenshot({
    path: "test-results/workbench-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 375, height: 900 });
  await page.screenshot({
    path: "test-results/workbench-mobile.png",
    fullPage: true,
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(
    page.getByRole("tab", { name: "商品资料", exact: true }),
  ).toBeVisible();
});

test("partial workbook import reports row errors and opens the valid product", async ({
  page,
}) => {
  await login(page, operatorName, "browser-password-123");
  await page.getByRole("button", { name: "批量导入", exact: true }).click();
  await page
    .getByLabel("选择导入文件", { exact: true })
    .setInputFiles("e2e/fixtures/partial-products.xlsx");
  await page.getByRole("button", { name: "校验并导入", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "本次导入：部分成功" }),
  ).toBeVisible();
  await expect(
    page.getByText("SKU数量缺失，不自动填充", { exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "查看已导入商品" }).click();
  await expect(page.getByLabel("商品货号 / SPU", { exact: true })).toHaveValue(
    "E2E-IMPORT-VALID",
  );
});

test("reviewer retry requires a reason and shows durable task progress", async ({
  page,
}) => {
  await login(page, reviewerName, "browser-password-123");
  await page.getByRole("button", { name: "任务与结果", exact: true }).click();
  const row = page
    .locator("tr")
    .filter({ hasText: "合成失败重试验收商品" })
    .filter({ has: page.locator(".status.FAILED") })
    .first();
  await expect(row.getByText("失败", { exact: true })).toBeVisible();
  const identity = await row.locator("strong").first().innerText();
  await row.getByRole("button", { name: "重试", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "确认操作", exact: true }),
  ).toBeDisabled();
  await page
    .getByLabel("原因", { exact: true })
    .fill("合成浏览器验收：确认重试原因已记录");
  await page.getByRole("button", { name: "确认操作", exact: true }).click();
  await expect(page.locator("tr").filter({ hasText: identity }).getByText("等待重试", { exact: true })).toBeVisible();
});

test("expired login preserves unsaved product values for the same user", async ({
  page,
}) => {
  await login(page, operatorName, "browser-password-123");
  await page.getByPlaceholder("搜索名称或货号").fill(`BROWSER-${suffix}`);
  await page
    .getByRole("button", { name: new RegExp(`BROWSER-${suffix}`) })
    .click();
  await page.getByLabel("销售价格", { exact: true }).fill("13.12345678");
  const csrf = (await (await page.request.get("/api/auth/csrf")).json()).token;
  await page.request.post("/api/auth/logout", {
    headers: { "X-CSRF-Token": csrf },
  });
  await page.getByRole("button", { name: "保存商品资料" }).click();
  await expect(
    page.getByRole("heading", { name: "登录工作台", exact: true }),
  ).toBeVisible();
  await page.getByLabel("用户名", { exact: true }).fill(operatorName);
  await page.getByLabel("密码", { exact: true }).fill("browser-password-123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByLabel("销售价格", { exact: true })).toHaveValue(
    "13.12345678",
  );
});
