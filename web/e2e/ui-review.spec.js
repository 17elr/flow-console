import { test, expect, request } from "@playwright/test";
import { randomUUID } from "node:crypto";

let products;
test.beforeAll(async () => {
  const api = await request.newContext({ baseURL: "http://127.0.0.1:8000" });
  await expect.poll(async () => {
    try { return (await api.get('/health')).ok(); }
    catch { return false; }
  }, {timeout: 30000}).toBeTruthy();
  const token = (await (await api.get("/api/auth/csrf")).json()).token;
  expect(
    (
      await api.post("/api/auth/login", {
        headers: { "X-CSRF-Token": token },
        data: { username: "admin", password: "integration-admin-pass" },
      })
    ).ok(),
  ).toBeTruthy();
  const suffix = randomUUID().slice(0, 8);
  products = [];
  for (const name of ["A", "B"]) {
    const result = await api.post("/api/products", {
      headers: { "X-CSRF-Token": token },
      data: {
        spu_code: `UI-${suffix}-${name}`,
        title: `UI review product ${name}`,
        currency: "USD",
        stock: 0,
      },
    });
    expect(result.ok()).toBeTruthy();
    products.push(await result.json());
  }
  await api.dispose();
});

async function login(page) {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("admin");
  await page.getByLabel("密码", { exact: true }).fill("integration-admin-pass");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "每件商品，稳步向前。" }),
  ).toBeVisible();
}
async function select(page, product) {
  await page.getByPlaceholder("搜索名称或货号").fill(product.spu_code);
  await page.locator(".product-row").first().click();
}

test("image and document upload failures remain visible", async ({ page }) => {
  await login(page);
  await select(page, products[0]);
  await expect(page.getByLabel("商品名称", { exact: true })).toHaveValue(
    products[0].title,
  );
  await page.route("**/api/source-assets", (route) =>
    route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({
        message: "图片无法解码，请重新选择",
        fieldErrors: { file: "无法解码" },
      }),
    }),
  );
  await page.getByRole("tab", { name: "图片与素材", exact: true }).click();
  await page
    .getByLabel("上传01 白底主图", { exact: true })
    .setInputFiles({
      name: "broken.png",
      mimeType: "image/png",
      buffer: Buffer.from("broken"),
    });
  await expect(
    page.getByRole("alert").filter({ hasText: "图片无法解码，请重新选择" }),
  ).toBeVisible();
  await page.waitForTimeout(400);
  await expect(
    page.getByRole("alert").filter({ hasText: "图片无法解码，请重新选择" }),
  ).toBeVisible();
  await page.route(`**/api/products/${products[0].id}/compliance`, (route) =>
    route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({ message: "文件内容无效，请重新上传" }),
    }),
  );
  await page.getByRole("tab", { name: "合规文件", exact: true }).click();
  await page
    .getByLabel("上传合规文件", { exact: true })
    .setInputFiles({
      name: "broken.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("broken"),
    });
  await expect(
    page.getByRole("alert").filter({ hasText: "文件内容无效，请重新上传" }),
  ).toBeVisible();
});

test("failed detail load never saves another products form as its draft", async ({
  page,
}) => {
  await login(page);
  await select(page, products[0]);
  await expect(page.getByLabel("商品名称", { exact: true })).toHaveValue(
    products[0].title,
  );
  await page
    .getByLabel("商品名称", { exact: true })
    .fill("Unsaved draft belonging to A");
  const endpoint = `**/api/products/${products[1].id}/workflow`;
  await page.route(endpoint, (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ message: "暂时无法读取商品B" }),
    }),
  );
  await select(page, products[1]);
  await expect(
    page.getByRole("alert").filter({ hasText: "暂时无法读取商品B" }),
  ).toBeVisible();
  await select(page, products[0]);
  await expect(page.getByLabel("商品名称", { exact: true })).toHaveValue(
    "Unsaved draft belonging to A",
  );
  await page.unroute(endpoint);
  await select(page, products[1]);
  await expect(page.getByLabel("商品名称", { exact: true })).toHaveValue(
    products[1].title,
  );
});

test("switching import mode clears incompatible selected file", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("button", { name: "批量导入", exact: true }).click();
  await page
    .getByLabel("选择导入文件", { exact: true })
    .setInputFiles("e2e/fixtures/partial-products.xlsx");
  await expect(page.locator(".upload-zone strong")).toHaveText(
    "partial-products.xlsx",
  );
  await page.getByText("ZIP 素材包", { exact: true }).click();
  await expect(page.locator(".upload-zone strong")).toHaveText(
    "选择 ZIP 商品素材包",
  );
});

test("navigation opens the next page at the top on mobile", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await login(page);
  await select(page, products[0]);
  await page.evaluate(() => window.scrollTo(0, 500));
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(0);
  await page.getByRole("button", { name: "批量导入", exact: true }).click();
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(0);
  await expect(
    page.getByRole("heading", { name: "批量导入，逐项有回音。" }),
  ).toBeInViewport();
});

test("logging back in from another section returns to the workbench", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("button", { name: "店铺配置", exact: true }).click();
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  await page.getByLabel("用户名", { exact: true }).fill("admin");
  await page.getByLabel("密码", { exact: true }).fill("integration-admin-pass");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "每件商品，稳步向前。" }),
  ).toBeVisible();
});
