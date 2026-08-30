"use client";

import {
  AlertCircle,
  ArrowLeft,
  Bell,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Database,
  Download,
  ExternalLink,
  FileSpreadsheet,
  FolderOpen,
  Filter,
  FolderInput,
  Image as ImageIcon,
  Layers3,
  ListChecks,
  Loader2,
  PackageCheck,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  Store as StoreIcon,
  TriangleAlert,
  Upload,
  UserCircle,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";

import {
  API_URL,
  ImportBatch,
  Overview,
  ProductDetail,
  ProductSummary,
  SkuVariant,
  Store,
  api,
} from "@/lib/api";

const statusCopy = {
  WAITING_DATA: { label: "待补资料", tone: "warning" },
  WAITING_GENERATION: { label: "待生成", tone: "success" },
  READY: { label: "已就绪", tone: "info" },
} as const;

type DetailTab = "basics" | "sku" | "assets" | "stores";
type UtilityPanel = "stores" | "help" | "notifications" | null;

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function StatusBadge({ status }: { status: keyof typeof statusCopy }) {
  const item = statusCopy[status];
  return <span className={`status-badge ${item.tone}`}>{item.label}</span>;
}

function ProductThumb({ url, title }: { url: string | null; title: string }) {
  return (
    <div className="product-thumb">
      {url ? (
        // Source image URLs are user-controlled, so they cannot use a fixed next/image host allowlist.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt={title} referrerPolicy="no-referrer" />
      ) : (
        <ImageIcon aria-hidden="true" size={18} />
      )}
    </div>
  );
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="empty-state">
      <FolderInput size={22} aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}

export function ProductCenter() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [products, setProducts] = useState<ProductSummary[]>([]);
  const [stores, setStores] = useState<Store[]>([]);
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [detail, setDetail] = useState<ProductDetail | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<DetailTab>("basics");
  const [selectedSkuId, setSelectedSkuId] = useState<number | null>(null);
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");
  const [storeId, setStoreId] = useState("");
  const [activeStoreId, setActiveStoreId] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [importMode, setImportMode] = useState<"file" | "folder">("file");
  const [selectedFolderFiles, setSelectedFolderFiles] = useState<File[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [utilityPanel, setUtilityPanel] = useState<UtilityPanel>(null);
  const [editMode, setEditMode] = useState(false);
  const [productSaving, setProductSaving] = useState(false);
  const [skuEditMode, setSkuEditMode] = useState(false);
  const [skuSaving, setSkuSaving] = useState(false);
  const [componentSaving, setComponentSaving] = useState(false);
  const [deletingComponentId, setDeletingComponentId] = useState<number | null>(null);
  const [listingSaving, setListingSaving] = useState(false);
  const [productForm, setProductForm] = useState<Record<string, string>>(Object.create(null));
  const fileRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);

  const loadProducts = useCallback(async () => {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    if (status !== "ALL") params.set("status", status);
    if (storeId) params.set("store_id", storeId);
    const data = await api<ProductSummary[]>(`/api/products?${params.toString()}`);
    setApiOnline(true);
    setProducts(data);
    setSelectedId((current) => {
      if (current && data.some((item) => item.id === current)) return current;
      return data[0]?.id ?? null;
    });
  }, [query, status, storeId]);

  const loadShell = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const [overviewData, storeData, batchData] = await Promise.all([
        api<Overview>("/api/overview"),
        api<Store[]>("/api/stores"),
        api<ImportBatch[]>("/api/imports"),
      ]);
      setOverview(overviewData);
      setStores(storeData);
      setBatches(batchData);
      setSelectedBatchId((current) =>
        current && batchData.some((batch) => batch.id === current) ? current : batchData[0]?.id ?? null,
      );
      setApiOnline(true);
      await loadProducts();
    } catch (caught) {
      setApiOnline(false);
      setError(caught instanceof Error ? caught.message : "无法连接资料中心 API");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [loadProducts]);

  const loadDetail = useCallback(async (id: number) => {
    try {
      const data = await api<ProductDetail>(`/api/products/${id}`);
      setApiOnline(true);
      setDetail(data);
      setSelectedSkuId((current) =>
        current && data.skus.some((sku) => sku.id === current) ? current : data.skus[0]?.id ?? null,
      );
      setProductForm({
        title: data.title ?? "",
        category: data.category ?? "",
        material: data.material ?? "",
        color: data.color ?? "",
        dimensions: data.dimensions ?? "",
        weight_g: data.weight_g?.toString() ?? "",
        cost: data.cost?.toString() ?? "",
        price: data.price?.toString() ?? "",
        stock: data.stock.toString(),
        source_image_url: data.source_image_url ?? "",
        image_rights: data.image_rights ?? "UNKNOWN",
      });
    } catch (caught) {
      setApiOnline(false);
      setError(caught instanceof Error ? caught.message : "商品详情加载失败");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadShell(), 0);
    return () => window.clearTimeout(timer);
  }, [loadShell]);

  useEffect(() => {
    if (!selectedId) return;
    const timer = window.setTimeout(() => {
      setDetailLoading(true);
      void loadDetail(selectedId);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [selectedId, loadDetail]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadProducts().catch((caught) => {
        setApiOnline(false);
        setError(caught instanceof Error ? caught.message : "商品列表加载失败");
        setLoading(false);
      });
    }, 250);
    return () => clearTimeout(timer);
  }, [query, status, storeId, loadProducts]);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), 3200);
    return () => clearTimeout(timer);
  }, [notice]);

  const selectedSku = useMemo(
    () => detail?.skus.find((sku) => sku.id === selectedSkuId) ?? null,
    [detail, selectedSkuId],
  );
  const selectedBatch = useMemo(
    () => batches.find((batch) => batch.id === selectedBatchId) ?? batches[0] ?? null,
    [batches, selectedBatchId],
  );
  const activeStore = useMemo(
    () => stores.find((store) => String(store.id) === activeStoreId) ?? null,
    [activeStoreId, stores],
  );
  const issueCount = useMemo(
    () => batches.reduce((total, batch) => total + batch.issue_rows, 0),
    [batches],
  );

  async function handleImport(event: FormEvent) {
    event.preventDefault();
    if (importMode === "file" && !selectedFile) return;
    if (importMode === "folder" && !selectedFolderFiles.length) return;
    setImporting(true);
    setError(null);
    const body = new FormData();
    if (importMode === "file" && selectedFile) body.append("file", selectedFile);
    if (importMode === "folder") selectedFolderFiles.forEach((file) => { body.append("files", file); body.append("relative_paths", file.webkitRelativePath || file.name); });
    try {
      const endpoint = importMode === "file" ? "/api/imports/excel" : "/api/imports/package";
      const batch = await api<ImportBatch>(endpoint, { method: "POST", body });
      setNotice(`导入完成：${batch.total_rows} 行，发现 ${batch.issue_rows} 个问题`);
      setImportOpen(false);
      setSelectedFile(null);
      setSelectedFolderFiles([]);
      await loadShell();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "导入失败");
    } finally {
      setImporting(false);
    }
  }

  async function saveProduct(event: FormEvent) {
    event.preventDefault();
    if (!detail) return;
    const numeric = (value: string) => (value.trim() ? Number(value) : null);
    const payload = {
      ...productForm,
      weight_g: numeric(productForm.weight_g),
      cost: numeric(productForm.cost),
      price: numeric(productForm.price),
      stock: Number(productForm.stock || 0),
    };
    setProductSaving(true);
    setError(null);
    try {
      const updated = await api<ProductDetail>(`/api/products/${detail.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      setDetail(updated);
      setEditMode(false);
      setNotice("商品资料已保存并重新校验");
      await Promise.all([loadProducts(), api<Overview>("/api/overview").then(setOverview)]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存失败");
    } finally {
      setProductSaving(false);
    }
  }

  async function saveSku(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail || !selectedSku) return;
    const data = new FormData(event.currentTarget);
    const numeric = (value: FormDataEntryValue | null) => {
      const text = String(value ?? "").trim();
      return text ? Number(text) : null;
    };
    setSkuSaving(true);
    setError(null);
    try {
      await api<SkuVariant>(`/api/skus/${selectedSku.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: String(data.get("name") ?? "").trim() || null,
          color: String(data.get("color") ?? "").trim() || null,
          size: String(data.get("size") ?? "").trim() || null,
          material: String(data.get("material") ?? "").trim() || null,
          quantity: Number(data.get("quantity") || 1),
          price: numeric(data.get("price")),
          stock: Number(data.get("stock") || 0),
          source_image_url: String(data.get("source_image_url") ?? "").trim() || null,
          is_sellable: data.get("is_sellable") === "on",
        }),
      });
      await Promise.all([
        loadDetail(detail.id),
        loadProducts(),
        api<Overview>("/api/overview").then(setOverview),
      ]);
      setSkuEditMode(false);
      setNotice("SKU 资料已保存并重新校验");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "SKU 保存失败");
    } finally {
      setSkuSaving(false);
    }
  }

  async function addComponent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedSku) return;
    const data = new FormData(event.currentTarget);
    setError(null);
    setComponentSaving(true);
    try {
      await api(`/api/skus/${selectedSku.id}/components`, {
        method: "POST",
        body: JSON.stringify({
          component_code: data.get("component_code") || null,
          component_name: data.get("component_name"),
          color: data.get("color") || null,
          quantity: Number(data.get("quantity") || 1),
          source_image_url: data.get("source_image_url") || null,
        }),
      });
      event.currentTarget.reset();
      await loadDetail(detail!.id);
      setNotice("套装组件已添加");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "组件添加失败");
    } finally {
      setComponentSaving(false);
    }
  }

  async function deleteComponent(id: number) {
    if (!detail) return;
    if (!window.confirm("确认移除这个套装组件吗？")) return;
    setError(null);
    setDeletingComponentId(id);
    try {
      await api(`/api/components/${id}`, { method: "DELETE" });
      await loadDetail(detail.id);
      setNotice("组件已移除");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "组件移除失败");
    } finally {
      setDeletingComponentId(null);
    }
  }

  async function addListing(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail) return;
    const data = new FormData(event.currentTarget);
    setListingSaving(true);
    setError(null);
    try {
      await api(`/api/products/${detail.id}/listings`, {
        method: "POST",
        body: JSON.stringify({
          store_id: Number(data.get("store_id")),
          listing_title: String(data.get("listing_title") ?? "").trim() || null,
          price: data.get("price") ? Number(data.get("price")) : null,
        }),
      });
      await loadDetail(detail.id);
      await loadProducts();
      setNotice("店铺版本已创建");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "店铺版本创建失败");
    } finally {
      setListingSaving(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark"><Layers3 size={19} aria-hidden="true" /></div>
          <div><strong>Flow Console</strong><span>AI commerce automation</span></div>
        </div>
        <div className="topbar-actions">
          <Link className="simple-mode-link" href="/" title="返回简单模式">
            <ArrowLeft size={15} />
            <span>简单模式</span>
          </Link>
          <button className="store-switch" type="button" aria-expanded={utilityPanel === "stores"} onClick={() => setUtilityPanel((current) => current === "stores" ? null : "stores")}>
            <span>{activeStore?.name ?? "全部店铺"}</span><ChevronDown size={14} />
          </button>
          <button className="icon-button" type="button" title="运行诊断" aria-label="运行诊断" aria-expanded={utilityPanel === "help"} onClick={() => setUtilityPanel((current) => current === "help" ? null : "help")}><CircleHelp size={18} /></button>
          <button className="icon-button notification" type="button" title="导入问题" aria-label="导入问题" aria-expanded={utilityPanel === "notifications"} onClick={() => setUtilityPanel((current) => current === "notifications" ? null : "notifications")}><Bell size={18} />{issueCount > 0 && <span>{issueCount > 9 ? "9+" : issueCount}</span>}</button>
          <div className="user"><UserCircle size={28} /><div><strong>运营管理员</strong><span>资料审核</span></div></div>
        </div>
        {utilityPanel && <button className="utility-dismiss" type="button" aria-label="关闭浮层" onClick={() => setUtilityPanel(null)} />}
        {utilityPanel === "stores" && <div className="utility-panel store-panel" role="dialog" aria-label="店铺筛选"><div className="utility-panel-head"><strong>当前店铺</strong><button className="icon-button" type="button" aria-label="关闭" onClick={() => setUtilityPanel(null)}><X size={15} /></button></div><button className={`utility-option ${!activeStoreId ? "active" : ""}`} type="button" onClick={() => { setActiveStoreId(""); setStoreId(""); setUtilityPanel(null); }}>全部店铺<Check size={14} /></button>{stores.map((store) => <button className={`utility-option ${activeStoreId === String(store.id) ? "active" : ""}`} type="button" key={store.id} onClick={() => { setActiveStoreId(String(store.id)); setStoreId(String(store.id)); setUtilityPanel(null); }}><span>{store.platform} · {store.name}</span>{activeStoreId === String(store.id) && <Check size={14} />}</button>)}</div>}
        {utilityPanel === "help" && <div className="utility-panel help-panel" role="dialog" aria-label="运行诊断"><div className="utility-panel-head"><strong>运行诊断</strong><button className="icon-button" type="button" aria-label="关闭" onClick={() => setUtilityPanel(null)}><X size={15} /></button></div><div className="diagnostic-row"><span>资料中心 API</span><strong className={apiOnline ? "diagnostic-ok" : "diagnostic-error"}>{apiOnline === null ? "检测中" : apiOnline ? "已连接" : "离线"}</strong></div><div className="diagnostic-row"><span>图片 Provider</span><strong className="diagnostic-paused">已暂停</strong></div><div className="utility-links"><a href={`${API_URL}/docs`} target="_blank" rel="noreferrer">API 文档<ExternalLink size={13} /></a><a href={`${API_URL}/api/imports/template`} target="_blank" rel="noreferrer">下载导入模板<Download size={13} /></a></div></div>}
        {utilityPanel === "notifications" && <div className="utility-panel notification-panel" role="dialog" aria-label="导入问题"><div className="utility-panel-head"><strong>导入问题</strong><button className="icon-button" type="button" aria-label="关闭" onClick={() => setUtilityPanel(null)}><X size={15} /></button></div>{issueCount === 0 ? <div className="utility-empty"><CheckCircle2 size={16} />当前没有导入问题</div> : batches.slice(0, 5).flatMap((batch) => batch.issues.slice(0, 3).map((issue) => <button className="notification-row" type="button" key={issue.id} onClick={() => { setSelectedBatchId(batch.id); setUtilityPanel(null); }}><span className={issue.severity === "ERROR" ? "notification-error" : "notification-warning"}>{issue.severity}</span><strong>{issue.identifier ?? issue.sheet}</strong><small>{issue.message}</small></button>))}</div>}
      </header>

      <div className="app-body">
        <aside className="sidebar">
          <div className="sidebar-title">高级管理</div>
          <nav>
            <button className="nav-item active" type="button" onClick={() => setNotice("当前已在批量资料管理")}><Database size={18} /><span>批量资料管理</span></button>
          </nav>
        </aside>

        <main className="content">
          <section className="commandbar">
            <div>
              <h1>批量资料管理</h1>
              <p>批量导入、校验并维护商品、SKU 和店铺版本</p>
            </div>
            <div className="command-actions">
              <span className={`connection-pill ${apiOnline === false ? "offline" : apiOnline === true ? "online" : "checking"}`}><span />{apiOnline === false ? "API 离线" : apiOnline === true ? "API 已连接" : "检测中"}</span>
              <button className="secondary-button" type="button" onClick={() => void loadShell()} disabled={refreshing}>{refreshing ? <Loader2 className="spin" size={15} /> : <RefreshCw size={15} />}{refreshing ? "连接中" : "刷新"}</button>
              <button className="primary-button" type="button" onClick={() => setImportOpen(true)}><Upload size={16} />本地导入</button>
            </div>
          </section>

          {error && <div className="error-banner"><AlertCircle size={17} /><span>{error}</span>{apiOnline === false && <button className="text-button" type="button" onClick={() => void loadShell()}>{refreshing ? "连接中" : "重新连接"}</button>}<button type="button" onClick={() => setError(null)} aria-label="关闭"><X size={16} /></button></div>}

          <section className="metrics" aria-label="资料中心概览">
            <div><span>商品总数</span><strong>{overview?.products ?? "-"}</strong><small>{overview?.stores ?? 0} 个店铺</small></div>
            <div><span>SKU 数量</span><strong>{overview?.skus ?? "-"}</strong><small>独立 SKU 素材</small></div>
            <div className="metric-warning"><span>待补资料</span><strong>{overview?.waiting_data ?? "-"}</strong><small>{overview?.issues ?? 0} 个阻塞问题</small></div>
            <div className="metric-success"><span>待生成</span><strong>{overview?.waiting_generation ?? "-"}</strong><small>可进入模块二</small></div>
          </section>

          <section className="workspace">
            <div className="batch-pane">
              <div className="pane-heading"><div><FileSpreadsheet size={16} /><strong>导入批次</strong></div><span>{batches.length}</span></div>
              <div className="batch-list">
                {batches.length === 0 ? (
                  <EmptyState>还没有 Excel 导入批次</EmptyState>
                ) : batches.map((batch) => (
                  <button className={`batch-row ${selectedBatchId === batch.id ? "selected" : ""}`} type="button" key={batch.id} onClick={() => setSelectedBatchId(batch.id)}>
                    <strong>{batch.filename}</strong>
                    <span>{formatDate(batch.created_at)}</span>
                    <div><span>{batch.total_rows} 行</span><span>{batch.issue_rows} 问题</span></div>
                    <small className={batch.issue_rows ? "warning-text" : "success-text"}>{batch.issue_rows ? "需要处理" : "校验完成"}</small>
                  </button>
                ))}
              </div>
              <button className="download-template" type="button" onClick={() => window.open(`${API_URL}/api/imports/template`, "_blank")}><Download size={15} />下载标准模板</button>
            </div>

            <div className="product-pane">
              <div className="pane-heading product-pane-title"><div><PackageCheck size={16} /><strong>商品数据</strong><span>{products.length} 款</span></div></div>
              <div className="filters">
                <label className="search-field"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 SPU / 商品名称" /></label>
                <label className="select-field"><Filter size={15} /><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="ALL">全部状态</option><option value="WAITING_DATA">待补资料</option><option value="WAITING_GENERATION">待生成</option><option value="READY">已就绪</option></select></label>
                <label className="select-field store-filter"><StoreIcon size={15} /><select value={storeId} onChange={(event) => { setStoreId(event.target.value); setActiveStoreId(event.target.value); }}><option value="">全部店铺</option>{stores.map((store) => <option key={store.id} value={store.id}>{store.platform} · {store.name}</option>)}</select></label>
              </div>
              <div className="table-wrap">
                <table className="product-table">
                  <thead><tr><th>商品</th><th>SKU</th><th>素材</th><th>店铺</th><th>状态</th></tr></thead>
                  <tbody>
                    {products.map((product) => (
                      <tr key={product.id} className={selectedId === product.id ? "selected" : ""} tabIndex={0} onClick={() => { setDetailLoading(true); setSelectedId(product.id); }} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setDetailLoading(true); setSelectedId(product.id); } }}>
                        <td><div className="product-cell"><ProductThumb url={product.source_image_url} title={product.title} /><div><strong>{product.title}</strong><span>{product.spu_code}</span><small>{product.material || "材质待补"} · 库存 {product.stock}</small></div></div></td>
                        <td><strong>{product.ready_sku_count}/{product.sku_count}</strong><span className="cell-sub">可进入生成</span></td>
                        <td>{product.blocker_count ? <span className="issue-count error"><AlertCircle size={13} />{product.blocker_count}</span> : product.warning_count ? <span className="issue-count warning"><TriangleAlert size={13} />{product.warning_count}</span> : <span className="issue-count success"><Check size={13} />完整</span>}</td>
                        <td><strong>{product.listing_count}</strong><span className="cell-sub">发布版本</span></td>
                        <td><StatusBadge status={product.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!loading && products.length === 0 && <EmptyState>没有符合筛选条件的商品</EmptyState>}
                {loading && <div className="loading-state"><Loader2 className="spin" size={20} />正在加载商品资料</div>}
              </div>
            </div>

            <div className="detail-pane">
              <div className="pane-heading"><div><ListChecks size={16} /><strong>商品校验</strong></div>{detail && <button className="text-button" type="button" onClick={() => setEditMode((value) => !value)}>{editMode ? "取消" : "编辑"}</button>}</div>
              {detailLoading ? <div className="loading-state"><Loader2 className="spin" size={20} />加载详情</div> : detail ? (
                <>
                  <div className="detail-hero"><ProductThumb url={detail.source_image_url} title={detail.title} /><div><span className="mono">{detail.spu_code}</span><h2>{detail.title}</h2><p>{detail.category}</p></div><StatusBadge status={detail.status} /></div>
                  <div className="detail-score"><div><span>资料完整度</span><strong>{Math.max(0, 100 - detail.blocker_count * 22 - detail.warning_count * 8)}</strong><small>/100</small></div><div className="score-track"><span style={{ width: `${Math.max(4, 100 - detail.blocker_count * 22 - detail.warning_count * 8)}%` }} /></div><div className="score-legend"><span><i className="dot green" />{detail.ready_sku_count} 个 SKU 就绪</span><span><i className="dot amber" />{detail.warning_count} 警告</span><span><i className="dot red" />{detail.blocker_count} 阻塞</span></div></div>
                  <div className="tabs" role="tablist">
                    {([['basics','基础资料'],['sku','SKU 组合'],['assets','素材'],['stores','店铺版本']] as const).map(([key, label]) => <button key={key} className={activeTab === key ? "active" : ""} type="button" onClick={() => setActiveTab(key)}>{label}</button>)}
                  </div>
                  <div className="detail-content">
                    {activeTab === "basics" && <BasicsTab detail={detail} editing={editMode} saving={productSaving} form={productForm} setForm={setProductForm} onSave={saveProduct} />}
                    {activeTab === "sku" && <SkuTab detail={detail} selectedSku={selectedSku} editing={skuEditMode} saving={skuSaving} componentSaving={componentSaving} deletingComponentId={deletingComponentId} onEdit={() => setSkuEditMode((value) => !value)} onSave={saveSku} onSelectSku={(id) => { setSkuEditMode(false); setSelectedSkuId(id); }} onAdd={addComponent} onDelete={deleteComponent} />}
                    {activeTab === "assets" && <AssetsTab detail={detail} />}
                    {activeTab === "stores" && <StoresTab detail={detail} stores={stores} saving={listingSaving} onAdd={addListing} />}
                  </div>
                </>
              ) : <EmptyState>请选择一款商品查看校验结果</EmptyState>}
            </div>
          </section>

          <section className="activity-pane">
            <div className="pane-heading"><div><Settings2 size={16} /><strong>{selectedBatch?.filename ?? "最近校验活动"}</strong></div><span>{selectedBatch?.issues.length ?? 0} 条</span></div>
            <div className="activity-list">
              {(selectedBatch?.issues ?? []).slice(0, 4).map((issue) => <div key={issue.id}><span>{issue.severity === "ERROR" ? <AlertCircle size={14} /> : <TriangleAlert size={14} />}</span><strong>{issue.identifier ?? issue.sheet}</strong><p>{issue.message}</p><small>{issue.sheet} 第 {issue.row_number} 行</small></div>)}
              {!selectedBatch?.issues.length && <div className="activity-empty"><CheckCircle2 size={15} />当前批次没有导入问题记录</div>}
            </div>
          </section>
        </main>
      </div>

      {importOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setImportOpen(false)}><div className="modal import-modal" role="dialog" aria-modal="true" aria-labelledby="import-title"><div className="modal-head"><div><FileSpreadsheet size={18} /><h2 id="import-title">从本地导入商品资料</h2></div><button className="icon-button" type="button" onClick={() => setImportOpen(false)} aria-label="关闭"><X size={18} /></button></div><form onSubmit={handleImport}><div className="import-mode-switch"><button type="button" className={importMode === "file" ? "active" : ""} onClick={() => setImportMode("file")}><FileSpreadsheet size={15} />单个 Excel</button><button type="button" className={importMode === "folder" ? "active" : ""} onClick={() => setImportMode("folder")}><FolderOpen size={15} />商品文件夹</button></div>{importMode === "file" ? <button className={`file-drop ${selectedFile ? "has-file" : ""}`} type="button" onClick={() => fileRef.current?.click()}><input ref={fileRef} type="file" accept=".xlsx,.xlsm" onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)} /><Upload size={24} /><strong>{selectedFile?.name ?? "选择 Excel 文件"}</strong><span>支持标准模板和中英文字段别名，最大 15MB</span></button> : <button className={`file-drop ${selectedFolderFiles.length ? "has-file" : ""}`} type="button" onClick={() => folderRef.current?.click()}><input ref={(node) => { folderRef.current = node; if (node) { node.setAttribute("webkitdirectory", ""); node.setAttribute("directory", ""); } }} type="file" multiple accept=".xlsx,.xlsm,image/png,image/jpeg,image/webp" onChange={(event) => setSelectedFolderFiles(Array.from(event.target.files ?? []))} /><FolderOpen size={24} /><strong>{selectedFolderFiles.length ? `已选择 ${selectedFolderFiles.length} 个文件` : "选择本地商品文件夹"}</strong><span>{selectedFolderFiles.length ? `${selectedFolderFiles.filter((file) => /\.xls[xm]$/i.test(file.name)).length} 个 Excel · ${selectedFolderFiles.filter((file) => /\.(png|jpe?g|webp)$/i.test(file.name)).length} 张图片` : "Excel 可选；没有 Excel 时按编码给现有商品补充图片"}</span></button>}<div className="folder-naming"><strong>图片命名</strong><span><code>SPU编码.jpg</code> 主图　<code>SPU编码__detail1.jpg</code> 细节图　<code>SKU编码.jpg</code> SKU 图</span></div><div className="import-rules"><h3>导入后自动校验</h3><ul><li>有 Excel：创建或更新商品资料</li><li>无 Excel：只给现有商品补充素材</li><li>每个可售 SKU 的专属原图</li><li>未匹配图片进入问题列表</li></ul></div><div className="modal-actions"><button className="secondary-button" type="button" onClick={() => window.open(`${API_URL}/api/imports/template`, "_blank")}><Download size={15} />下载模板</button><button className="primary-button" type="submit" disabled={(importMode === "file" ? !selectedFile : !selectedFolderFiles.length) || importing}>{importing ? <Loader2 className="spin" size={16} /> : <Upload size={16} />}{importing ? "正在校验" : "开始导入"}</button></div></form></div></div>}
      {notice && <div className="toast"><CheckCircle2 size={17} />{notice}</div>}
    </div>
  );
}

