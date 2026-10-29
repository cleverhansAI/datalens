export type Dataset = {
  id: string;
  name: string;
  image_count: number;
  annotation_count: number;
};

export type ViewFilter = {
  field: string;
  operator: "eq" | "neq" | "in" | "gte" | "lte" | "contains";
  value: string | number | Array<string | number>;
};

export type ViewSpec = {
  filters: ViewFilter[];
  group_by?: string | null;
  sort_by?: string | null;
  sort_desc?: boolean;
  page: number;
  page_size: number;
};

export type ViewQueryRequest = {
  spec?: ViewSpec | null;
  saved_view_id?: string | null;
};

export type ViewResult = {
  total: number;
  total_annotations: number;
  class_distribution: Record<string, number>;
  groups: { key: string; count: number }[];
  avg_width?: number;
  avg_height?: number;
  avg_aspect_ratio?: number;
  images: {
    id: number;
    file_path: string;
    directory_name: string;
    width: number;
    height: number;
    aspect_ratio: number;
  }[];
  annotations: {
    id: number;
    image_id: number;
    class_id: number;
    class_name: string;
    bbox_xywh: [number, number, number, number];
    area: number;
    aspect_ratio: number;
  }[];
};

export type ObjectStats = {
  object_count: number;
  avg_area: number;
  class_distribution: Record<string, number>;
  bbox_width_min: number;
  bbox_width_max: number;
  bbox_height_min: number;
  bbox_height_max: number;
};

export type ImageStats = {
  image_count: number;
  avg_width: number;
  avg_height: number;
  avg_aspect_ratio: number;
  directory_distribution: Record<string, number>;
};

export type EmbeddingPoint = {
  entity_id: number;
  x: number;
  y: number;
  cluster_id: number;
  file_path?: string;
};

export type EmbeddingProjection = {
  run_id: string;
  cluster_count: number;
  points: EmbeddingPoint[];
};

export type SavedView = {
  id: string;
  dataset_id: string;
  name: string;
  description: string;
  spec: ViewSpec;
  created_at: string;
  updated_at: string;
};

export type SavedViewCreateRequest = {
  name: string;
  description: string;
  spec: ViewSpec;
};

export type SavedViewUpdateRequest = {
  name?: string;
  description?: string;
  spec?: ViewSpec;
};

export type RunRecord = {
  id: string;
  dataset_id: string;
  saved_view_id?: string | null;
  run_type: string;
  status: "queued" | "running" | "done" | "failed";
  config: Record<string, unknown>;
  view_spec?: ViewSpec | null;
  artifact_path?: string | null;
  artifact_paths: Record<string, string>;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
};

export type SessionState = {
  dataset_id: string | null;
  view: ViewSpec | null;
};

export type TaskStatus = {
  task_id: string;
  state: "queued" | "running" | "done" | "failed";
  progress: number;
  completed?: number | null;
  total?: number | null;
  message: string;
  result?: Record<string, unknown> | null;
};

const API = apiBase();

function apiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE;
  if (configured) {
    return configured.replace(/\/$/, "");
  }
  if (process.env.NODE_ENV === "development") {
    return "http://127.0.0.1:8000/api/v1";
  }
  return "/api/v1";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store"
  });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json() as Promise<T>;
}

export const api = {
  listDatasets: () => request<Dataset[]>("/datasets"),
  getSession: () => request<SessionState>("/session"),
  saveSession: (payload: SessionState) =>
    request<SessionState>("/session", { method: "PUT", body: JSON.stringify(payload) }),
  createDataset: (payload: unknown) =>
    request<Dataset>("/datasets", { method: "POST", body: JSON.stringify(payload) }),
  queryView: (datasetId: string, payload: ViewQueryRequest | ViewSpec) =>
    request<ViewResult>(`/views/${datasetId}/query`, { method: "POST", body: JSON.stringify(payload) }),
  listSavedViews: (datasetId: string) => request<SavedView[]>(`/views/${datasetId}/saved`),
  createSavedView: (datasetId: string, payload: SavedViewCreateRequest) =>
    request<SavedView>(`/views/${datasetId}/saved`, { method: "POST", body: JSON.stringify(payload) }),
  getSavedView: (viewId: string) => request<SavedView>(`/views/saved/${viewId}`),
  updateSavedView: (viewId: string, payload: SavedViewUpdateRequest) =>
    request<SavedView>(`/views/saved/${viewId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteSavedView: (viewId: string) => request<{ ok: boolean }>(`/views/saved/${viewId}`, { method: "DELETE" }),
  imageStats: (datasetId: string) => request<ImageStats>(`/stats/${datasetId}/images`),
  objectStats: (datasetId: string) => request<ObjectStats>(`/stats/${datasetId}/objects`),
  runEmbeddings: (payload: unknown) =>
    request<RunRecord>("/embeddings/run", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  runEmbeddingsAsync: (payload: unknown) =>
    request<TaskStatus>("/embeddings/run_async", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  listEmbeddingRuns: (datasetId: string) => request<RunRecord[]>(`/embeddings/${datasetId}/runs`),
  taskStatus: (taskId: string) => request<TaskStatus>(`/tasks/${taskId}`),
  projection: (runId: string) => request<EmbeddingProjection>(`/embeddings/projection/${runId}`),
  duplicatesVisual: (datasetId: string) => request<unknown[]>(`/duplicates/${datasetId}/visual`),
  exportCoco: (datasetId: string, payload: ViewQueryRequest | ViewSpec) =>
    request<{ path: string }>(`/exports/${datasetId}/coco`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  imageUrl: (filePath: string) => `${API}/media/image?path=${encodeURIComponent(filePath)}`
};
