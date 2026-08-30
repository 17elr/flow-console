"use client";

import {
  AlertTriangle, Check, CheckCircle2, Database, FileImage, Image as ImageIcon,
  Layers3, Loader2, LockKeyhole, Play, RefreshCw, RotateCcw, Search, ShieldCheck,
  Store, Upload, X,
} from "lucide-react";
import Link from "next/link";
import NextImage from "next/image";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { API_URL, ImageBatch, ImageJob, ImageReadiness, ProductDetail, ProductSummary, ProviderStatus, SceneProfile, api } from "@/lib/api";

const roleNames: Record<string, string> = {
  SPU_WHITE_MAIN: "白底主图", SPU_DETAIL_1: "细节图 1", SPU_DETAIL_2: "细节图 2",
  SPU_SIZE_INFO: "尺寸信息图", SKU_WHITE: "SKU 白底图",
  SCENE_MODEL_WEAR: "模特佩戴图", SCENE_LIFESTYLE: "生活场景图",
};
const stageNames: Record<string, string> = {
  QUEUED: "排队", MIRRORING: "镜像素材", LAYOUT: "抠图与排版", QC: "自动质检",
  COMPLETED: "已完成", READY_FOR_REVIEW: "待人工审核", GENERATING: "生成中", REFERENCING: "整理参考图", FAILED: "需处理",
};

function statusLabel(status: string) {
  return ({ NOT_CHECKED: "待检查", NOT_CONFIGURED: "待配置", READY: "可生成", READY_FOR_REVIEW: "待人工审核", BLOCKED: "缺素材", PROCESSING: "处理中", GENERATED: "已生成", NEEDS_ATTENTION: "需处理", COMPLETED: "已完成", RUNNING: "处理中", PENDING: "排队中", WAITING_SOURCE: "待补素材", ENGINE_UNAVAILABLE: "引擎不可用", QC_FAILED: "质检失败", FAILED: "失败", RETRYABLE: "可重试" } as Record<string, string>)[status] ?? status;
}