function BasicsTab({ detail, editing, saving, form, setForm, onSave }: { detail: ProductDetail; editing: boolean; saving: boolean; form: Record<string,string>; setForm: React.Dispatch<React.SetStateAction<Record<string,string>>>; onSave: (event: FormEvent) => void }) {
  const fields = [
    ["title", "商品标题", true], ["category", "类目", true], ["material", "材质", true],
    ["color", "颜色", false], ["dimensions", "尺寸", false], ["weight_g", "重量(g)", false],
    ["cost", "成本", false], ["price", "售价", false], ["stock", "库存", false],
    ["source_image_url", "商品原图", true], ["image_rights", "图片授权", true],
  ] as const;
  if (editing) return <form className="edit-form" onSubmit={onSave}>{fields.map(([key,label]) => <label key={key}><span>{label}</span>{key === "image_rights" ? <select value={form[key] ?? "UNKNOWN"} onChange={(event) => setForm((old) => ({...old,[key]:event.target.value}))}><option value="UNKNOWN">未确认</option><option value="AUTHORIZED">已授权</option><option value="OWNED">自有实拍</option></select> : <input value={form[key] ?? ""} onChange={(event) => setForm((old) => ({...old,[key]:event.target.value}))} />}</label>)}<button className="primary-button full" type="submit" disabled={saving}>{saving ? <Loader2 className="spin" size={15} /> : <Check size={15} />}{saving ? "保存中" : "保存并重新校验"}</button></form>;
  return <div className="validation-list">{fields.map(([key,label,required]) => { const raw = key === "weight_g" ? detail.weight_g : key === "cost" ? detail.cost : detail[key as keyof ProductDetail]; const missing = raw === null || raw === "" || (key === "image_rights" && raw === "UNKNOWN"); return <div key={key}><span className={missing && required ? "validation-icon error" : missing ? "validation-icon warning" : "validation-icon success"}>{missing && required ? <X size={12} /> : missing ? <TriangleAlert size={12} /> : <Check size={12} />}</span><div><strong>{label}</strong><span>{missing ? "待补充" : String(raw)}</span></div>{required && <small>必填</small>}</div>;})}</div>;
}

