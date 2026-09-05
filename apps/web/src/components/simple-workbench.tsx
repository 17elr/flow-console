"use client";
/* eslint-disable @next/next/no-img-element */

import { ChangeEvent, useCallback, useEffect, useState } from "react";
import {
  CalendarClock,
  Check,
  Download,
  Eye,
  FileText,
  ImagePlus,
  Layers3,
  LoaderCircle,
  Plus,
  RefreshCw,
  ShieldCheck,
  Store,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { API_URL, ProductSummary, api } from "@/lib/api";
import { FinishedUpload } from "@/components/finished-upload";

type SkuForm = {
  sku_code: string;
  color: string;
  size: string;
  quantity: number;
  price?: number;
  stock: number;
};
type SourceSlot = {
  slot: string;
  label: string;
  target: string;
  required: boolean;
  status: "UPLOADED" | "MISSING" | "OPTIONAL";
  asset: { id: number; width: number; height: number } | null;
};
type Output = {
  job_id: number;
  role: string;
  sku_id: number | null;
  status: string;
  error: string | null;
  qc: Record<string, unknown> | null;
  asset: { id: number; width: number; height: number; sha256: string } | null;
  review: {
    decision: "APPROVED" | "REJECTED";
    note: string | null;
    reviewer: string;
    updated_at: string;
  } | null;
};
type Shop = { store_id: number; name: string; platform: string; mode: string };
type Draft = {
  id: number;
  store_id: number;
  channel: string;
  status: string;
  error_message: string | null;
  package_available: boolean;
};
type DraftResult = {
  store_id: number;
  status: string;
  draft_id?: number;
  error?: string | null;
  package_available?: boolean;
  verification_required?: boolean;
};
type ListingCopy = {
  id: number;
  platform: string;
  title: string;
  bullet_points: string[];
  description: string;
  sku_names: Record<string, string>;
  status: string;
  issues: Array<{ field: string; message: string }>;
  title_length: number;
  rules: { title_max: number };
};
type Workflow = {
  image_source: "FINISHED_UPLOAD" | "GENERATED";
  packaging_selection: { id: number; slot: number; filename: string; width: number; height: number } | null;
  publish_blockers: string[];
  product: {
    id: number;
    spu_code: string;
    title: string;
    category: string;
    price: number;
    stock: number;
    dimensions: string;
    skus: Array<SkuForm & { id: number }>;
  };
  slots: SourceSlot[];
  status: string;
  missing_count: number;
  outputs: Output[];
  output_count: number;
  expected_output_count: number;
  stores: Shop[];
  drafts: Draft[];
  listing_copies: ListingCopy[];
  review: {
    status: "IN_REVIEW" | "READY_TO_APPROVE" | "APPROVED" | "REJECTED";
    approved: boolean;
    can_approve: boolean;
    approved_images: number;
    rejected_images: number;
    expected_images: number;
    copies_reviewed: number;
    expected_copies: number;
    product_note: string | null;
  };
};

const newSku = (): SkuForm => ({
  sku_code: "",
  color: "",
  size: "",
  quantity: 1,
  stock: 0,
});
const names: Record<string, string> = {
  SPU_WHITE_MAIN: "白底主图",
  SPU_DETAIL_1: "细节图 1",
  SPU_DETAIL_2: "细节图 2",
  SPU_SIZE_INFO: "尺寸信息图",
  SCENE_MODEL_WEAR: "模特佩戴图",
  SCENE_LIFESTYLE: "生活场景图",
  SKU_WHITE: "SKU 白底图",
};
const statuses: Record<string, string> = {
  WAITING_SOURCE: "请先补齐素材",
  READY_TO_GENERATE: "素材已齐，可以生成",
  GENERATING: "正在生成图片",
  NEEDS_ATTENTION: "有图片需要处理",
  READY_TO_PUBLISH: "图片已齐，可以创建草稿",
};

export function SimpleWorkbench() {
  const [products, setProducts] = useState<ProductSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedProductIds, setSelectedProductIds] = useState<number[]>([]);
  const [flow, setFlow] = useState<Workflow | null>(null);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [preview, setPreview] = useState("");
  const [shops, setShops] = useState<number[]>([]);
  const [draftPlatform, setDraftPlatform] = useState<"TEMU" | "ALIEXPRESS">("TEMU");
  const [autoPublish, setAutoPublish] = useState(false);
  const [copyPlatform, setCopyPlatform] = useState("TEMU");
  const [form, setForm] = useState({
    spu_code: "",
    title: "",
    category: "",
    price: 0,
    stock: 0,
    dimensions: "",
    skus: [newSku()],
  });

  const loadProducts = useCallback(async () => {
    const data = await api<ProductSummary[]>("/api/products?limit=100");
    setProducts(data);
    const requested = Number(new URLSearchParams(window.location.search).get("product"));
    setSelectedId((value) => (requested && data.some((item) => item.id === requested) ? requested : value ?? data[0]?.id ?? null));
  }, []);
  const loadFlow = useCallback(
    async (id: number) =>
      setFlow(await api<Workflow>(`/api/products/${id}/workflow`)),
    [],
  );
  useEffect(() => {
    const timer = window.setTimeout(
      () => loadProducts().catch((e) => setNotice(e.message)),
      0,
    );
    return () => window.clearTimeout(timer);
  }, [loadProducts]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (selectedId) loadFlow(selectedId).catch((e) => setNotice(e.message));
      else setFlow(null);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [selectedId, loadFlow]);
  useEffect(() => {
    if (!selectedId || flow?.status !== "GENERATING") return;
    const timer = window.setInterval(
      () => loadFlow(selectedId).catch(() => undefined),
      1800,
    );
    return () => clearInterval(timer);
  }, [selectedId, flow?.status, loadFlow]);

  const missing =
    flow?.slots.filter((slot) => slot.required && slot.status === "MISSING") ??
    [];
  const activeCopy = flow?.listing_copies.find(
    (item) => item.platform === copyPlatform,
  );
  const selectedCopiesReady = shops.every((storeId) => {
    const store = flow?.stores.find((item) => item.store_id === storeId);
    const platform =
      store?.platform.toUpperCase() === "ALIEXPRESS"
        ? "ALIEXPRESS"
        : store?.platform.toUpperCase();
    return (
      flow?.listing_copies.some(
        (item) => item.platform === platform && item.status === "REVIEWED",
      ) ?? false
    );
  });
  const draftShops = flow?.stores.filter((store) => {
    const platform = store.platform.toUpperCase() === "ALIEXPRESS" ? "ALIEXPRESS" : "TEMU";
    return platform === draftPlatform;
  }) ?? [];
  function chooseDraftPlatform(platform: "TEMU" | "ALIEXPRESS") {
    setDraftPlatform(platform);
    setShops([]);
    setAutoPublish(false);
  }
  const tell = (error: unknown) =>
    setNotice(error instanceof Error ? error.message : "操作失败");
  async function deleteSelectedProduct() {
    if (!selectedId || !flow) return;
    const productName = `${flow.product.spu_code} · ${flow.product.title}`;
    if (!window.confirm(`确定删除商品“${productName}”吗？\n\n本地资料、SKU、图片任务和审核记录会被删除。已创建的妙手草稿不会被远程删除。`)) return;
    setBusy("delete");
    try {
      const result = await api<{ external_drafts_preserved: number }>(`/api/products/${selectedId}`, { method: "DELETE" });
      setProducts((items) => {
        const next = items.filter((item) => item.id !== selectedId);
        setSelectedId(next[0]?.id ?? null);
        return next;
      });
      setFlow(null);
      setNotice(result.external_drafts_preserved > 0 ? `商品已删除；${result.external_drafts_preserved} 个外部草稿未远程删除` : "商品已删除");
    } catch (e) { tell(e); } finally { setBusy(""); }
  }
  async function deleteMarkedProducts() {
    if (!selectedProductIds.length) return;
    if (!window.confirm(`确定删除选中的 ${selectedProductIds.length} 款商品吗？\n\n只删除 Flow Console 本地资料，不会远程删除妙手草稿。`)) return;
    setBusy("bulk-delete");
    try {
      const result = await api<{ product_ids: number[] }>("/api/products/bulk-delete", { method: "POST", body: JSON.stringify({ product_ids: selectedProductIds }) });
      setSelectedProductIds([]);
      await loadProducts();
      setNotice(`已删除 ${result.product_ids.length} 款本地商品`);
    } catch (e) { tell(e); } finally { setBusy(""); }
  }

  async function saveProduct() {
    if (
      !form.spu_code ||
      !form.title ||
      !form.category ||
      !form.dimensions ||
      form.skus.some((sku) => !sku.sku_code || !sku.color)
    )
      return setNotice(
        "请填写商品编号、标题、类目、尺寸以及每个 SKU 的编号和颜色",
      );
    setBusy("save");
    try {
      const data = await api<Workflow>("/api/simple-products", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setFlow(data);
      setSelectedId(data.product.id);
      await loadProducts();
      setNotice("商品资料已保存，请继续上传图片");
    } catch (e) {
      tell(e);
    } finally {
      setBusy("");
    }
  }
  async function upload(
    slot: SourceSlot,
    event: ChangeEvent<HTMLInputElement>,
  ) {
    const file = event.target.files?.[0];
    if (!file || !flow) return;
    const body = new FormData();
    body.append("product_id", String(flow.product.id));
    body.append("file", file);
    setBusy(slot.slot);
    try {
      setFlow(
        await api<Workflow>(`/api/source-assets/${slot.slot}`, {
          method: "PUT",
          body,
        }),
      );
      setNotice(`${slot.label}已上传`);
    } catch (e) {
      tell(e);
    } finally {
      setBusy("");
      event.target.value = "";
    }
  }
  async function removeSource(id: number) {
    if (!flow || !confirm("删除这张素材图片？")) return;
    try {
      await api(`/api/source-assets/${id}`, { method: "DELETE" });
      await loadFlow(flow.product.id);
    } catch (e) {
      tell(e);
    }
  }
  async function generate(force = false) {
    if (!flow) return;
    setBusy("generate");
    try {
      setFlow(
        await api<Workflow>(`/api/products/${flow.product.id}/generate-all`, {
          method: "POST",
          body: JSON.stringify({ force }),
        }),
      );
      setNotice("图片生成已开始");
    } catch (e) {
      tell(e);
    } finally {
      setBusy("");
    }
  }
  async function retry(output: Output) {
    if (!flow) return;
    setBusy(`retry-${output.job_id}`);
    try {
      await api(
        output.role.startsWith("SCENE_")
          ? `/api/scene-jobs/${output.job_id}/retry`
          : `/api/image-jobs/${output.job_id}/retry`,
        { method: "POST" },
      );
      await loadFlow(flow.product.id);
    } catch (e) {
      tell(e);
    } finally {
      setBusy("");
    }
  }
  async function replaceOutput(
    output: Output,
    event: ChangeEvent<HTMLInputElement>,
  ) {
    const file = event.target.files?.[0];
    if (!file || !output.asset) return;
    const body = new FormData();
    body.append("file", file);
    try {
      setFlow(
        await api<Workflow>(`/api/generated-assets/${output.asset.id}`, {
          method: "PUT",
          body,
        }),
      );
    } catch (e) {
      tell(e);
    } finally {
      event.target.value = "";
    }
  }
  async function removeOutput(output: Output) {
    if (!flow || !output.asset || !confirm("删除这张生成图片？")) return;
    try {
      await api(`/api/generated-assets/${output.asset.id}`, {
        method: "DELETE",
      });
      await loadFlow(flow.product.id);
    } catch (e) {
      tell(e);
    }
  }
  async function createDrafts() {
    if (!flow || !shops.length) return setNotice("请至少选择一个店铺");
    if (flow.publish_blockers.length) return setNotice(flow.publish_blockers.join("；"));
    if (!flow.review.approved) return setNotice("请先完成整款人工审核");
    setBusy("draft");
    try {
      const response = await api<{ results: DraftResult[] }>(
        `/api/products/${flow.product.id}/miaoshou-drafts`, {
        method: "POST",
        body: JSON.stringify({ store_ids: shops, confirmed_review: true, auto_publish: autoPublish }),
      });
      await loadFlow(flow.product.id);
      const failures = response.results.filter((item) => item.status === "FAILED");
      const pending = response.results.filter((item) => item.status === "PUBLISHING");
      if (failures.length) {
        const messages = failures.map((item) => {
          const shop = flow.stores.find((candidate) => candidate.store_id === item.store_id);
          return `${shop?.name ?? `店铺 ${item.store_id}`}：${item.error || "创建草稿失败"}`;
        });
        setNotice(messages.join("；"));
      } else if (pending.length) {
        setNotice(`${pending.length} 个妙手草稿已存在；之前曾进入发布处理中，当前不影响手动发布`);
      } else {
        const created = response.results.filter((item) => item.status === "DRAFT_CREATED").length;
        const published = response.results.filter((item) => item.status === "PUBLISHED").length;
        const packages = response.results.filter((item) => item.status === "PACKAGE_READY").length;
        setNotice(
          [created ? `${created} 个妙手草稿已创建` : "", published ? `${published} 个商品已在妙手发布` : "", packages ? `${packages} 个导入包已生成` : ""]
            .filter(Boolean)
            .join("，"),
        );
      }
    } catch (e) {
      tell(e);
    } finally {
      setBusy("");
    }
  }
  async function createAliExpressPackage() {
    if (!flow || !shops.length) return setNotice("请至少选择一个速卖通店铺");
    if (flow.publish_blockers.length) return setNotice(flow.publish_blockers.join("；"));
    if (!flow.review.approved) return setNotice("请先完成整款人工审核");
    setBusy("aliexpress-package");
    try {
      const response = await api<{ results: DraftResult[] }>(
        `/api/products/${flow.product.id}/aliexpress-import-package`,
        {
          method: "POST",
          body: JSON.stringify({ store_ids: shops, confirmed_review: true }),
        },
      );
      await loadFlow(flow.product.id);
      const failures = response.results.filter((item) => item.status === "FAILED");
      const ready = response.results.filter((item) => item.status === "PACKAGE_READY");
      if (failures.length) {
        const messages = failures.map((item) => {
          const shop = flow.stores.find((candidate) => candidate.store_id === item.store_id);
          return `${shop?.name ?? `店铺 ${item.store_id}`}：${item.error || "生成导入包失败"}`;
        });
        setNotice(messages.join("；"));
      } else if (ready.length) {
        setNotice(`${ready.length} 个速卖通导入包已生成，请在结果区域下载`);
      }
    } catch (e) {
      tell(e);
    } finally {
      setBusy("");
    }
  }
  async function reviewImage(
    output: Output,
    decision: "APPROVED" | "REJECTED",
  ) {
    if (!flow || !output.asset) return;
    const note =
      decision === "REJECTED" ? window.prompt("请填写驳回原因") : null;
    if (decision === "REJECTED" && !note) return;
    setBusy(`review-${output.asset.id}`);
    try {
      setFlow(
        await api<Workflow>(`/api/reviews/images/${output.asset.id}`, {
          method: "PUT",
          body: JSON.stringify({ decision, note }),
        }),
      );
      setNotice(decision === "APPROVED" ? "图片已通过" : "图片已驳回");
    } catch (error) {
      tell(error);
    } finally {
      setBusy("");
    }
  }
  async function reviewProduct(decision: "APPROVED" | "REJECTED") {
    if (!flow) return;
    const note =
      decision === "REJECTED" ? window.prompt("请填写整款驳回原因") : null;
    if (decision === "REJECTED" && !note) return;
    setBusy("product-review");
    try {
      setFlow(
        await api<Workflow>(`/api/products/${flow.product.id}/review`, {
          method: "PUT",
          body: JSON.stringify({ decision, note }),
        }),
      );
      setNotice(decision === "APPROVED" ? "整款商品已批准" : "整款商品已驳回");
    } catch (error) {
      tell(error);
    } finally {
      setBusy("");
    }
  }
  async function approveAll() {
    if (!flow) return;
    if (!window.confirm("确定将当前商品的全部图片和平台文案一次性审核通过吗？请确认你已完成实际核对。")) return;
    setBusy("approve-all");
    try {
      let latest = flow;
      for (const output of flow.outputs) {
        if (output.asset && output.review?.decision !== "APPROVED") {
          latest = await api<Workflow>(`/api/reviews/images/${output.asset.id}`, {
            method: "PUT",
            body: JSON.stringify({ decision: "APPROVED", note: null }),
          });
        }
      }
      for (const copy of latest.listing_copies) {
        if (copy.status !== "REVIEWED") {
          latest = await api<Workflow>(`/api/listing-copies/${copy.id}`, {
            method: "PUT",
            body: JSON.stringify({ title: copy.title, bullet_points: copy.bullet_points, description: copy.description, sku_names: copy.sku_names, confirmed_review: true }),
          });
        }
      }
      latest = await api<Workflow>(`/api/products/${latest.product.id}/review`, {
        method: "PUT",
        body: JSON.stringify({ decision: "APPROVED", note: null }),
      });
      setFlow(latest);
      setNotice("当前商品全部图片、SKU 图和平台文案已审核通过");
    } catch (e) { tell(e); } finally { setBusy(""); }
  }
  async function generateCopies() {
    if (!flow) return;
    setBusy("copy-generate");
    try {
      setFlow(
        await api<Workflow>(`/api/products/${flow.product.id}/listing-copies`, {
          method: "POST",
        }),
      );
      setNotice("两套英文文案已生成，请检查并确认");
    } catch (e) {
      tell(e);
    } finally {
      setBusy("");
    }
  }
  function editCopy(
    platform: string,
    field: keyof ListingCopy,
    value: unknown,
  ) {
    setFlow((current) =>
      current
        ? {
            ...current,
            listing_copies: current.listing_copies.map((item) =>
              item.platform === platform ? { ...item, [field]: value } : item,
            ),
          }
        : current,
    );
  }
  async function saveCopy(record: ListingCopy) {
    if (!flow) return;
    setBusy(`copy-${record.platform}`);
    try {
      setFlow(
        await api<Workflow>(`/api/listing-copies/${record.id}`, {
          method: "PUT",
          body: JSON.stringify({
            title: record.title,
            bullet_points: record.bullet_points,
            description: record.description,
            sku_names: record.sku_names,
            confirmed_review: true,
          }),
        }),
      );
      setNotice(
        `${record.platform === "TEMU" ? "TEMU" : "速卖通"}文案已保存并确认`,
      );
    } catch (e) {
      tell(e);
    } finally {
      setBusy("");
    }
  }
  function updateSku(
    index: number,
    field: keyof SkuForm,
    value: string | number,
  ) {
    const skus = [...form.skus];
    skus[index] = { ...skus[index], [field]: value };
    setForm({ ...form, skus });
  }

  return (
    <div className="simple-app">
      <header className="simple-header">
        <div className="simple-brand">
          <Layers3 size={20} />
          <div>
            <strong>Flow Console</strong>
            <span>商品上架工作台</span>
          </div>
        </div>
        <div className="simple-header-actions">
          <select
            value={selectedId ?? ""}
            onChange={(e) =>
              setSelectedId(e.target.value ? Number(e.target.value) : null)
            }
          >
            <option value="">+ 新建商品</option>
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.spu_code}
              </option>
            ))}
          </select>
          <details className="simple-bulk-delete">
            <summary>批量删除</summary>
            <div className="simple-bulk-menu">
              <label><input type="checkbox" checked={products.length > 0 && selectedProductIds.length === products.length} onChange={(event) => setSelectedProductIds(event.target.checked ? products.map((item) => item.id) : [])} />全部选择</label>
              {products.map((product) => <label key={product.id}><input type="checkbox" checked={selectedProductIds.includes(product.id)} onChange={(event) => setSelectedProductIds((items) => event.target.checked ? [...items, product.id] : items.filter((id) => id !== product.id))} />{product.spu_code}</label>)}
              <button type="button" className="danger-command" disabled={!selectedProductIds.length || busy === "bulk-delete"} onClick={() => void deleteMarkedProducts()}>{busy === "bulk-delete" ? "删除中…" : `删除已选 (${selectedProductIds.length})`}</button>
            </div>
          </details>
          {selectedId ? (
            <button className="simple-danger-icon" title="删除当前商品" aria-label="删除当前商品" disabled={busy === "delete"} onClick={deleteSelectedProduct}>
              {busy === "delete" ? <LoaderCircle size={16} className="spin" /> : <Trash2 size={16} />}
            </button>
          ) : null}
          <button
            title="刷新"
            onClick={() => selectedId && loadFlow(selectedId)}
          >
            <RefreshCw size={16} />
          </button>
          <a href="/automation"><CalendarClock size={15} /> 自动运行</a>
          <a href="/advanced">高级管理</a>
        </div>
      </header>
      <main className="simple-main">
        <div className="simple-title">
          <div>
            <h1>{flow?.product.title || "新建一款商品"}</h1>
            <p>按顺序完成资料、素材、图片和店铺草稿。</p>
          </div>
          {flow && (
            <span className={`simple-state ${flow.status.toLowerCase()}`}>
              {statuses[flow.status] ?? flow.status}
            </span>
          )}
        </div>
        <FinishedUpload onImported={() => loadProducts().catch(tell)} />
        <nav className="simple-steps six">
          {[
            "商品资料",
            "上传素材",
            "生成图片",
            "英文文案",
            "人工审核",
            "选择店铺",
          ].map((name, i) => (
            <div className={i === 0 || flow ? "active" : ""} key={name}>
              <span>{i + 1}</span>
              <strong>{name}</strong>
            </div>
          ))}
        </nav>
        <section className="simple-section">
          <Heading
            number="1"
            title="商品资料"
            text="只填写生成图片和创建草稿所需的信息"
          />
          {flow ? (
            <div className="product-summary">
              {[
                ["商品编号", flow.product.spu_code],
                ["类目", flow.product.category],
                ["售价", `$${flow.product.price}`],
                ["库存", flow.product.stock],
                ["尺寸", flow.product.dimensions],
                ["SKU", `${flow.product.skus.length} 个`],
              ].map(([label, value]) => (
                <div key={label}>
                  <small>{label}</small>
                  <strong>{value}</strong>
                </div>
              ))}
            </div>
          ) : (
            <div className="simple-form">
              <Field
                label="商品编号"
                value={form.spu_code}
                onChange={(v) => setForm({ ...form, spu_code: v })}
                placeholder="例如 NK-001"
              />
              <Field
                label="商品标题"
                value={form.title}
                onChange={(v) => setForm({ ...form, title: v })}
                placeholder="例如 925 银色珍珠项链"
                wide
              />
              <Field
                label="商品类目"
                value={form.category}
                onChange={(v) => setForm({ ...form, category: v })}
                placeholder="项链"
              />
              <Field
                label="售价"
                value={String(form.price)}
                onChange={(v) => setForm({ ...form, price: Number(v) })}
                type="number"
              />
              <Field
                label="库存"
                value={String(form.stock)}
                onChange={(v) => setForm({ ...form, stock: Number(v) })}
                type="number"
              />
              <Field
                label="真实尺寸"
                value={form.dimensions}
                onChange={(v) => setForm({ ...form, dimensions: v })}
                placeholder="链长 45cm，吊坠 12mm"
              />
              <div className="sku-editor wide">
                <div className="sku-editor-head">
                  <strong>SKU</strong>
                  <button
                    onClick={() =>
                      setForm({ ...form, skus: [...form.skus, newSku()] })
                    }
                  >
                    <Plus size={14} />
                    添加 SKU
                  </button>
                </div>
                {form.skus.map((sku, i) => (
                  <div className="sku-row" key={i}>
                    <input
                      value={sku.sku_code}
                      onChange={(e) => updateSku(i, "sku_code", e.target.value)}
                      placeholder="SKU 编号"
                    />
                    <input
                      value={sku.color}
                      onChange={(e) => updateSku(i, "color", e.target.value)}
                      placeholder="颜色"
                    />
                    <input
                      value={sku.size}
                      onChange={(e) => updateSku(i, "size", e.target.value)}
                      placeholder="尺寸"
                    />
                    <input
                      type="number"
                      value={sku.quantity}
                      onChange={(e) =>
                        updateSku(i, "quantity", Number(e.target.value))
                      }
                      title="数量"
                    />
                    <input
                      type="number"
                      value={sku.stock}
                      onChange={(e) =>
                        updateSku(i, "stock", Number(e.target.value))
                      }
                      title="库存"
                    />
                    <button
                      disabled={form.skus.length === 1}
                      onClick={() =>
                        setForm({
                          ...form,
                          skus: form.skus.filter((_, x) => x !== i),
                        })
                      }
                    >
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
              <button
                className="primary-command wide"
                onClick={saveProduct}
                disabled={busy === "save"}
              >
                {busy === "save" ? (
                  <LoaderCircle className="spin" size={16} />
                ) : (
                  <Check size={16} />
                )}
                保存并继续
              </button>
            </div>
          )}
        </section>
        {flow && (
          <>
            {flow.image_source !== "FINISHED_UPLOAD" && <section className="simple-section">
              <Heading
                number="2"
                title="上传素材"
                text={
                  missing.length
                    ? `还缺 ${missing.length} 张必需图片，直接上传到对应位置`
                    : "必需图片已齐，可以生成"
                }
              />
              <div className="slot-list">
                {flow.slots.map((slot) => (
                  <div className="source-slot" key={slot.slot}>
                    <div className="slot-preview">
                      {slot.asset ? (
                        <img
                          src={`${API_URL}/api/assets/${slot.asset.id}/content?kind=source`}
                          alt={slot.label}
                        />
                      ) : (
                        <ImagePlus size={22} />
                      )}
                    </div>
                    <div className="slot-copy">
                      <strong>{slot.label}</strong>
                      <span>绑定：{slot.target}</span>
                      {slot.status === "MISSING" && (
                        <em>缺少真实图片，不能用 AI 猜测</em>
                      )}
                      {slot.status === "OPTIONAL" && (
                        <em className="optional">可不上传，系统会从主图生成</em>
                      )}
                    </div>
                    <div className={`slot-status ${slot.status.toLowerCase()}`}>
                      {slot.status === "UPLOADED" ? (
                        <>
                          <Check size={15} />
                          已上传
                        </>
                      ) : slot.required ? (
                        "缺少"
                      ) : (
                        "可选"
                      )}
                    </div>
                    {slot.asset && (
                      <button
                        title="查看大图"
                        onClick={() =>
                          setPreview(
                            `${API_URL}/api/assets/${slot.asset!.id}/content?kind=source`,
                          )
                        }
                      >
                        <Eye size={16} />
                      </button>
                    )}
                    <label className="file-command">
                      {busy === slot.slot ? (
                        <LoaderCircle className="spin" size={15} />
                      ) : (
                        <Upload size={15} />
                      )}{" "}
                      {slot.asset ? "替换" : "上传"}
                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/webp"
                        onChange={(e) => upload(slot, e)}
                      />
                    </label>
                    {slot.asset && (
                      <button
                        className="danger"
                        title="删除"
                        onClick={() => removeSource(slot.asset!.id)}
                      >
                        <Trash2 size={15} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </section>}
            <section className="simple-section">
              <div className="heading-row">
                <Heading
                  number="3"
                  title={flow.image_source === "FINISHED_UPLOAD" ? "检查成品图片" : "生成并检查图片"}
                  text={flow.image_source === "FINISHED_UPLOAD" ? "图片已从本地文件夹导入，未调用 AI 生图" : "一次生成 6 张主图和每个 SKU 的独立白底图"}
                />
                {flow.image_source === "FINISHED_UPLOAD" && flow.packaging_selection ? <span className="simple-packaging-state">已选择包装图 {flow.packaging_selection.slot}</span> : null}
                <button className="primary-command" disabled={busy === "approve-all" || flow.review.status === "APPROVED"} onClick={approveAll}>
                  <ShieldCheck size={16} />
                  一键全部通过
                </button>
                {flow.image_source !== "FINISHED_UPLOAD" && <button
                  className="primary-command"
                  disabled={
                    missing.length > 0 ||
                    flow.status === "GENERATING" ||
                    busy === "generate"
                  }
                  onClick={() => generate(flow.outputs.length > 0)}
                >
                  {flow.status === "GENERATING" ? (
                    <LoaderCircle className="spin" size={16} />
                  ) : (
                    <ImagePlus size={16} />
                  )}{" "}
                  {flow.outputs.length ? "重新生成全部" : "生成全部图片"}
                </button>}
              </div>
              {missing.length > 0 && (
                <div className="attention-line">
                  请先补齐：{missing.map((s) => s.label).join("、")}
                </div>
              )}
              <div className="output-grid">
                {flow.outputs.map((output) => (
                  <article
                    className={`output-card ${output.error ? "failed" : ""}`}
                    key={output.job_id}
                  >
                    <div className="output-image">
                      {output.asset ? (
                        <img
                          src={`${API_URL}/api/assets/${output.asset.id}/content`}
                          alt={names[output.role]}
                        />
                      ) : output.status === "RUNNING" ? (
                        <LoaderCircle className="spin" size={24} />
                      ) : (
                        <ImagePlus size={24} />
                      )}
                    </div>
                    <div className="output-meta">
                      <strong>
                        {names[output.role]}
                        {output.role === "SKU_WHITE"
                          ? ` · ${flow.product.skus.find((s) => s.id === output.sku_id)?.sku_code || ""}`
                          : ""}
                      </strong>
                      <span>
                        {output.asset
                          ? "已生成，请人工检查"
                          : output.error || "等待生成"}
                      </span>
                    </div>
                    <div className="output-actions">
                      {output.asset && (
                        <button
                          title="查看"
                          onClick={() =>
                            setPreview(
                              `${API_URL}/api/assets/${output.asset!.id}/content`,
                            )
                          }
                        >
                          <Eye size={15} />
                        </button>
                      )}
                      {flow.image_source !== "FINISHED_UPLOAD" && <button
                        title="重新生成"
                        disabled={busy === `retry-${output.job_id}`}
                        onClick={() => retry(output)}
                      >
                        <RefreshCw size={15} />
                      </button>}
                      {output.asset && (
                        <label title="替换">
                          <Upload size={15} />
                          <input
                            type="file"
                            accept="image/*"
                            onChange={(e) => replaceOutput(output, e)}
                          />
                        </label>
                      )}
                      {output.asset && (
                        <button
                          title="删除"
                          onClick={() => removeOutput(output)}
                        >
                          <Trash2 size={15} />
                        </button>
                      )}
                    </div>
                    {output.asset ? (
                      <div
                        className={`image-review ${output.review?.decision.toLowerCase() ?? "pending"}`}
                      >
                        <div>
                          <strong>
                            {output.review?.decision === "APPROVED"
                              ? "审核通过"
                              : output.review?.decision === "REJECTED"
                                ? "已驳回"
                                : "等待审核"}
                          </strong>
                          <span>
                            {output.review?.note ||
                              (output.qc
                                ? "自动质检已记录，请核对商品和 SKU"
                                : "请核对商品结构、颜色和数量")}
                          </span>
                        </div>
                        <div>
                          <button
                            disabled={busy === `review-${output.asset.id}`}
                            onClick={() => reviewImage(output, "APPROVED")}
                          >
                            <Check size={14} />
                            通过
                          </button>
                          <button
                            disabled={busy === `review-${output.asset.id}`}
                            onClick={() => reviewImage(output, "REJECTED")}
                          >
                            <X size={14} />
                            驳回
                          </button>
                        </div>
                      </div>
                    ) : null}
                  </article>
                ))}
              </div>
              {!flow.outputs.length && (
                <div className="empty-output">
                  <ImagePlus size={26} />
                  <strong>还没有生成图片</strong>
                  <span>素材齐全后，点击“生成全部图片”</span>
                </div>
              )}
            </section>
            <CopySection
              flow={flow}
              activeCopy={activeCopy}
              platform={copyPlatform}
              busy={busy}
              onPlatformChange={setCopyPlatform}
              onGenerate={generateCopies}
              onEdit={editCopy}
              onSave={saveCopy}
            />
            <ReviewSection flow={flow} busy={busy} onDecision={reviewProduct} onApproveAll={approveAll} />
            <section className="simple-section">
              <Heading
                number="6"
                title={draftPlatform === "ALIEXPRESS" ? "选择速卖通店铺并生成导入包" : "选择店铺并创建草稿"}
                text={draftPlatform === "ALIEXPRESS" ? "生成 Excel 和图片 ZIP，导入妙手后手工核对并保存" : "选择平台后创建对应的妙手商品草稿"}
              />
              <div className="draft-platform-tabs" role="tablist" aria-label="草稿平台">
                <button type="button" className={draftPlatform === "TEMU" ? "active" : ""} onClick={() => chooseDraftPlatform("TEMU")}>TEMU 草稿</button>
                <button type="button" className={draftPlatform === "ALIEXPRESS" ? "active" : ""} onClick={() => chooseDraftPlatform("ALIEXPRESS")}>速卖通导入包</button>
              </div>
              <div className="store-list">
                {draftShops.map((shop) => (
                  <label
                    className={`store-choice ${shops.includes(shop.store_id) ? "selected" : ""}`}
                    key={shop.store_id}
                  >
                    <input
                      type="checkbox"
                      checked={shops.includes(shop.store_id)}
                      onChange={() =>
                        setShops((value) =>
                          value.includes(shop.store_id)
                            ? value.filter((id) => id !== shop.store_id)
                            : [...value, shop.store_id],
                        )
                      }
                    />
                    <Store size={18} />
                    <div>
                      <strong>{shop.name}</strong>
                      <span>
                        {shop.platform} · {shop.mode}
                      </span>
                    </div>
                  </label>
                ))}
              </div>
              {!draftShops.length && (
                <p className="draft-note">
                  暂无已同步的速卖通店铺，请先在高级管理中同步妙手店铺授权。
                </p>
              )}
              {draftPlatform === "ALIEXPRESS" ? (
                <button
                  className="primary-command draft-command"
                  disabled={
                    flow.status !== "READY_TO_PUBLISH" ||
                    !flow.review.approved ||
                    !shops.length ||
                    !selectedCopiesReady ||
                    busy === "aliexpress-package"
                  }
                  onClick={createAliExpressPackage}
                >
                  {busy === "aliexpress-package" ? <LoaderCircle className="spin" size={16} /> : <Download size={16} />}
                  {busy === "aliexpress-package" ? "正在生成导入包" : "生成导入包"}
                </button>
              ) : (
                <button
                  className="primary-command draft-command"
                  disabled={
                    flow.status !== "READY_TO_PUBLISH" ||
                    !flow.review.approved ||
                    !shops.length ||
                    !selectedCopiesReady ||
                    busy === "draft"
                  }
                  onClick={createDrafts}
                >
                  {busy === "draft" ? <LoaderCircle className="spin" size={16} /> : <Store size={16} />}
                  {busy === "draft" ? "妙手处理中" : "创建草稿"}
                </button>
              )}
              {draftPlatform === "TEMU" && <label className="draft-mode-toggle">
                <input
                  type="checkbox"
                  checked={autoPublish}
                  disabled={flow.stores.filter((s) => shops.includes(s.store_id)).some((s) => s.platform.toUpperCase() === "ALIEXPRESS")}
                  onChange={(event) => setAutoPublish(event.target.checked)}
                />
                <span>自动发布模式</span>
              </label>}
              {flow.status !== "READY_TO_PUBLISH" && (
                <p className="draft-note">
                  全部图片生成并人工查看后，才可以创建草稿。
                </p>
              )}
              <div className="draft-results">
                {flow.drafts.map((draft) => {
                  const shop = flow.stores.find(
                    (s) => s.store_id === draft.store_id,
                  );
                  return (
                    <div key={draft.id}>
                      <Check size={15} />
                      <span>
                        <strong>{shop?.name || draft.channel}</strong>
                        {draft.status === "DRAFT_CREATED"
                          ? "妙手草稿已创建"
                          : draft.status === "PACKAGE_READY"
                            ? "导入包已准备"
                            : draft.status === "PUBLISHED"
                              ? "妙手已发布"
                              : draft.status === "PUBLISHING"
                                ? "妙手草稿已存在"
                                : "处理失败"}
                      </span>
                      {draft.package_available && (
                        <a
                          href={`${API_URL}/api/miaoshou-drafts/${draft.id}/package`}
                        >
                          <Download size={14} />
                          下载导入包
                        </a>
                      )}
                      {draft.error_message && <em>{draft.error_message}</em>}
                    </div>
                  );
                })}
              </div>
            </section>
          </>
        )}
      </main>
      {notice && (
        <div className="simple-toast">
          <span>{notice}</span>
          <button onClick={() => setNotice("")}>
            <X size={15} />
          </button>
        </div>
      )}
      {preview && (
        <div className="preview-modal" onClick={() => setPreview("")}>
          <button>
            <X size={18} />
          </button>
          <img
            src={preview}
            alt="图片预览"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  );
}

function ReviewSection({
  flow,
  busy,
  onDecision,
  onApproveAll,
}: {
  flow: Workflow;
  busy: string;
  onDecision: (decision: "APPROVED" | "REJECTED") => void;
  onApproveAll: () => void;
}) {
  const review = flow.review;
  const statusLabel = {
    IN_REVIEW: "等待逐项审核",
    READY_TO_APPROVE: "可以批准整款",
    APPROVED: "整款审核已通过",
    REJECTED: "存在驳回项",
  }[review.status];
  return (
    <section className="simple-section review-section">
      <Heading
        number="5"
        title="人工审核"
        text="核对全部图片、SKU 映射和两套平台文案后批准整款"
      />
      <div className="review-summary">
        <div>
          <span>图片审核</span>
          <strong>
            {review.approved_images}/{review.expected_images}
          </strong>
          <small>
            {review.rejected_images
              ? `${review.rejected_images} 张已驳回`
              : "逐张通过后计入"}
          </small>
        </div>
        <div>
          <span>平台文案</span>
          <strong>
            {review.copies_reviewed}/{review.expected_copies}
          </strong>
          <small>TEMU 与速卖通分别确认</small>
        </div>
        <div className={`review-state ${review.status.toLowerCase()}`}>
          <span>整款状态</span>
          <strong>{statusLabel}</strong>
          <small>{review.product_note || "审核结果会持久保存"}</small>
        </div>
      </div>
      <div className="review-checklist">
        <span>
          <Check size={14} />
          六张 SPU 主图均为独立单图
        </span>
        <span>
          <Check size={14} />
          每个可售 SKU 都有专属白底图
        </span>
        <span>
          <Check size={14} />
          颜色、结构、数量和套装内容与实物一致
        </span>
        <span>
          <Check size={14} />
          英文文案没有虚构属性或禁用声明
        </span>
      </div>
      <div className="review-final-actions">
        <p>
          {review.can_approve
            ? "全部必需项已通过，可以批准整款商品。"
            : "请先处理未审核、驳回或缺失的项目。"}
        </p>
        <button
          className="primary-command"
          disabled={busy === "approve-all" || review.status === "APPROVED"}
          onClick={onApproveAll}
        >
          <ShieldCheck size={16} />
          一键全部通过
        </button>
        <button
          className="secondary-review-command"
          disabled={busy === "product-review"}
          onClick={() => onDecision("REJECTED")}
        >
          <X size={15} />
          驳回整款
        </button>
        <button
          className="primary-command"
          disabled={!review.can_approve || busy === "product-review"}
          onClick={() => onDecision("APPROVED")}
        >
          <ShieldCheck size={16} />
          批准整款商品
        </button>
      </div>
    </section>
  );
}

function CopySection({
  flow,
  activeCopy,
  platform,
  busy,
  onPlatformChange,
  onGenerate,
  onEdit,
  onSave,
}: {
  flow: Workflow;
  activeCopy?: ListingCopy;
  platform: string;
  busy: string;
  onPlatformChange: (platform: string) => void;
  onGenerate: () => void;
  onEdit: (platform: string, field: keyof ListingCopy, value: unknown) => void;
  onSave: (record: ListingCopy) => void;
}) {
  return (
    <section className="simple-section">
      <div className="heading-row">
        <Heading
          number="4"
          title="生成并确认英文文案"
          text="TEMU 与速卖通分别校验，内容只使用真实商品和 SKU 数据"
        />
        <button
          className="primary-command"
          disabled={busy === "copy-generate"}
          onClick={onGenerate}
        >
          {busy === "copy-generate" ? (
            <LoaderCircle className="spin" size={16} />
          ) : (
            <FileText size={16} />
          )}
          {flow.listing_copies.length ? "重新生成文案" : "生成英文文案"}
        </button>
      </div>
      {flow.listing_copies.length ? (
        <div className="copy-workspace">
          <div className="copy-tabs">
            {[
              ["TEMU", "TEMU"],
              ["ALIEXPRESS", "速卖通"],
            ].map(([value, label]) => {
              const record = flow.listing_copies.find(
                (item) => item.platform === value,
              );
              return (
                <button
                  key={value}
                  className={platform === value ? "active" : ""}
                  onClick={() => onPlatformChange(value)}
                >
                  {label}
                  <span className={record?.status === "REVIEWED" ? "done" : ""}>
                    {record?.status === "REVIEWED" ? "已确认" : "待确认"}
                  </span>
                </button>
              );
            })}
          </div>
          {activeCopy ? (
            <div className="copy-editor">
              <label>
                <span>
                  英文标题
                  <small>
                    {activeCopy.title.length}/{activeCopy.rules.title_max}
                  </small>
                </span>
                <input
                  value={activeCopy.title}
                  onChange={(event) =>
                    onEdit(activeCopy.platform, "title", event.target.value)
                  }
                />
              </label>
              <label>
                <span>英文卖点</span>
                <textarea
                  rows={5}
                  value={activeCopy.bullet_points.join("\n")}
                  onChange={(event) =>
                    onEdit(
                      activeCopy.platform,
                      "bullet_points",
                      event.target.value.split("\n"),
                    )
                  }
                />
                <small>每行一个卖点，最多 5 条</small>
              </label>
              <label>
                <span>英文描述</span>
                <textarea
                  rows={5}
                  value={activeCopy.description}
                  onChange={(event) =>
                    onEdit(
                      activeCopy.platform,
                      "description",
                      event.target.value,
                    )
                  }
                />
              </label>
              <div className="sku-copy-list">
                <strong>SKU 英文名称</strong>
                {flow.product.skus.map((sku) => (
                  <label key={sku.id}>
                    <span>{sku.sku_code}</span>
                    <input
                      value={activeCopy.sku_names[String(sku.id)] ?? ""}
                      onChange={(event) =>
                        onEdit(activeCopy.platform, "sku_names", {
                          ...activeCopy.sku_names,
                          [String(sku.id)]: event.target.value,
                        })
                      }
                    />
                  </label>
                ))}
              </div>
              {activeCopy.issues.length ? (
                <div className="copy-issues">
                  {activeCopy.issues.map((issue, index) => (
                    <span key={`${issue.field}-${index}`}>{issue.message}</span>
                  ))}
                </div>
              ) : null}
              <div className="copy-save-row">
                <span>
                  保存即表示已人工检查，没有虚构材质、品牌、认证或功效声明。
                </span>
                <button
                  className="primary-command"
                  disabled={busy === `copy-${activeCopy.platform}`}
                  onClick={() => onSave(activeCopy)}
                >
                  <Check size={16} />
                  保存并确认
                </button>
              </div>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="empty-copy">
          <FileText size={25} />
          <strong>还没有英文文案</strong>
          <span>点击“生成英文文案”，系统会分别生成两套平台内容。</span>
        </div>
      )}
    </section>
  );
}

function Heading({
  number,
  title,
  text,
}: {
  number: string;
  title: string;
  text: string;
}) {
  return (
    <div className="section-heading">
      <span>{number}</span>
      <div>
        <h2>{title}</h2>
        <p>{text}</p>
      </div>
    </div>
  );
}
function Field({
  label,
  value,
  onChange,
  placeholder = "",
  type = "text",
  wide = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
  wide?: boolean;
}) {
  return (
    <label className={wide ? "wide" : ""}>
      {label}
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </label>
  );
}
