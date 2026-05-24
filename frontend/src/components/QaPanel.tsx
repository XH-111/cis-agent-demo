import { SearchCheck } from "lucide-react";
import type { QaResult } from "../types";
import { Pill } from "../types";

const maxRework = 3;

function panelClass(status: string) {
  if (status === "passed") return "border-green-200 bg-green-50";
  if (status === "manual_review") return "border-amber-200 bg-amber-50";
  return "border-red-200 bg-red-50";
}

function List({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded border border-line bg-white p-3">
      <div className="mb-2 text-sm font-semibold">{title}</div>
      {items.length ? items.map((item) => <p key={item} className="mb-1 text-sm text-slate-700">{item}</p>) : <p className="text-sm text-slate-500">暂无</p>}
    </div>
  );
}

export function QaPanel({ qa }: { qa?: QaResult }) {
  if (!qa) return null;

  return (
    <section className={`rounded border p-4 ${panelClass(qa.status)}`}>
      <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold"><SearchCheck size={18} /> 业务质检结果</h2>
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
        <span>final_status:</span>
        <Pill value={qa.status} />
        <span>rework_count: {qa.rework_count}</span>
        <span>max_rework: {maxRework}</span>
        {qa.route_to && <span className="font-semibold text-danger">route_to: {qa.route_to}</span>}
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <List title="hard_errors" items={qa.hard_errors} />
        <List title="soft_suggestions" items={qa.soft_suggestions} />
        <List
          title="rework_instructions"
          items={qa.rework_instructions.map((item) =>
            [
              `error_type: ${item.error_type}`,
              item.failed_claim ? `failed_claim: ${item.failed_claim}` : undefined,
              item.failed_schema ? `failed_schema: ${item.failed_schema}` : undefined,
              `reason: ${item.reason}`,
              `route_to: ${item.target_agent}`,
              `suggested_action: ${item.suggested_action}`,
              `rework_count: ${qa.rework_count}`,
              `final_status: ${qa.status}`
            ].filter(Boolean).join(" | ")
          )}
        />
      </div>
      <div className="mt-3 rounded border border-line bg-white p-3">
        <div className="mb-2 text-sm font-semibold">rework_history</div>
        {qa.rework_history?.length ? (
          <div className="space-y-2">
            {qa.rework_history.map((item) => (
              <div key={`${item.round}-${item.error_type}-${item.route_to}`} className="rounded border border-line bg-panel p-2 text-sm text-slate-700">
                round: {item.round} | from_status: {item.from_status} | error_type: {item.error_type} | route_to: {item.route_to ?? "-"} | action: {item.action} | result_status: {item.result_status ?? "-"}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-500">暂无自动返工历史</p>
        )}
      </div>
    </section>
  );
}
