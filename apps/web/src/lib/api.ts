export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type Status = "WAITING_DATA" | "WAITING_GENERATION" | "READY";

export interface ImportIssue {
  id: number;
  sheet: string;
  row_number: number;
  identifier: string | null;
  field: string | null;
  severity: "ERROR" | "WARNING";
  code: string;
  message: string;
}

export interface ImportBatch {
  id: number;
  filename: string;
  status: string;
  total_rows: number;
  valid_rows: number;
  issue_rows: number;
  created_at: string;
  issues: ImportIssue[];
}

export interface Overview {
  products: number;
  skus: number;
  waiting_data: number;
  waiting_generation: number;
  ready: number;
  issues: number;
  stores: number;
  latest_batch: ImportBatch | null;
}

export interface ProductSummary {
  id: number;
  spu_code: string;
  title: string;
  category: string;
  material: string | null;
  price: number | null;
  currency: string;
  stock: number;
  source_image_url: string | null;
  image_rights: string;
  status: Status;
  image_readiness: "NOT_CHECKED" | "READY" | "BLOCKED" | "PROCESSING" | "GENERATED" | "NEEDS_ATTENTION";
  scene_readiness: string;
  sku_count: number;
  ready_sku_count: number;
  listing_count: number;
  blocker_count: number;
  warning_count: number;
  updated_at: string;
}

export interface SkuComponent {
  id: number;
  component_code: string | null;
  component_name: string;
  color: string | null;
  quantity: number;
  source_image_url: string | null;
}

export interface SkuVariant {
  id: number;
  sku_code: string;
  name: string | null;
  color: string | null;
  size: string | null;
  material: string | null;
  quantity: number;
  price: number | null;
  stock: number;
  source_image_url: string | null;
  is_sellable: boolean;
  status: Status;
  components: SkuComponent[];
}

export interface Store {
  id: number;
  name: string;
  platform: string;
  mode: string;
  currency: string;
  active: boolean;
}

export interface Listing {
  id: number;
  store_id: number;
  listing_title: string | null;
  price: number | null;
  status: string;
  store: Store;
}

export interface Asset {
  id: number;
  sku_id: number | null;
  asset_type: string;
  url: string | null;
  rights_status: string;
  role: string;
  storage_key: string | null;
  sha256: string | null;
  mime_type: string | null;
  width: number | null;
  height: number | null;
  mirror_status: string;
}

export interface ReadinessIssue { code: string; message: string; target: string }
export interface ImageReadiness {
  product_id: number;
  status: "READY" | "BLOCKED";
  missing: ReadinessIssue[];
  warnings: ReadinessIssue[];
}
export interface GeneratedAsset {
  id: number; role: string; version: number; storage_key: string; sha256: string;
  width: number; height: number; byte_size: number; qc_json: string | null; created_at: string;
}
export interface ImageJob {
  id: number; sku_id: number | null; job_type: string; stage: string; status: string;
  retry_count: number; max_retries: number; error_code: string | null; error_message: string | null;
  qc_json: string | null; manifest_json: string | null; result_asset: GeneratedAsset | null;
}
export interface ImageBatch {
  id: number; product_id: number; input_fingerprint: string; pipeline_version: string; version: number;
  status: string; total_jobs: number; completed_jobs: number; failed_jobs: number; waiting_jobs: number;
  pipeline_kind?: string; provider?: string | null; model?: string | null; prompt_version?: string | null; reference_sku_id?: number | null;
  created_at: string; completed_at: string | null; jobs: ImageJob[];
}

export interface SceneProfile {
  product_id: number; reference_sku_id: number | null; model_age: string; clothing_color: string; framing: string;
  model_background: string; lifestyle_scene: string; surface_material: string; light_direction: string; depth_of_field: string;
  model_prompt_override?: string | null; lifestyle_prompt_override?: string | null; template_version: string; status: string; missing: ReadinessIssue[];
}
export interface ProviderStatus { provider: string; model: string; configured: boolean; network_call: boolean; available: boolean; model_visible: boolean; model_count: number; error: string | null; capabilities: Record<string, unknown> }

export interface ProductDetail extends ProductSummary {
  dimensions: string | null;
  weight_g: number | null;
  cost: number | null;
  color: string | null;
  skus: SkuVariant[];
  assets: Asset[];
  listings: Listing[];
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers:
      init?.body instanceof FormData
        ? init.headers
        : { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "请求失败" }));
    const detail = payload.detail;
    const message = typeof detail === "string" ? detail : detail?.message ?? `请求失败 (${response.status})`;
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