function SkuTab({
  detail,
  selectedSku,
  editing,
  saving,
  componentSaving,
  deletingComponentId,
  onEdit,
  onSave,
  onSelectSku,
  onAdd,
  onDelete,
}: {
  detail: ProductDetail;
  selectedSku: SkuVariant | null;
  editing: boolean;
  saving: boolean;
  componentSaving: boolean;
  deletingComponentId: number | null;
  onEdit: () => void;
  onSave: (event: FormEvent<HTMLFormElement>) => void;
  onSelectSku: (id: number) => void;
  onAdd: (event: FormEvent<HTMLFormElement>) => void;
  onDelete: (id: number) => void;
}) {
  return (
    <div className="sku-section">
      <div className="sku-switcher">
        {detail.skus.map((sku) => <button key={sku.id} type="button" className={selectedSku?.id === sku.id ? "active" : ""} onClick={() => onSelectSku(sku.id)}><span>{sku.sku_code}</span><small>{sku.components.length ? `${sku.components.length} 个组件` : "单品 SKU"}</small><i className={sku.status === "WAITING_DATA" ? "red" : "green"} /></button>)}
      </div>
      {selectedSku && <>
        <div className="sku-section-heading"><div><strong>{selectedSku.name || selectedSku.sku_code}</strong><span>{selectedSku.is_sellable ? "可销售" : "已停用"}</span></div><button className="text-button" type="button" onClick={onEdit}>{editing ? "取消编辑" : "编辑 SKU"}</button></div>
        {editing ? (
          <form className="sku-edit-form" onSubmit={onSave}>
            <label><span>SKU 名称</span><input name="name" defaultValue={selectedSku.name ?? ""} /></label>
            <label><span>颜色</span><input name="color" defaultValue={selectedSku.color ?? ""} /></label>
            <label><span>尺寸</span><input name="size" defaultValue={selectedSku.size ?? ""} /></label>
            <label><span>材质</span><input name="material" defaultValue={selectedSku.material ?? ""} /></label>
            <label><span>数量</span><input name="quantity" type="number" min="1" defaultValue={selectedSku.quantity} /></label>
            <label><span>售价</span><input name="price" type="number" min="0" step="0.01" defaultValue={selectedSku.price ?? ""} /></label>
            <label><span>库存</span><input name="stock" type="number" min="0" defaultValue={selectedSku.stock} /></label>
            <label className="sku-image-field"><span>SKU 专属原图</span><input name="source_image_url" defaultValue={selectedSku.source_image_url ?? ""} /></label>
            <label className="checkbox-field"><input name="is_sellable" type="checkbox" defaultChecked={selectedSku.is_sellable} /><span>可销售 SKU</span></label>
            <button className="primary-button full" type="submit" disabled={saving}>{saving ? <Loader2 className="spin" size={15} /> : <Check size={15} />}{saving ? "保存中" : "保存并重新校验"}</button>
          </form>
        ) : (
          <div className="sku-facts"><div><span>颜色</span><strong>{selectedSku.color || "待补"}</strong></div><div><span>尺寸</span><strong>{selectedSku.size || "待补"}</strong></div><div><span>数量</span><strong>{selectedSku.quantity}</strong></div><div><span>SKU 原图</span><strong>{selectedSku.source_image_url ? "已关联" : "缺失"}</strong></div></div>
        )}
        <div className="component-heading"><strong>套装组件矩阵</strong><span>仅套装 SKU 需要</span></div>
        <div className="component-table">{selectedSku.components.map((component) => <div key={component.id}><span className="mono">{component.component_code || "未编码"}</span><strong>{component.component_name}</strong><span>{component.color || "-"}</span><span>× {component.quantity}</span><button className="icon-button danger" type="button" disabled={deletingComponentId === component.id} onClick={() => onDelete(component.id)} title="移除组件" aria-label="移除组件">{deletingComponentId === component.id ? <Loader2 className="spin" size={14} /> : <X size={14} />}</button></div>)}{selectedSku.components.length === 0 && <EmptyState>当前按单品 SKU 处理</EmptyState>}</div>
        <form className="component-form" onSubmit={onAdd}><input name="component_code" placeholder="组件编码" /><input name="component_name" required placeholder="组件名称*" /><input name="color" placeholder="颜色" /><input name="quantity" type="number" min="1" defaultValue="1" aria-label="数量" /><input name="source_image_url" placeholder="组件原图 URL" /><button className="secondary-button" type="submit" disabled={componentSaving}>{componentSaving ? <Loader2 className="spin" size={14} /> : <Plus size={14} />}{componentSaving ? "添加中" : "添加组件"}</button></form>
      </>}
    </div>
  );
}

