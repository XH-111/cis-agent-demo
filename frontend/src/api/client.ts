import type { Dag, Evidence, QaResult, Report, Task, TraceRecord } from "./types";

const baseUrl = "";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${url}`, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

export const api = {
  createTask: (payload: { product_name: string; competitors: string[]; region: string; industry: string }) =>
    request<Task>("/api/tasks", { method: "POST", body: JSON.stringify(payload) }),
  listTasks: () => request<Task[]>("/api/tasks"),
  runTask: (taskId: string) => request(`/api/tasks/${taskId}/run`, { method: "POST" }),
  dag: (taskId: string) => request<Dag>(`/api/tasks/${taskId}/dag`),
  evidence: (taskId: string) => request<Evidence[]>(`/api/tasks/${taskId}/evidence`),
  qa: (taskId: string) => request<QaResult>(`/api/tasks/${taskId}/qa`),
  report: (taskId: string) => request<Report>(`/api/tasks/${taskId}/report`),
  traces: (taskId: string) => request<TraceRecord[]>(`/api/tasks/${taskId}/traces`)
};
