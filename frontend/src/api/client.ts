import type { CollectorStatus, Dag, Evidence, LlmStatus, QaResult, Report, SearchTestResult, Task, TaskRun, TraceRecord } from "./types";

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
  runTask: (taskId: string, demoMode = "normal", autoRework = false, writerMode = "mock", collectorMode = "mock", analystMode = "evidence", workflowEngine = "custom") =>
    request(`/api/tasks/${taskId}/run?demo_mode=${encodeURIComponent(demoMode)}&auto_rework=${autoRework}&writer_mode=${encodeURIComponent(writerMode)}&collector_mode=${encodeURIComponent(collectorMode)}&analyst_mode=${encodeURIComponent(analystMode)}&workflow_engine=${encodeURIComponent(workflowEngine)}`, { method: "POST" }),
  dag: (taskId: string) => request<Dag>(`/api/tasks/${taskId}/dag`),
  evidence: (taskId: string) => request<Evidence[]>(`/api/tasks/${taskId}/evidence`),
  qa: (taskId: string) => request<QaResult>(`/api/tasks/${taskId}/qa`),
  report: (taskId: string) => request<Report>(`/api/tasks/${taskId}/report`),
  traces: (taskId: string) => request<TraceRecord[]>(`/api/tasks/${taskId}/traces`),
  runs: (taskId: string) => request<TaskRun[]>(`/api/tasks/${taskId}/runs`),
  latestRun: (taskId: string) => request<TaskRun>(`/api/tasks/${taskId}/runs/latest`),
  runEvidence: (taskId: string, runId: string) => request<Evidence[]>(`/api/tasks/${taskId}/runs/${runId}/evidence`),
  runQa: (taskId: string, runId: string) => request<QaResult>(`/api/tasks/${taskId}/runs/${runId}/qa`),
  runReport: (taskId: string, runId: string) => request<Report>(`/api/tasks/${taskId}/runs/${runId}/report`),
  runTraces: (taskId: string, runId: string) => request<TraceRecord[]>(`/api/tasks/${taskId}/runs/${runId}/traces`),
  llmStatus: () => request<LlmStatus>("/api/llm/status"),
  testLlm: () => request<LlmStatus>("/api/llm/test", { method: "POST" }),
  collectorStatus: () => request<CollectorStatus>("/api/search/status"),
  testSearch: (query: string) => request<SearchTestResult>("/api/search/test", { method: "POST", body: JSON.stringify({ query }) })
};
