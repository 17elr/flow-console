"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  CalendarClock,
  CheckCircle2,
  LoaderCircle,
  Play,
  RefreshCw,
  Save,
  Settings2,
  Store,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";

type StoreConfig = {
  id: number;
  name: string;
  platform: string;
  mode: string;
  external_shop_id: string | null;
  automation_ready: boolean;
  config: {
    active: boolean;
    auto_publish: boolean;
    price_multiplier: number;
    visual_profile: string;
    max_daily: number;
  };
};
type Schedule = {
  id: number;
  name: string;
  active: boolean;
  run_time: string;
  timezone: string;
  store_ids: number[];
  max_products: number;
  last_run_date: string | null;
};
type Run = {
  id: number;
  trigger: string;
  status: string;
  processed: number;
  succeeded: number;
  failed: number;
  skipped: number;
  started_at: string;
  completed_at: string | null;
  details: Array<{ product_id?: number; spu?: string; status: string; error?: string; reason?: string }>;
};
type Overview = {
  metrics: { active_schedules: number; draft_success: number; draft_failed: number; image_pass_rate: number; runs: number };
  schedules: Schedule[];
  runs: Run[];
  stores: StoreConfig[];
};

const emptyOverview: Overview = {
  metrics: { active_schedules: 0, draft_success: 0, draft_failed: 0, image_pass_rate: 0, runs: 0 },
  schedules: [],
  runs: [],
  stores: [],
};

