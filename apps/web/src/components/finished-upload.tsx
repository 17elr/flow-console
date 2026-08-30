"use client";
/* eslint-disable @next/next/no-img-element */

import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { CheckCircle2, Eye, FileSpreadsheet, FolderOpen, LoaderCircle, Trash2, Upload, XCircle } from "lucide-react";
import { API_URL, api } from "@/lib/api";

type ProductMatch = {
  product_id: number;
  product_code: string;
  image_count: number;
  assigned: Record<string, string>;
  missing: string[];
  conflicts: string[];
  unused_files: string[];
  detected_skus: Array<{ sku_code: string; name: string; image: string | null }>;
  packaging_preset_id?: number;
};
type ImportResult = {
  status: string;
  product_count: number;
  matched_count: number;
  extra_folders: string[];
  products: ProductMatch[];
  product_ids: number[];
  draft_results?: Array<{ product_id?: number; spu?: string; store_id?: number; status: string; external_id?: string; error?: string }>;
};
type PackagingPreset = { slot: number; image: { id: number; slot: number; filename: string; width: number; height: number } | null };
type DraftRetryResult = Pick<ImportResult, "draft_results">;

const roleNames: Record<string, string> = {
  SPU_WHITE_MAIN: "白底主图", SPU_DETAIL_1: "细节图 1", SPU_DETAIL_2: "细节图 2",
  SPU_SIZE_INFO: "尺寸信息图", SCENE_MODEL_WEAR: "模特佩戴图", SCENE_LIFESTYLE: "生活场景图",
};