function AssetsTab({ detail }: { detail: ProductDetail }) {
  return <div className="asset-list"><div className="asset-group"><div><strong>SPU 商品素材</strong><span>主图生成参考</span></div>{detail.assets.filter((asset) => asset.sku_id === null).map((asset) => <div className="asset-row" key={asset.id}><ProductThumb url={asset.url} title={detail.title} /><div><strong>{asset.asset_type}</strong><span>{asset.rights_status}</span></div><CheckCircle2 size={16} /></div>)}{detail.assets.filter((asset) => asset.sku_id === null).length === 0 && <EmptyState>缺少 SPU 商品原图</EmptyState>}</div><div className="asset-group"><div><strong>SKU 专属素材</strong><span>每个可售 SKU 必须独立关联</span></div>{detail.skus.map((sku) => <div className="asset-row" key={sku.id}><ProductThumb url={sku.source_image_url} title={sku.name || sku.sku_code} /><div><strong>{sku.sku_code}</strong><span>{sku.source_image_url ? "已关联专属原图" : "缺少专属原图"}</span></div>{sku.source_image_url ? <CheckCircle2 size={16} /> : <AlertCircle className="red-icon" size={16} />}</div>)}</div></div>;
}

function StoresTab({ detail, stores, saving, onAdd }: { detail: ProductDetail; stores: Store[]; saving: boolean; onAdd:(event:FormEvent<HTMLFormElement>)=>void }) {
  const available = stores.filter((store) => !detail.listings.some((listing) => listing.store_id === store.id));
  return <div className="store-list"><div className="store-table">{detail.listings.map((listing) => <div key={listing.id}><span className={`platform ${listing.store.platform.toLowerCase()}`}>{listing.store.platform}</span><div><strong>{listing.store.name}</strong><span>{listing.listing_title || listing.store.mode}</span></div><div><strong>{listing.price ? `${listing.store.currency} ${listing.price.toFixed(2)}` : "待定价"}</strong><span>{listing.status === "NOT_READY" ? "待完善" : listing.status}</span></div></div>)}{detail.listings.length === 0 && <EmptyState>尚未创建店铺版本</EmptyState>}</div>{available.length > 0 ? <form className="add-store-form" onSubmit={onAdd}><select name="store_id" required defaultValue=""><option value="" disabled>选择目标店铺</option>{available.map((store) => <option key={store.id} value={store.id}>{store.platform} · {store.name} · {store.mode}</option>)}</select><input name="listing_title" defaultValue={detail.title} placeholder="店铺商品标题" /><input name="price" type="number" min="0" step="0.01" defaultValue={detail.price ?? ""} placeholder="售价" /><button className="secondary-button" type="submit" disabled={saving}>{saving ? <Loader2 className="spin" size={14} /> : <Plus size={14} />}{saving ? "创建中" : "新增店铺版本"}</button></form> : <div className="all-stores-added"><CheckCircle2 size={15} />所有已配置店铺均已创建版本</div>}</div>;
}
