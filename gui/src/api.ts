export const ENGINE_URL = "http://127.0.0.1:8741";

export interface BackendInfo {
  name: string;
  device: string;
  detail: string;
}

export interface Health {
  status: string;
  version: string;
  backend: BackendInfo;
  data_dir: string;
}

export interface StepStatus {
  status: "pending" | "running" | "done" | "failed" | "skipped";
  progress: number;
  detail: string;
}

export interface Job {
  id: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  video_path: string;
  source_language: string | null;
  target_language: string;
  steps: Record<string, StepStatus>;
  error: string | null;
  artifacts: Record<string, string>;
  backend: BackendInfo | Record<string, never>;
}

export interface Segment {
  start: number;
  end: number;
  text: string;
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const resp = await fetch(ENGINE_URL + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${resp.status}: ${text}`);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  health: () => req<Health>("GET", "/health"),
  listJobs: () => req<{ jobs: Job[] }>("GET", "/jobs"),
  getJob: (id: string) => req<Job>("GET", `/jobs/${id}`),
  createJob: (payload: {
    video_path: string;
    source_language: string | null;
    target_language: string;
    asr: { provider: string; model: string | null };
    translation: {
      enabled: boolean;
      base_url?: string;
      api_key?: string;
      model?: string;
    };
  }) => req<Job>("POST", "/jobs", payload),
  getTranscript: (id: string) =>
    req<{ language: string | null; segments: Segment[] }>(
      "GET",
      `/jobs/${id}/transcript`
    ),
};