export function FinishedUpload({ onImported }: { onImported: () => void }) {
  const [open, setOpen] = useState(false);
  const [workbook, setWorkbook] = useState<File | null>(null);
  const [images, setImages] = useState<File[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);
  const [presets, setPresets] = useState<PackagingPreset[]>([]);
  const [preview, setPreview] = useState<number | null>(null);
  const folders = useMemo(() => new Set(images.map((file) => { const parts = file.webkitRelativePath.replace(/\\/g, "/").split("/").filter(Boolean); return parts.at(-2)?.toLowerCase() === "sku" ? parts.at(-3) : parts.at(-2); }).filter(Boolean)).size, [images]);

  async function loadPresets() { setPresets(await api<PackagingPreset[]>("/api/packaging-presets")); }
  useEffect(() => {
    const timer = window.setTimeout(() => loadPresets().catch(() => undefined), 0);
    return () => window.clearTimeout(timer);
  }, []);

  function chooseFolder(event: ChangeEvent<HTMLInputElement>) {
    setImages(Array.from(event.target.files ?? []).filter((file) => /\.(png|jpe?g|webp)$/i.test(file.name)));
    setResult(null); setError("");
  }

  async function submit() {
    if (!workbook || !images.length) return;
    const body = new FormData(); body.append("workbook", workbook);
    for (const file of images) { body.append("files", file, file.name); body.append("relative_paths", file.webkitRelativePath || file.name); }
    setBusy("import"); setError("");
    try { const data = await api<ImportResult>("/api/imports/finished-images", { method: "POST", body }); setResult(data); onImported(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "导入失败"); }
    finally { setBusy(""); }
  }

  async function uploadPreset(slot: number, event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; if (!file) return;
    const body = new FormData(); body.append("file", file); setBusy(`packaging-${slot}`); setError("");
    try { await api(`/api/packaging-presets/${slot}`, { method: "PUT", body }); await loadPresets(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "包装图片上传失败"); }
    finally { setBusy(""); event.target.value = ""; }
  }

  async function deletePreset(slot: number) {
    if (!window.confirm(`删除包装图 ${slot}？`)) return;
    try { await api(`/api/packaging-presets/${slot}`, { method: "DELETE" }); await loadPresets(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "包装图片删除失败"); }
  }

  async function retryDrafts(productIds: number[]) {
    if (!productIds.length) return;
    const data = await api<DraftRetryResult>("/api/imports/finished-images/auto-drafts", { method: "POST", body: JSON.stringify({ product_ids: productIds }) });
    setResult((current) => current ? { ...current, draft_results: data.draft_results } : current);
    const created = data.draft_results?.filter((item) => item.status === "DRAFT_CREATED").length ?? 0;
    const failed = (data.draft_results?.length ?? 0) - created;
    setError(failed ? `${created} 个草稿已创建，${failed} 个仍失败，请看下方原因` : `${created} 个妙手草稿已创建`);
    onImported();
  }

  async function selectPackaging(productId: number, presetId: number) {
    setBusy(`select-packaging-${productId}`);
    setError("");
    try {
      await api(`/api/products/${productId}/packaging-selection`, { method: "PUT", body: JSON.stringify({ preset_id: presetId }) });
      setResult((current) => current ? { ...current, products: current.products.map((item) => item.product_id === productId ? { ...item, packaging_preset_id: presetId } : item) } : current);
      await retryDrafts([productId]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "包装选择失败");
    } finally {
      setBusy("");
    }
  }

  async function applyPackagingToAll(presetId: number) {
    if (!result) return;
    setBusy(`bulk-packaging-${presetId}`);
    setError("");
    try {
      await api("/api/products/packaging-selection/bulk", { method: "PUT", body: JSON.stringify({ product_ids: result.product_ids, preset_id: presetId }) });
      setResult((current) => current ? { ...current, products: current.products.map((item) => ({ ...item, packaging_preset_id: presetId })) } : current);
      await retryDrafts(result.product_ids);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "批量包装选择失败");
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="finished-import">
      <div className="finished-import-head">
        <div><strong>已有成品图？直接上传并上架</strong><span>跳过 AI 生图，用产品编号自动匹配单页 Excel 和图片文件夹</span></div>
        <button className="finished-toggle" onClick={() => setOpen((value) => !value)}><Upload size={15} />{open ? "收起" : "上传成品图"}</button>
      </div>
      {open ? <div className="finished-import-body">
        <div className="packaging-library">
          <div className="packaging-library-head">
            <div><strong>全局外包装图库</strong><span>保存两种包装，每款商品导入后从中二选一</span></div>
            {result ? <div className="packaging-bulk">{presets.filter((item) => item.image).map((item) => <button key={item.slot} disabled={busy === `bulk-packaging-${item.image!.id}`} onClick={() => applyPackagingToAll(item.image!.id)}>{busy === `bulk-packaging-${item.image!.id}` ? "正在应用" : `全部使用包装图 ${item.slot}`}</button>)}</div> : null}
          </div>
          <div className="packaging-slots">{presets.map((preset) => <div className={preset.image ? "packaging-slot uploaded" : "packaging-slot"} key={preset.slot}>
            <div className="packaging-thumb">{preset.image ? <img src={`${API_URL}/api/packaging-presets/${preset.slot}/content?v=${preset.image.id}`} alt={`包装图 ${preset.slot}`} /> : <Upload size={20} />}</div>
            <div><strong>包装图 {preset.slot}</strong><span>{preset.image?.filename ?? "尚未上传"}</span></div>
            {preset.image ? <button title="查看" onClick={() => setPreview(preset.slot)}><Eye size={14} /></button> : null}
            <label>{busy === `packaging-${preset.slot}` ? "上传中" : preset.image ? "替换" : "上传"}<input type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => uploadPreset(preset.slot, event)} /></label>
            {preset.image ? <button title="删除" onClick={() => deletePreset(preset.slot)}><Trash2 size={14} /></button> : null}
          </div>)}</div>
        </div>
        <div className="finished-upload-grid">
          <label className={workbook ? "finished-drop selected" : "finished-drop"}><FileSpreadsheet size={24} /><strong>{workbook?.name ?? "上传单页产品参数 Excel"}</strong><span>第一列必须是产品编号</span><input type="file" accept=".xlsx,.xlsm" onChange={(event) => { setWorkbook(event.target.files?.[0] ?? null); setResult(null); }} /></label>
          <label className={images.length ? "finished-drop selected" : "finished-drop"}><FolderOpen size={24} /><strong>{images.length ? `${folders} 个产品文件夹` : "选择成品图总文件夹"}</strong><span>{images.length ? `已读取 ${images.length} 张图片` : "每个子文件夹用产品编号命名"}</span><input type="file" multiple accept="image/png,image/jpeg,image/webp" ref={(node) => { if (node) { node.setAttribute("webkitdirectory", ""); node.setAttribute("directory", ""); } }} onChange={chooseFolder} /></label>
        </div>
        <div className="finished-naming"><strong>识别规则</strong><code>产品编号文件夹 / 6张主图（按上传顺序） / sku子文件夹（文件名为SKU编号）</code><span>主图文件名不限；SKU图片名必须在全部商品中唯一，无法匹配或重复时禁止创建草稿。</span></div>
        <div className="finished-actions"><span>{error || (busy.startsWith("bulk-packaging") ? "正在应用包装图并重试创建草稿" : workbook && images.length ? "资料已选择，上传后会自动创建妙手草稿" : "请分别选择 Excel 和成品图文件夹")}</span><button disabled={!workbook || !images.length || busy === "import"} onClick={submit}>{busy === "import" ? <LoaderCircle className="spin" size={15} /> : <CheckCircle2 size={15} />}{busy === "import" ? "正在上传并创建草稿" : "上传并自动创建草稿"}</button></div>
        {result ? <div className="finished-result">
          <div className="finished-result-summary"><strong>{result.matched_count} / {result.product_count} 款图片完整</strong><span>完整商品会自动创建妙手草稿，默认不自动发布</span></div>
          {result.draft_results?.length ? <div className="finished-draft-results">{result.draft_results.map((draft, index) => <div key={`${draft.product_id}-${draft.store_id}-${index}`} className={draft.status === "DRAFT_CREATED" ? "ok" : "issue"}>
            {draft.status === "DRAFT_CREATED" ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
            <span><strong>{draft.spu ?? `商品 ${draft.product_id ?? ""}`}</strong>{draft.status === "DRAFT_CREATED" ? `妙手草稿 ${draft.external_id} 已创建` : draft.error ?? draft.status}</span>
          </div>)}</div> : null}
          {result.extra_folders.length ? <p className="finished-warning">Excel 中找不到这些文件夹：{result.extra_folders.join("、")}</p> : null}
          <div className="finished-match-list">{result.products.map((product) => {
            const blocked = product.missing.length > 0 || product.conflicts.length > 0 || !product.packaging_preset_id;
            return <div key={product.product_id} className={blocked ? "finished-match issue" : "finished-match ok"}>
              {blocked ? <XCircle size={17} /> : <CheckCircle2 size={17} />}
              <div><strong>{product.product_code}</strong><span>{product.image_count} 张图片 · 自动创建 {product.detected_skus.length} 个 SKU</span><small>{product.detected_skus.map((sku) => `${sku.sku_code}=${sku.image}`).join("；") || "未识别SKU图片"}</small>
                {product.missing.length ? <em>缺少：{product.missing.map((item) => roleNames[item] ?? item.replace("NO_SKU_IMAGES", "SKU图片")).join("、")}</em> : null}
                {product.conflicts.length ? <em>SKU名称重复：{product.conflicts.join("、")}</em> : null}
                <div className="packaging-choice"><span>外包装：</span>{presets.filter((item) => item.image).map((preset) => <label key={preset.slot}><input type="radio" name={`packaging-${product.product_id}`} checked={product.packaging_preset_id === preset.image!.id} onChange={() => selectPackaging(product.product_id, preset.image!.id)} />包装图 {preset.slot}</label>)}{!product.packaging_preset_id ? <em>已按规则自动选择；如需调整可重新选择</em> : null}</div>
              </div>
              <button onClick={() => window.location.assign(`/?product=${product.product_id}`)}>检查商品</button>
            </div>;
          })}</div>
        </div> : null}
      </div> : null}
      {preview ? <div className="finished-preview" onClick={() => setPreview(null)}><img src={`${API_URL}/api/packaging-presets/${preview}/content`} alt={`包装图 ${preview}`} /></div> : null}
    </section>
  );
}