export function ImagePipeline() {
  const [products, setProducts] = useState<ProductSummary[]>([]);
  const [detail, setDetail] = useState<ProductDetail | null>(null);
  const [batches, setBatches] = useState<ImageBatch[]>([]);
  const [selectedProductId, setSelectedProductId] = useState<number | null>(null);
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null);
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [readiness, setReadiness] = useState<ImageReadiness | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("ALL");
  const [busy, setBusy] = useState(false);
  const [online, setOnline] = useState(true);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [viewMode, setViewMode] = useState<"deterministic" | "scene">("deterministic");
  const [sceneProfile, setSceneProfile] = useState<SceneProfile | null>(null);
  const [providerStatus, setProviderStatus] = useState<ProviderStatus | null>(null);
  const [sceneBatches, setSceneBatches] = useState<ImageBatch[]>([]);
  const uploadRef = useRef<HTMLInputElement>(null);

  const loadAll = useCallback(async () => {
    try {
      const [productRows, batchRows] = await Promise.all([
        api<ProductSummary[]>("/api/products"), api<ImageBatch[]>("/api/image-batches"),
      ]);
      setProducts(productRows); setBatches(batchRows); setOnline(true); setError("");
      setSelectedProductId((current) => current ?? productRows[0]?.id ?? null);
    } catch (reason) {
      setOnline(false); setError(reason instanceof Error ? reason.message : "API 无法连接");
    }
  }, []);

  // The initial request synchronizes this client workspace with the API.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void loadAll(); }, [loadAll]);
  useEffect(() => {
    if (!selectedProductId) return;
    Promise.all([
      api<ProductDetail>(`/api/products/${selectedProductId}`),
      api<ImageReadiness>(`/api/products/${selectedProductId}/image-readiness`),
    ]).then(([nextDetail, nextReadiness]) => { setDetail(nextDetail); setReadiness(nextReadiness); }).catch((reason) => setError(reason.message));
  }, [selectedProductId, batches]);
  useEffect(() => {
    if (!selectedProductId) return;
    Promise.all([
      api<SceneProfile>(`/api/products/${selectedProductId}/scene-profile`),
      api<ProviderStatus>("/api/image-provider/status"),
      api<ImageBatch[]>(`/api/scene-batches?product_id=${selectedProductId}`),
    ]).then(([profile, provider, rows]) => {
      setSceneProfile(profile); setProviderStatus(provider); setSceneBatches(rows);
    }).catch((reason) => setError(reason instanceof Error ? reason.message : "场景配置读取失败"));
  }, [selectedProductId, batches]);
  useEffect(() => {
    const running = batches.some((batch) => ["PENDING", "RUNNING"].includes(batch.status));
    if (!running) return;
    const timer = window.setInterval(() => { void loadAll(); }, 1800);
    return () => window.clearInterval(timer);
  }, [batches, loadAll]);

  const filtered = useMemo(() => products.filter((product) => {
    const matchesText = `${product.spu_code} ${product.title}`.toLowerCase().includes(query.toLowerCase());
    return matchesText && (filter === "ALL" || product.image_readiness === filter);
  }), [products, query, filter]);
  const selectedBatch = useMemo(() => {
    const productBatches = batches.filter((batch) => batch.product_id === selectedProductId);
    return productBatches.find((batch) => batch.id === selectedBatchId) ?? productBatches[0] ?? null;
  }, [batches, selectedBatchId, selectedProductId]);
  const stats = useMemo(() => ({
    ready: products.filter((p) => p.image_readiness === "READY").length,
    processing: products.filter((p) => p.image_readiness === "PROCESSING").length,
    generated: products.filter((p) => p.image_readiness === "GENERATED").length,
    blocked: products.filter((p) => ["BLOCKED", "NEEDS_ATTENTION", "NOT_CHECKED"].includes(p.image_readiness)).length,
  }), [products]);

  async function generate(productIds: number[], force = false) {
    if (!productIds.length) { setNotice("请先选择商品"); return; }
    setBusy(true); setError("");
    let completed = 0;
    for (const productId of productIds) {
      try {
        const batch = await api<ImageBatch>(`/api/products/${productId}/image-batches`, { method: "POST", body: JSON.stringify({ force }) });
        setSelectedBatchId(batch.id); completed += 1;
      } catch (reason) { setError(reason instanceof Error ? reason.message : "批次创建失败"); }
    }
    setNotice(`已提交 ${completed} 款商品`); setChecked(new Set()); setBusy(false); await loadAll();
  }

  async function retry(job: ImageJob) {
    setBusy(true);
    try { await api(`/api/${job.job_type.startsWith("SCENE_") ? "scene-jobs" : "image-jobs"}/${job.id}/retry`, { method: "POST" }); setNotice(`${roleNames[job.job_type]} 已重新排队`); await loadAll(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "重试失败"); }
    finally { setBusy(false); }
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProductId || !uploadRef.current?.files?.[0]) return;
    const form = new FormData(event.currentTarget);
    form.set("product_id", String(selectedProductId)); form.set("file", uploadRef.current.files[0]);
    setBusy(true);
    try { await api("/api/source-assets", { method: "POST", body: form }); setUploadOpen(false); setNotice("素材已校验并存入本地镜像"); await loadAll(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "素材上传失败"); }
    finally { setBusy(false); }
  }

  async function saveSceneProfile() {
    if (!selectedProductId || !sceneProfile) return;
    setBusy(true);
    try {
      const next = await api<SceneProfile>(`/api/products/${selectedProductId}/scene-profile`, { method: "PATCH", body: JSON.stringify(sceneProfile) });
      setSceneProfile(next); setNotice("场景模板已保存"); await loadAll();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "场景模板保存失败"); }
    finally { setBusy(false); }
  }

  async function generateScene(force = false) {
    if (!selectedProductId || !sceneProfile?.reference_sku_id) { setError("请先选择主推 SKU"); return; }
    setBusy(true);
    try {
      const batch = await api<ImageBatch>(`/api/products/${selectedProductId}/scene-batches`, { method: "POST", body: JSON.stringify({ ...sceneProfile, force }) });
      setSceneBatches((current) => [batch, ...current.filter((item) => item.id !== batch.id)]); setNotice("已提交两张场景图，完成后进入人工审核"); await loadAll();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "场景批次创建失败"); }
    finally { setBusy(false); }
  }

  const spuJobs = selectedBatch?.jobs.filter((job) => job.job_type !== "SKU_WHITE") ?? [];
  const skuJobs = selectedBatch?.jobs.filter((job) => job.job_type === "SKU_WHITE") ?? [];
  const productBatches = batches.filter((batch) => batch.product_id === selectedProductId);

  return (
    <div className="app-shell image-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark">FC</span><div><strong>Flow Console</strong><small>AI 电商自动化</small></div></div>
        <div className="topbar-context"><Layers3 size={15} /><span>确定性图片流水线</span><small>模块二</small></div>
        <div className={`connection-pill ${online ? "online" : "offline"}`}><span />{online ? "API 在线" : "API 离线"}</div>
      </header>
      <div className="app-body">
        <aside className="sidebar">
          <div className="sidebar-title">产品工作台</div>
          <nav>
            <Link className="nav-item" href="/"><Database size={18} /><span>商品资料</span></Link>
            <Link className="nav-item active" href="/images"><ImageIcon size={18} /><span>图片流水线</span><small>模块二</small></Link>
            <button className="nav-item" type="button" aria-disabled="true" onClick={() => setNotice("人工审核将在模块五开放")}><ShieldCheck size={18} /><span>人工审核</span><small>后续</small></button>
            <button className="nav-item" type="button" aria-disabled="true" onClick={() => setNotice("渠道发布将在模块六开放")}><Store size={18} /><span>渠道发布</span><small>后续</small></button>
          </nav>
          <div className="sidebar-foot"><div><span className="provider-dot provider-local" />本地确定性处理</div><small>gpt-image-2 调用次数：0</small></div>
        </aside>
        <main className="content image-content">
          <div className="commandbar">
            <div><h1>图片流水线</h1><p>真实素材抠图、独立排版与自动质检；SKU 图片按编码强绑定</p></div>
            <div className="command-actions">
              <button className="secondary-button" type="button" onClick={() => void loadAll()}><RefreshCw size={15} />刷新</button>
              <button className="secondary-button" type="button" disabled={!selectedProductId} onClick={() => setUploadOpen(true)}><Upload size={15} />补充素材</button>
              <button className="primary-button" type="button" disabled={busy || checked.size === 0} onClick={() => void generate([...checked])}>{busy ? <Loader2 className="spin" size={15} /> : <Play size={15} />}批量生成</button>
            </div>
          </div>
          {error && <div className="error-banner"><AlertTriangle size={16} /><span>{error}</span><button type="button" onClick={() => setError("")}><X size={15} /></button></div>}
          {notice && <div className="image-notice"><Check size={15} />{notice}<button type="button" onClick={() => setNotice("")}><X size={14} /></button></div>}
          <section className="metrics image-metrics">
            <div><span>可生成</span><strong>{stats.ready}</strong><small>素材与尺寸完整</small></div>
            <div><span>处理中</span><strong>{stats.processing}</strong><small>镜像 / 抠图 / 质检</small></div>
            <div className="metric-success"><span>已生成</span><strong>{stats.generated}</strong><small>全部任务通过</small></div>
            <div className="metric-warning"><span>需处理</span><strong>{stats.blocked}</strong><small>缺素材或质检失败</small></div>
          </section>
          <section className="image-workspace">
            <div className="image-products-pane">
              <div className="pane-heading"><strong>商品队列</strong><span>{filtered.length} 款</span></div>
              <div className="image-filters"><label className="search-field"><Search size={14} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索 SPU / 商品" /></label><select value={filter} onChange={(e) => setFilter(e.target.value)}><option value="ALL">全部状态</option><option value="READY">可生成</option><option value="BLOCKED">缺素材</option><option value="PROCESSING">处理中</option><option value="GENERATED">已生成</option><option value="NEEDS_ATTENTION">需处理</option></select></div>
              <div className="image-product-list">
                {filtered.map((product) => <div className={`image-product-row ${selectedProductId === product.id ? "selected" : ""}`} key={product.id}>
                  <input aria-label={`选择 ${product.spu_code}`} type="checkbox" checked={checked.has(product.id)} onChange={(e) => setChecked((current) => { const next = new Set(current); if (e.target.checked) next.add(product.id); else next.delete(product.id); return next; })} />
                  <button type="button" onClick={() => { setSelectedProductId(product.id); setSelectedBatchId(null); }}><strong>{product.title}</strong><span className="mono">{product.spu_code}</span><small>{product.sku_count} SKU</small></button>
                  <span className={`pipeline-status ${product.image_readiness.toLowerCase()}`}>{statusLabel(product.image_readiness)}</span>
                </div>)}
              </div>
            </div>
            <div className="image-output-pane">
              <div className="output-toolbar">
                <div><strong>{detail?.title ?? "选择商品"}</strong><span className="mono">{detail?.spu_code}</span></div>
                <div className="version-picker"><span>版本</span><select value={selectedBatch?.id ?? ""} onChange={(e) => setSelectedBatchId(Number(e.target.value))}><option value="">尚未生成</option>{productBatches.map((batch) => <option key={batch.id} value={batch.id}>v{batch.version} · {statusLabel(batch.status)}</option>)}</select></div>
              </div>
              <div className="tabs image-tabs"><button type="button" className={viewMode === "deterministic" ? "active" : ""} onClick={() => setViewMode("deterministic")}>确定性图片</button><button type="button" className={viewMode === "scene" ? "active" : ""} onClick={() => setViewMode("scene")}>场景图片</button></div>
              {viewMode === "scene" && <SceneWorkspace profile={sceneProfile} provider={providerStatus} batches={sceneBatches} detail={detail} busy={busy} onProfileChange={setSceneProfile} onSave={() => void saveSceneProfile()} onGenerate={() => void generateScene(false)} onForce={() => void generateScene(true)} onRetry={retry} />}
              {readiness?.status === "BLOCKED" && <div className="readiness-strip"><AlertTriangle size={16} /><div><strong>图片素材未就绪</strong><span>{readiness.missing.map((item) => `${item.target}：${item.message}`).join("；")}</span></div><button type="button" onClick={() => setUploadOpen(true)}>补充素材</button></div>}
              {selectedBatch && <div className="batch-progress"><span style={{ width: `${Math.round((selectedBatch.completed_jobs / Math.max(1, selectedBatch.total_jobs)) * 100)}%` }} /><div>{selectedBatch.completed_jobs}/{selectedBatch.total_jobs} 已完成 · {selectedBatch.waiting_jobs + selectedBatch.failed_jobs} 需处理</div></div>}
              {viewMode === "deterministic" && <div className="output-scroll">
                <div className="output-section-title"><div><strong>SPU 确定性主图</strong><span>四张独立单图 · 1024×1024 PNG</span></div>{readiness?.status === "READY" && !selectedBatch && <button className="primary-button" type="button" onClick={() => void generate([readiness.product_id])}><Play size={14} />开始生成</button>}</div>
                <div className="spu-output-grid">{(spuJobs.length ? spuJobs : ["SPU_WHITE_MAIN", "SPU_DETAIL_1", "SPU_DETAIL_2", "SPU_SIZE_INFO"].map((role) => ({ id: role, job_type: role, status: "EMPTY", stage: "QUEUED", result_asset: null } as unknown as ImageJob))).map((job) => <OutputTile key={job.id} job={job} onRetry={retry} />)}</div>
                <div className="output-section-title"><div><strong>SKU 白底图</strong><span>每个可销售 SKU 独立生成并绑定编码</span></div><span>{skuJobs.length || detail?.skus.filter((sku) => sku.is_sellable).length || 0} 张</span></div>
                <div className="sku-output-list">{skuJobs.length ? skuJobs.map((job) => <OutputTile key={job.id} job={job} skuCode={detail?.skus.find((sku) => sku.id === job.sku_id)?.sku_code} onRetry={retry} />) : detail?.skus.filter((sku) => sku.is_sellable).map((sku) => <OutputTile key={sku.id} skuCode={sku.sku_code} job={{ id: sku.id, job_type: "SKU_WHITE", status: "EMPTY", stage: "QUEUED", result_asset: null } as unknown as ImageJob} onRetry={retry} />)}</div>
                <div className="output-section-title locked-title"><div><strong>生成式场景图</strong><span>模特佩戴图与生活场景图</span></div><span><LockKeyhole size={13} />模块三</span></div>
                <div className="locked-output-row"><div><LockKeyhole size={18} />模特佩戴图</div><div><LockKeyhole size={18} />生活场景图</div></div>
              </div>}
            </div>
            <aside className="image-history-pane">
              <div className="pane-heading"><strong>运行记录</strong><span>{productBatches.length} 个版本</span></div>
              <div className="readiness-summary"><div><span>当前就绪状态</span><strong className={readiness?.status === "READY" ? "success-text" : "warning-text"}>{statusLabel(readiness?.status ?? "NOT_CHECKED")}</strong></div>{readiness?.warnings.map((item) => <p key={item.code}><AlertTriangle size={12} />{item.message}</p>)}</div>
              <div className="version-history">{productBatches.map((batch) => <button type="button" className={selectedBatch?.id === batch.id ? "selected" : ""} key={batch.id} onClick={() => setSelectedBatchId(batch.id)}><div><strong>版本 v{batch.version}</strong><span className={`pipeline-status ${batch.status.toLowerCase()}`}>{statusLabel(batch.status)}</span></div><span>{new Date(batch.created_at).toLocaleString("zh-CN")}</span><small>{batch.pipeline_version} · 指纹 {batch.input_fingerprint.slice(0, 8)}</small></button>)}</div>
              <div className="zero-ai-note"><FileImage size={16} /><div><strong>确定性处理</strong><span>本模块未调用 gpt-image-2</span></div></div>
            </aside>
          </section>
        </main>
      </div>
      {uploadOpen && <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) setUploadOpen(false); }}><form className="modal-card asset-upload-modal" onSubmit={upload}><div className="modal-heading"><div><strong>补充真实素材</strong><span>{detail?.spu_code}</span></div><button className="icon-button" type="button" onClick={() => setUploadOpen(false)}><X size={17} /></button></div><div className="modal-body"><label><span>素材角色</span><select name="role" defaultValue="SPU_MAIN_SOURCE"><option value="SPU_MAIN_SOURCE">SPU 主原图</option><option value="SPU_DETAIL_1_SOURCE">细节原图 1</option><option value="SPU_DETAIL_2_SOURCE">细节原图 2</option><option value="SKU_SOURCE">SKU 专属原图</option></select></label><label><span>绑定 SKU（SKU 素材必选）</span><select name="sku_id" defaultValue=""><option value="">不绑定 SKU</option>{detail?.skus.map((sku) => <option key={sku.id} value={sku.id}>{sku.sku_code}</option>)}</select></label><label><span>图片文件</span><input ref={uploadRef} type="file" accept="image/png,image/jpeg,image/webp" required /></label><p>图片会校验哈希、尺寸和格式后存入受控存储，不会由 AI 补画缺失商品。</p><button className="primary-button full" disabled={busy} type="submit">{busy ? <Loader2 className="spin" size={15} /> : <Upload size={15} />}上传并校验</button></div></form></div>}
    </div>
  );
}

