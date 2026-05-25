import { Database } from "lucide-react";
import type { Evidence, Report } from "../types";

export function KnowledgeView({
  report,
  evidence,
  onEvidenceIdsSelect
}: {
  report?: Report;
  evidence?: Evidence[];
  onEvidenceIdsSelect?: (ids: string[]) => void;
}) {
  const knowledge = report?.json_report.knowledge;
  if (!knowledge) return null;
  const evidenceById = new Map((evidence ?? []).map((item) => [item.evidence_id, item]));
  return (
    <section className="bg-white p-4">
      <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold"><Database size={18} /> 竞品知识</h2>
      <div className="grid gap-3 md:grid-cols-2">
        {Object.entries(knowledge).map(([key, value]) => {
          const evidenceIds = extractEvidenceIds(value);
          const insufficient = JSON.stringify(value).includes("Evidence is insufficient");
          return (
            <div key={key} className={`rounded border p-3 ${insufficient ? "border-amber-300 bg-amber-50" : "border-line bg-panel"}`}>
              <div className="mb-2 text-sm font-semibold">{key}</div>
              {insufficient && <div className="mb-2 rounded border border-amber-300 bg-white px-2 py-1 text-xs text-warning">证据不足，建议补充更多公开来源。</div>}
              {evidenceIds.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-1 text-xs">
                  {evidenceIds.map((id) => (
                    <button
                      key={id}
                      className="rounded border border-line bg-white px-2 py-0.5 text-slate-700 hover:border-accent"
                      onClick={() => onEvidenceIdsSelect?.([id])}
                      title={evidenceById.get(id)?.source_domain ?? id}
                    >
                      {id}
                    </button>
                  ))}
                </div>
              )}
              <pre className="max-h-56 overflow-auto whitespace-pre-wrap text-xs leading-5">{JSON.stringify(value, null, 2)}</pre>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function extractEvidenceIds(value: unknown): string[] {
  const ids = new Set<string>();
  function walk(item: unknown) {
    if (Array.isArray(item)) {
      item.forEach(walk);
      return;
    }
    if (item && typeof item === "object") {
      for (const [key, nested] of Object.entries(item)) {
        if (key === "evidence_ids" && Array.isArray(nested)) {
          nested.forEach((id) => {
            if (typeof id === "string") ids.add(id);
          });
        } else {
          walk(nested);
        }
      }
    }
  }
  walk(value);
  return Array.from(ids);
}
