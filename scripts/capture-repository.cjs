/** Capture the actual Vue UI with isolated, explicitly synthetic browser fixtures. */
const { chromium } = require('../web/node_modules/playwright');
const fs = require('node:fs/promises');
const path = require('node:path');

const baseURL = process.argv[2] || 'http://127.0.0.1:3100';
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'docs/images');
const user = { id: 9001, username: '演示工作区', role: 'ADMIN' };
const products = [
  { id: 1, spu_code: 'DEMO-N001', title: '示例 · 极简链条项链', category: '演示饰品 / 项链', material: 'Stainless steel', color: 'Silver / Gold', dimensions: '45 cm + 5 cm', weight_g: '12.50', price: '29.90', cost: '8.20', currency: 'USD', stock: 120, image_rights: 'UNKNOWN', content_version: 3, sku_count: 2, status: 'NEEDS_REVIEW' },
  { id: 2, spu_code: 'DEMO-E002', title: '示例 · 几何耳饰套装', category: '演示饰品 / 耳饰', material: 'Stainless steel', color: 'Silver', dimensions: '2.5 cm', weight_g: '8.00', price: '19.90', cost: '6.50', currency: 'USD', stock: 80, image_rights: 'UNKNOWN', content_version: 2, sku_count: 1, status: 'APPROVED' },
  { id: 3, spu_code: 'DEMO-B003', title: '示例 · 简约链条手链', category: '演示饰品 / 手链', material: 'Stainless steel', color: 'Gold', dimensions: '18 cm', weight_g: '9.00', price: '24.90', cost: '7.30', currency: 'USD', stock: 60, image_rights: 'UNKNOWN', content_version: 1, sku_count: 1, status: 'REJECTED' },
];
const stores = [
  { id: 1, name: 'TEMU 演示店铺', platform: 'TEMU', mode: 'SEMI', currency: 'USD', active: true, external_shop_id: '', account_key: 'demo-account', config_version: 1 },
  { id: 2, name: 'AliExpress 演示店铺', platform: 'ALIEXPRESS', mode: 'ALIEXPRESS', currency: 'USD', active: true, external_shop_id: '', account_key: 'demo-account', config_version: 1 },
];
const imports = [
  { id: 3, filename: '饰品资料_第三批.xlsx', status: 'PARTIAL', total_rows: 12, valid_rows: 10, issue_rows: 2, error_count: 2, created_at: '2026-10-24 10:45', product_ids: [1, 2, 3], issues: [{ sheet: '商品SKU', row_number: 8, identifier: 'DEMO-B003', field: 'quantity', message: '请补充SKU的真实数量' }, { sheet: '商品SKU', row_number: 11, identifier: 'DEMO-N004', field: 'price', message: '售价需为有效的非负金额' }] },
  { id: 2, filename: '秋季商品_成品素材.zip', status: 'COMPLETED', total_rows: 8, valid_rows: 8, issue_rows: 0, error_count: 0, created_at: '2026-10-24 10:12', product_ids: [1, 2], issues: [] },
  { id: 1, filename: '基础商品资料.xlsx', status: 'COMPLETED', total_rows: 6, valid_rows: 6, issue_rows: 0, error_count: 0, created_at: '2026-10-24 09:30', product_ids: [1], issues: [] },
];
const tasks = [
  { id: 104, spu_code: 'DEMO-N001', title: '示例 · 极简链条项链', store_name: 'TEMU 演示店铺', platform: 'TEMU', target_action: 'CREATE_DRAFT', status: 'PENDING', external_id: null, external_status: null, stage: 'CREATE', attempt: 0, last_error: null },
  { id: 103, spu_code: 'DEMO-E002', title: '示例 · 几何耳饰套装', store_name: 'TEMU 演示店铺', platform: 'TEMU', target_action: 'PUBLISH', status: 'VERIFYING', external_id: 'DEMO-EXTERNAL-103', external_status: 'UNKNOWN', stage: 'VERIFY', attempt: 1, last_error: '演示状态：等待权威结果核验' },
  { id: 102, spu_code: 'DEMO-E002', title: '示例 · 几何耳饰套装', store_name: 'AliExpress 演示店铺', platform: 'ALIEXPRESS', target_action: 'CREATE_DRAFT', status: 'DRAFT_CREATED', external_id: 'DEMO-EXTERNAL-102', external_status: 'DRAFT_CREATED', stage: 'CREATE', attempt: 0, last_error: null },
  { id: 101, spu_code: 'DEMO-B003', title: '示例 · 简约链条手链', store_name: 'TEMU 演示店铺', platform: 'TEMU', target_action: 'CREATE_DRAFT', status: 'NEEDS_REVIEW', external_id: null, external_status: null, stage: 'CREATE', attempt: 0, last_error: '演示状态：商品规格更新，请重新审核' },
];