function OutputTile({ job, skuCode, onRetry }: { job: ImageJob; skuCode?: string; onRetry: (job: ImageJob) => void }) {
  const retryable = ["RETRYABLE", "WAITING_SOURCE", "QC_FAILED", "ENGINE_UNAVAILABLE"].includes(job.status);
  return <article className={`output-tile ${job.status.toLowerCase()}`}>
    <div className="output-preview">{job.result_asset ? <NextImage unoptimized width={82} height={82} src={`${API_URL}/api/assets/${job.result_asset.id}/content`} alt={skuCode ?? roleNames[job.job_type]} /> : job.status === "EMPTY" ? <ImageIcon size={22} /> : <Loader2 className={job.status === "RUNNING" ? "spin" : ""} size={22} />}</div>
    <div className="output-meta"><strong>{skuCode ?? roleNames[job.job_type]}</strong><span>{statusLabel(job.status)} · {stageNames[job.stage] ?? job.stage}</span>{job.error_message && <small title={job.error_message}>{job.error_message}</small>}</div>
    {["COMPLETED", "READY_FOR_REVIEW"].includes(job.status) ? <CheckCircle2 className="output-ok" size={17} /> : retryable ? <button className="icon-button" type="button" title="重试任务" onClick={() => onRetry(job)}><RotateCcw size={15} /></button> : null}
  </article>;
}

