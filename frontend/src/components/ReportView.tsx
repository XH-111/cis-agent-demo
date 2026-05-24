import { FileText } from "lucide-react";
import { useState } from "react";
import type { Claim, Evidence, Report } from "../types";
import { categoryLabel } from "../types";
import { EvidencePanel } from "./EvidencePanel";

export function ReportView({
  report,
  evidence,
  selectedClaim,
  onSelect
}: {
  report?: Report;
  evidence: Evidence[];
  selectedClaim?: Claim;
  onSelect: (claim: Claim) => void;
}) {
  const [showJson, setShowJson] = useState(false);
  if (!report) return null;

  return (
    <section className="grid gap-4 bg-white p-4 lg:grid-cols-[minmax(0,1fr)_420px]">
      <div>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-lg font-semibold"><FileText size={18} /> 分析报告</h2>
          <button className="rounded border border-line px-3 py-1.5 text-sm font-semibold" onClick={() => setShowJson((value) => !value)}>
            {showJson ? "收起 JSON 报告" : "展开 JSON 报告"}
          </button>
        </div>
        <pre className="max-h-[420px] overflow-auto rounded border border-line bg-panel p-4 whitespace-pre-wrap text-sm leading-6">{report.markdown}</pre>
        {showJson && (
          <pre className="mt-3 max-h-80 overflow-auto rounded border border-line bg-panel p-4 text-xs leading-5">{JSON.stringify(report.json_report, null, 2)}</pre>
        )}
      </div>

      <div className="space-y-3">
        <section className="rounded border border-line bg-white p-4">
          <h3 className="mb-3 text-sm font-semibold">Claim 列表</h3>
          <div className="space-y-2">
            {report.claims.map((claim) => (
              <button
                key={claim.claim_id}
                onClick={() => onSelect(claim)}
                className={`block w-full rounded border p-3 text-left text-sm ${selectedClaim?.claim_id === claim.claim_id ? "border-accent bg-blue-50" : "border-line bg-panel"} ${claim.evidence_ids.length ? "" : "border-danger bg-red-50"}`}
              >
                <div className="font-semibold">{categoryLabel[claim.category] ?? claim.category} · 置信度 {Math.round(claim.confidence * 100)}%</div>
                <div className="mt-1">{claim.text}</div>
                <div className={`mt-2 text-xs ${claim.evidence_ids.length ? "text-slate-600" : "font-semibold text-danger"}`}>
                  {claim.evidence_ids.length ? `证据：${claim.evidence_ids.join(", ")}` : "缺少 evidence_ids"}
                </div>
              </button>
            ))}
          </div>
        </section>
        <EvidencePanel claim={selectedClaim} evidence={evidence} />
      </div>
    </section>
  );
}