function detail(product) {
  return {
    ...product, platform_payload: {}, assets: [], reviews: [], legacy_results: [],
    review: { status: product.status, content_version: product.content_version },
    skus: Array.from({ length: product.sku_count }, (_, index) => ({ id: product.id * 10 + index, sku_code: `${product.spu_code}-${index ? 'GL' : 'SL'}`, name: index ? 'Gold' : 'Silver', color: index ? 'Gold' : 'Silver', size: product.dimensions, quantity: 1, price: product.price, stock: index ? 48 : 72, components: [] })),
    listing_copies: [{ id: product.id, platform: 'TEMU', title: 'Demo item · sample copy for interface preview', description: 'Synthetic product facts for interface presentation. No real platform request is performed.', bullet_points_json: '["Synthetic demonstration data","Review required before any platform action"]' }],
  };
}

async function main() {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ ...(process.platform === 'win32' ? { channel: 'msedge' } : {}), headless: true });
  try {
    const page = await browser.newPage({ baseURL, viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url());
      if (route.request().method() !== 'GET') throw new Error('Screenshot capture never writes to an API');
      const staticRoutes = {
        '/api/auth/csrf': { token: 'synthetic-preview-only' }, '/api/auth/me': user,
        '/api/products': products, '/api/stores': stores,
        '/api/overview': { products: products.length, skus: 4, stores: 2, task_counts: [] },
        '/api/compliance-library': [], '/api/imports': imports, '/api/publish-tasks': tasks,
        '/api/local-packages': [], '/api/automation/schedules': [],
      };
      const workflow = url.pathname.match(/^\/api\/products\/(\d+)\/workflow$/);
      const product = workflow && products.find(p => p.id === Number(workflow[1]));
      const body = product ? { product: detail(product), review: { status: product.status }, blockers: ['演示商品尚未上传完整成品图，请补齐后审核。'] } : staticRoutes[url.pathname];
      if (body === undefined) throw new Error(`Missing isolated fixture: ${url.pathname}`);
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });
    await page.goto(baseURL);
    await page.getByRole('heading', { name: '每件商品，稳步向前。' }).waitFor();
    await page.locator('.detail-fields:not([disabled])').waitFor();
    await page.locator('.el-loading-mask').waitFor({ state: 'hidden' });
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: path.join(output, 'showcase-workbench.png') });
    for (const [label, filename] of [['批量导入', 'showcase-import.png'], ['任务与结果', 'showcase-tasks.png']]) {
      await page.getByRole('button', { name: label, exact: true }).click();
      await page.waitForTimeout(250);
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: path.join(output, filename) });
    }
    await page.getByRole('button', { name: '商品工作台', exact: true }).click();
    await page.setViewportSize({ width: 375, height: 900 });
    await page.locator('.detail-fields:not([disabled])').waitFor();
    await page.locator('.el-loading-mask').waitFor({ state: 'hidden' });
    await page.evaluate(() => window.scrollTo(0, 0));
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('Mobile screenshot overflows');
    await page.screenshot({ path: path.join(output, 'showcase-mobile.png') });
    if (errors.length) throw new Error(errors.join('\n'));
    const cover = await browser.newPage({ viewport: { width: 1280, height: 440 }, deviceScaleFactor: 2 });
    await cover.setContent(`<style>html,body{margin:0}svg{display:block}</style>${await fs.readFile(path.join(output, 'repository-cover.svg'), 'utf8')}`);
    await cover.evaluate(() => document.fonts.ready);
    await cover.screenshot({ path: path.join(output, 'repository-cover.png'), omitBackground: true });
    console.log('Captured four actual Vue screens with synthetic fixtures and rendered the SVG cover. No backend or platform calls.');
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