function SceneWorkspace({ profile, provider, batches, detail, busy, onProfileChange, onSave, onGenerate, onForce, onRetry }: { profile: SceneProfile | null; provider: ProviderStatus | null; batches: ImageBatch[]; detail: ProductDetail | null; busy: boolean; onProfileChange: (profile: SceneProfile | null) => void; onSave: () => void; onGenerate: () => void; onForce: () => void; onRetry: (job: ImageJob) => void }) {
  const latest = batches[0];
  const update = (key: keyof SceneProfile, value: string | number | null) => profile && onProfileChange({ ...profile, [key]: value });
  return <div className="scene-workspace">
    <div className="scene-config-panel">
      <div className="output-section-title"><div><strong>场景模板与主推 SKU</strong><span>两张独立单图，生成后进入人工审核</span></div><span className={provider?.available ? "success-text" : "warning-text"}>{provider?.available ? `${provider.provider} · ${provider.model} 在线` : provider?.configured ? "Provider 检查失败" : "Provider 未配置"}</span></div>
      <label><span>主推 SKU</span><select value={profile?.reference_sku_id ?? ""} onChange={(e) => update("reference_sku_id", e.target.value ? Number(e.target.value) : null)}><option value="">选择主推 SKU</option>{detail?.skus.filter((sku) => sku.is_sellable).map((sku) => <option key={sku.id} value={sku.id}>{sku.sku_code} · {sku.name ?? sku.color}</option>)}</select></label>
      <label><span>模特模板覆盖</span><textarea value={profile?.model_prompt_override ?? ""} onChange={(e) => update("model_prompt_override", e.target.value)} placeholder="可选：服装、构图或背景覆盖" /></label>
      <label><span>生活场景模板覆盖</span><textarea value={profile?.lifestyle_prompt_override ?? ""} onChange={(e) => update("lifestyle_prompt_override", e.target.value)} placeholder="可选：台面、光线或景深覆盖" /></label>
      <div className="scene-actions"><button className="secondary-button" type="button" disabled={busy || !profile} onClick={onSave}>保存模板</button><button className="primary-button" type="button" disabled={busy || profile?.status !== "READY"} onClick={onGenerate}><Play size={14} />生成场景图</button><button className="secondary-button" type="button" disabled={busy || profile?.status !== "READY"} onClick={onForce}>强制新版本</button></div>
      {profile?.status === "BLOCKED" && <div className="readiness-strip"><AlertTriangle size={15} /><span>{profile.missing.map((item) => item.message).join("；")}</span></div>}
    </div>
    <div className="scene-results"><div className="output-section-title"><div><strong>场景图结果</strong><span>{latest ? `v${latest.version} · ${statusLabel(latest.status)}` : "尚未生成"}</span></div><span>状态：待人工审核</span></div><div className="spu-output-grid">{(["SCENE_MODEL_WEAR", "SCENE_LIFESTYLE"] as const).map((role) => { const job = latest?.jobs.find((item) => item.job_type === role); return <OutputTile key={role} job={job ?? ({ id: role, job_type: role, status: "EMPTY", stage: "QUEUED", result_asset: null } as unknown as ImageJob)} onRetry={onRetry} />; })}</div></div>
  </div>;
}