export function AutomationConsole() {
  const [data, setData] = useState<Overview>(emptyOverview);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [selectedStores, setSelectedStores] = useState<number[]>([]);
  const [runLimit, setRunLimit] = useState(20);
  const [schedule, setSchedule] = useState({ name: "每日已审核商品", run_time: "09:00", max_products: 20 });
  const [expandedRun, setExpandedRun] = useState<number | null>(null);
  const [runPage, setRunPage] = useState(1);
  const [selectedSchedules, setSelectedSchedules] = useState<number[]>([]);
  const [selectedRuns, setSelectedRuns] = useState<number[]>([]);

  function formatRunTime(value: string) {
    const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`;
    return new Date(normalized).toLocaleString("zh-CN", { hour12: false });
  }

  const load = useCallback(async () => {
    const result = await api<Overview>("/api/automation/overview");
    setData(result);
    setSelectedStores((current) => current.filter((id) => result.stores.some((item) => item.id === id && item.automation_ready)).length ? current.filter((id) => result.stores.some((item) => item.id === id && item.automation_ready)) : result.stores.filter((item) => item.config.active && item.automation_ready).map((item) => item.id));
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => load().catch((error) => setNotice(error.message)), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const hasRunningRun = data.runs.some((run) => run.status === "RUNNING");
  useEffect(() => {
    if (!hasRunningRun) return;
    const timer = window.setInterval(() => load().catch(() => undefined), 2000);
    return () => window.clearInterval(timer);
  }, [hasRunningRun, load]);

  const storeNames = useMemo(() => new Map(data.stores.map((item) => [item.id, item.name])), [data.stores]);
  const runStatusLabel = (run: Run) => {
    if (run.status === "RUNNING") return "运行中";
    if (run.status === "COMPLETED") return "完成";
    if (run.status === "INTERRUPTED") return "已中断";
    if (run.status === "WAITING_EXTERNAL") return "等待妙手";
    return "有失败";
  };
  const toggleStore = (id: number) => setSelectedStores((items) => items.includes(id) ? items.filter((item) => item !== id) : [...items, id]);

  async function saveStore(store: StoreConfig) {
    setBusy(`store-${store.id}`);
    try {
      await api(`/api/automation/stores/${store.id}`, { method: "PUT", body: JSON.stringify(store.config) });
      setNotice(`${store.name} 的自动运行设置已保存`);
      await load();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "保存失败");
    } finally { setBusy(""); }
  }

  async function syncStores() {
    setBusy("sync-stores");
    try {
      const results = await Promise.all([
        api<{ count: number }>("/api/miaoshou/stores/sync?mode=SEMI", { method: "POST" }),
        api<{ count: number }>("/api/miaoshou/stores/sync?mode=FULL", { method: "POST" }),
        api<{ count: number }>("/api/miaoshou/stores/sync?mode=ALIEXPRESS", { method: "POST" }),
      ]);
      setNotice(`已同步妙手店铺 ${results.reduce((total, result) => total + result.count, 0)} 条记录`);
      await load();
    } catch (error) { setNotice(error instanceof Error ? error.message : "同步妙手店铺失败"); }
    finally { setBusy(""); }
  }

  async function removeStore(store: StoreConfig) {
    if (!window.confirm(`移除“${store.name}”？历史草稿和数据会保留。`)) return;
    setBusy(`remove-${store.id}`);
    try {
      await api(`/api/stores/${store.id}`, { method: "DELETE" });
      setNotice(`${store.name} 已从自动运行页面移除`);
      await load();
    } catch (error) { setNotice(error instanceof Error ? error.message : "移除店铺失败"); }
    finally { setBusy(""); }
  }

  async function createSchedule() {
    if (!selectedStores.length) return setNotice("请至少选择一个店铺");
    setBusy("schedule");
    try {
      await api("/api/automation/schedules", { method: "POST", body: JSON.stringify({ ...schedule, timezone: "Asia/Shanghai", store_ids: selectedStores, active: true }) });
      setNotice("每日计划已创建，只会处理人工已审核商品");
      await load();
    } catch (error) { setNotice(error instanceof Error ? error.message : "创建计划失败"); }
    finally { setBusy(""); }
  }

  async function toggleSchedule(item: Schedule) {
    setBusy(`schedule-${item.id}`);
    try {
      await api(`/api/automation/schedules/${item.id}`, { method: "PATCH", body: JSON.stringify({ active: !item.active }) });
      await load();
    } catch (error) { setNotice(error instanceof Error ? error.message : "更新计划失败"); }
    finally { setBusy(""); }
  }

  async function deleteSchedule(item: Schedule) {
    if (!window.confirm(`删除计划“${item.name}”？`)) return;
    setBusy(`delete-schedule-${item.id}`);
    try { await api(`/api/automation/schedules/${item.id}`, { method: "DELETE" }); setNotice("每日计划已删除"); await load(); }
    catch (error) { setNotice(error instanceof Error ? error.message : "删除计划失败"); }
    finally { setBusy(""); }
  }

  async function deleteRun(run: Run) {
    if (!window.confirm("删除这条运行结果？")) return;
    setBusy(`delete-run-${run.id}`);
    try { await api(`/api/automation/runs/${run.id}`, { method: "DELETE" }); setNotice("运行结果已删除"); await load(); }
    catch (error) { setNotice(error instanceof Error ? error.message : "删除运行结果失败"); }
    finally { setBusy(""); }
  }

  async function deleteSelectedSchedules() {
    if (!selectedSchedules.length || !window.confirm(`删除选中的 ${selectedSchedules.length} 个计划？`)) return;
    setBusy("delete-schedules");
    try { await Promise.all(selectedSchedules.map((id) => api(`/api/automation/schedules/${id}`, { method: "DELETE" }))); setSelectedSchedules([]); setNotice("已删除选中的每日计划"); await load(); }
    catch (error) { setNotice(error instanceof Error ? error.message : "批量删除计划失败"); }
    finally { setBusy(""); }
  }

  async function deleteSelectedRuns() {
    if (!selectedRuns.length || !window.confirm(`删除选中的 ${selectedRuns.length} 条运行结果？`)) return;
    setBusy("delete-runs");
    try { await Promise.all(selectedRuns.map((id) => api(`/api/automation/runs/${id}`, { method: "DELETE" }))); setSelectedRuns([]); setNotice("已删除选中的运行结果"); await load(); }
    catch (error) { setNotice(error instanceof Error ? error.message : "批量删除运行结果失败"); }
    finally { setBusy(""); }
  }

  async function runNow() {
    if (!selectedStores.length) return setNotice("请至少选择一个店铺");
    setBusy("run");
    try {
      const result = await api<Run>("/api/automation/runs", { method: "POST", body: JSON.stringify({ store_ids: selectedStores, max_products: runLimit }) });
      const waitingExternal = result.details.filter((item) => item.status === "PUBLISHING").length;
      setNotice(`运行完成：成功 ${result.succeeded}，失败 ${result.failed}，等待妙手 ${waitingExternal}，等待审核 ${result.skipped}`);
      setExpandedRun(result.id);
      await load();
    } catch (error) { setNotice(error instanceof Error ? error.message : "运行失败"); }
    finally { setBusy(""); }
  }

  function updateStore(id: number, field: string, value: string | boolean | number) {
    setData((current) => ({ ...current, stores: current.stores.map((item) => item.id === id ? { ...item, config: { ...item.config, [field]: value } } : item) }));
  }

  return <div className="simple-app automation-app">
    <header className="simple-header">
      <div className="simple-brand"><CalendarClock size={20} /><div><strong>Flow Console</strong><span>自动运行中心</span></div></div>
      <div className="simple-header-actions">
        <button onClick={() => load().catch((error) => setNotice(error.message))} title="刷新"><RefreshCw size={15} /></button>
        <Link href="/"><ArrowLeft size={15} /> 商品工作台</Link>
        <Link href="/advanced">高级管理</Link>
      </div>
    </header>
    <main className="simple-main automation-main">
        <div className="simple-title"><div><h1>自动运行</h1><p>按计划把人工已审核商品创建为店铺草稿，未审核商品会自动跳过。</p></div><span className="simple-state">默认仅创建草稿</span></div>
      {notice && <div className="automation-notice">{notice}<button onClick={() => setNotice("")}>×</button></div>}

      <div className="automation-metrics">
        <div><CalendarClock /><span>启用计划</span><strong>{data.metrics.active_schedules}</strong></div>
        <div><CheckCircle2 /><span>草稿成功</span><strong>{data.metrics.draft_success}</strong></div>
        <div><XCircle /><span>草稿失败</span><strong>{data.metrics.draft_failed}</strong></div>
        <div><Settings2 /><span>图片通过率</span><strong>{data.metrics.image_pass_rate}%</strong></div>
      </div>

      <section className="simple-section">
        <div className="section-heading"><span>1</span><div><h2>店铺设置</h2><p>只显示已同步的妙手店铺；移除只隐藏店铺，历史数据保留。</p></div><button className="table-command" onClick={syncStores} disabled={Boolean(busy)}>{busy === "sync-stores" ? <LoaderCircle className="spin" size={14} /> : <RefreshCw size={14} />}同步我的妙手店铺</button></div>
        <div className="automation-store-table">
          <div className="automation-table-head"><span>店铺</span><span>参与自动运行</span><span>自动发布</span><span>价格倍率</span><span>每日上限</span><span>视觉模板</span><span>操作</span></div>
          {data.stores.map((store) => <div className="automation-store-row" key={store.id}>
            <span><strong>{store.name}</strong><small>{store.platform} · {store.mode}</small></span>
            <label className="switch-label"><input type="checkbox" checked={store.config.active} onChange={(event) => updateStore(store.id, "active", event.target.checked)} />启用</label>
            <label className="switch-label"><input type="checkbox" checked={store.config.auto_publish} onChange={(event) => updateStore(store.id, "auto_publish", event.target.checked)} />发布</label>
            <input type="number" min="0.1" max="10" step="0.05" value={store.config.price_multiplier} onChange={(event) => updateStore(store.id, "price_multiplier", Number(event.target.value))} />
            <input type="number" min="1" max="100" value={store.config.max_daily} onChange={(event) => updateStore(store.id, "max_daily", Number(event.target.value))} />
            <select value={store.config.visual_profile} onChange={(event) => updateStore(store.id, "visual_profile", event.target.value)}><option value="neutral-commerce">中性电商</option><option value="clean-luxury">简洁轻奢</option><option value="bright-daily">明亮日常</option></select>
            <span className="store-actions"><button className="table-command" onClick={() => saveStore(store)} disabled={Boolean(busy)}>{busy === `store-${store.id}` ? <LoaderCircle className="spin" size={14} /> : <Save size={14} />}保存</button><button className="table-command danger-command" onClick={() => removeStore(store)} disabled={Boolean(busy)}>移除</button></span>
          </div>)}
          {!data.stores.length && <div className="automation-empty">请先在高级管理中配置店铺。</div>}
        </div>
      </section>

      <div className="automation-columns">
        <section className="simple-section">
          <div className="section-heading"><span>2</span><div><h2>选择目标店铺</h2><p>同一商品可以同时创建多个店铺草稿。</p></div></div>
          <div className="automation-store-checks">{data.stores.filter((item) => item.config.active).map((store) => <label key={store.id}><input type="checkbox" disabled={!store.automation_ready} checked={selectedStores.includes(store.id)} onChange={() => toggleStore(store.id)} /><Store size={15} /><span>{store.name}<small>{store.automation_ready ? store.platform : `${store.platform} · 未同步授权`}</small></span></label>)}</div>
        </section>
        <section className="simple-section">
          <div className="section-heading"><span>3</span><div><h2>立即运行</h2><p>立即处理当前已审核商品，结果会逐款隔离。</p></div></div>
          <div className="automation-run-command"><label>最多处理<input type="number" min="1" max="100" value={runLimit} onChange={(event) => setRunLimit(Number(event.target.value))} />款</label><button className="primary-command" onClick={runNow} disabled={busy === "run"}>{busy === "run" ? <LoaderCircle className="spin" size={16} /> : <Play size={16} />}立即运行</button></div>
        </section>
      </div>

      <section className="simple-section">
        <div className="section-heading"><span>4</span><div><h2>每日计划</h2><p>到达设定时间后自动创建草稿，仍然要求人工审核已通过。</p></div></div>
        <div className="automation-schedule-form"><input value={schedule.name} onChange={(event) => setSchedule({ ...schedule, name: event.target.value })} aria-label="计划名称" /><input type="time" value={schedule.run_time} onChange={(event) => setSchedule({ ...schedule, run_time: event.target.value })} aria-label="运行时间" /><label>每次<input type="number" min="1" max="100" value={schedule.max_products} onChange={(event) => setSchedule({ ...schedule, max_products: Number(event.target.value) })} />款</label><button className="primary-command" onClick={createSchedule} disabled={busy === "schedule"}>{busy === "schedule" ? <LoaderCircle className="spin" size={16} /> : <CalendarClock size={16} />}创建计划</button></div>
        <div className="bulk-toolbar"><label><input type="checkbox" checked={data.schedules.length > 0 && selectedSchedules.length === data.schedules.length} onChange={(event) => setSelectedSchedules(event.target.checked ? data.schedules.map((item) => item.id) : [])} />全选计划</label><button className="danger-command" onClick={deleteSelectedSchedules} disabled={!selectedSchedules.length || Boolean(busy)}>删除已选 ({selectedSchedules.length})</button></div><div className="automation-schedules">{data.schedules.map((item) => <div key={item.id}><input type="checkbox" checked={selectedSchedules.includes(item.id)} onChange={() => setSelectedSchedules((items) => items.includes(item.id) ? items.filter((id) => id !== item.id) : [...items, item.id])} /><span className={item.active ? "schedule-dot active" : "schedule-dot"}></span><span><strong>{item.name}</strong><small>每天 {item.run_time} · 最多 {item.max_products} 款 · {item.store_ids.map((id) => storeNames.get(id) ?? `店铺 ${id}`).join("、")}</small></span><span>{item.last_run_date ? `最近 ${item.last_run_date}` : "尚未运行"}</span><button type="button" onClick={() => toggleSchedule(item)} disabled={Boolean(busy)}>{item.active ? "暂停" : "启用"}</button><button type="button" className="danger-command" onClick={() => deleteSchedule(item)} disabled={Boolean(busy)}>移除</button></div>)}</div>
      </section>

      <section className="simple-section">
        <div className="section-heading"><span>5</span><div><h2>运行结果</h2><p>单款失败不会阻塞其他商品；点开可查看具体原因。</p></div></div>
        <div className="bulk-toolbar"><label><input type="checkbox" checked={data.runs.length > 0 && selectedRuns.length === data.runs.length} onChange={(event) => setSelectedRuns(event.target.checked ? data.runs.map((item) => item.id) : [])} />全选结果</label><button className="danger-command" onClick={deleteSelectedRuns} disabled={!selectedRuns.length || Boolean(busy)}>删除已选 ({selectedRuns.length})</button></div><div className="automation-runs"><div className="automation-table-head run-head"><span>选择</span><span>时间</span><span>方式</span><span>处理</span><span>成功</span><span>失败</span><span>等待审核</span><span>状态</span><span>操作</span></div>{data.runs.slice((runPage - 1) * 10, runPage * 10).map((run) => <div key={run.id} className="run-record"><input type="checkbox" checked={selectedRuns.includes(run.id)} onChange={() => setSelectedRuns((items) => items.includes(run.id) ? items.filter((id) => id !== run.id) : [...items, run.id])} /><button type="button" className="run-row" onClick={() => setExpandedRun(expandedRun === run.id ? null : run.id)}><span>{formatRunTime(run.started_at)}</span><span>{run.trigger === "SCHEDULED" ? "每日计划" : "手动"}</span><span>{run.processed}</span><span className="success-text">{run.succeeded}</span><span className="error-text">{run.failed}</span><span>{run.skipped}</span><span>{runStatusLabel(run)}</span></button><button type="button" className="danger-command run-delete" onClick={(event) => { event.stopPropagation(); deleteRun(run); }} disabled={Boolean(busy)}>删除</button>{expandedRun === run.id && <div className="run-details">{run.details.map((detail, index) => <div key={`${detail.spu}-${index}`}><strong>{detail.spu ?? (detail.product_id ? `商品 ${detail.product_id}` : "本次运行")}</strong><span>{detail.status}</span><p>{detail.error ?? detail.reason ?? "已完成"}</p></div>)}{!run.details.length && <div>{run.status === "RUNNING" ? "正在处理第一款商品，请稍候。" : "本次没有符合条件的商品。"}</div>}</div>}</div>)}{data.runs.length > 10 && <div className="run-pagination"><button onClick={() => setRunPage((page) => Math.max(1, page - 1))} disabled={runPage === 1}>上一页</button><span>第 {runPage} / {Math.ceil(data.runs.length / 10)} 页</span><button onClick={() => setRunPage((page) => Math.min(Math.ceil(data.runs.length / 10), page + 1))} disabled={runPage >= Math.ceil(data.runs.length / 10)}>下一页</button></div>}</div>
      </section>
    </main>
  </div>;
}
