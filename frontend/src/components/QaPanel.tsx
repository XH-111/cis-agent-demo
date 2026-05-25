import { SearchCheck } from "lucide-react";
import type { QaResult, WorkflowSummary } from "../types";
import { Pill } from "../types";

type RouteHistoryItem = {
  from: string;
  to: string;
  reason?: string;
  resultStatus?: string;
};

export function QaPanel({ qa, workflowSummary }: { qa?: QaResult; workflowSummary?: WorkflowSummary }) {
  if (!qa) return null;

  const reworkHistory = buildReworkHistory(qa, workflowSummary);
  const statusClass = qa.status === "passed"
    ? "border-green-200 bg-green-50"
    : qa.status === "manual_review"
      ? "border-amber-300 bg-amber-50"
      : "border-red-200 bg-red-50";

  return (
    <section className={`rounded border p-4 ${statusClass}`}>
      <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold">
        <SearchCheck size={18} /> 业务质检结果
      </h2>

      <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
        <span>final_status:</span>
        <Pill value={qa.status} />
        <span>rework_count: {qa.rework_count}</span>
        <span>max_rework: 3</span>
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <InfoBlock title="hard_errors" items={qa.hard_errors} emptyText="暂无" />
        <InfoBlock title="soft_suggestions" items={qa.soft_suggestions} emptyText="暂无" />
        <InfoBlock
          title="rework_instructions"
          items={(qa.rework_instructions ?? []).map((item) => [
            `error_type: ${item.error_type}`,
            item.failed_claim ? `failed_claim: ${item.failed_claim}` : undefined,
            item.failed_schema ? `failed_schema: ${item.failed_schema}` : undefined,
            `reason: ${item.reason}`,
            `route_to: ${item.target_agent ?? qa.route_to ?? "-"}`,
            `suggested_action: ${item.suggested_action}`,
            `rework_count: ${qa.rework_count}`,
            `final_status: ${qa.status}`,
          ].filter(Boolean).join(" | "))}
          emptyText="暂无"
        />
      </div>

      <div className="mt-3 rounded border border-line bg-white p-3 text-sm">
        <h3 className="mb-2 font-semibold">rework_history</h3>
        {reworkHistory.length ? (
          <div className="space-y-1">
            {reworkHistory.map((item, index) => (
              <div key={`${item.from}-${item.to}-${index}`}>
                第 {index + 1} 次返工：{item.from} -&gt; {item.to}
                {item.reason ? `，原因：${item.reason}` : ""}
                {item.resultStatus ? `，结果：${item.resultStatus}` : ""}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-slate-500">暂无自动返工历史</p>
        )}
      </div>
    </section>
  );
}

function InfoBlock({ title, items, emptyText }: { title: string; items?: string[]; emptyText: string }) {
  const cleanItems = (items ?? []).filter(Boolean);
  return (
    <div className="rounded border border-line bg-white p-3 text-sm">
      <h3 className="mb-2 font-semibold">{title}</h3>
      {cleanItems.length ? (
        <div className="space-y-2">
          {cleanItems.map((item, index) => <p key={`${title}-${index}`}>{item}</p>)}
        </div>
      ) : (
        <p className="text-slate-500">{emptyText}</p>
      )}
    </div>
  );
}

function buildReworkHistory(qa: QaResult, workflowSummary?: WorkflowSummary): RouteHistoryItem[] {
  const qaHistory = (qa.rework_history ?? [])
    .map((item) => ({
      from: "QaAgent",
      to: item.route_to ?? "-",
      reason: item.error_type ?? item.action,
      resultStatus: item.result_status,
    }))
    .filter((item) => item.to !== "-");

  if (qaHistory.length) return qaHistory;

  return (workflowSummary?.conditional_routes_taken ?? [])
    .filter((item) => item.to_node !== "final_report")
    .map((item) => ({
      from: normalizeNodeName(item.from_node ?? "qa"),
      to: normalizeNodeName(item.to_node ?? "-"),
      reason: item.reason,
      resultStatus: item.final_status,
    }));
}

function normalizeNodeName(node: string) {
  const names: Record<string, string> = {
    qa: "QaAgent",
    collector: "CollectorAgent",
    analyst: "AnalystAgent",
    report_writer: "ReportWriterAgent",
    final_report: "FinalReportAgent",
  };
  return names[node] ?? node;
}
