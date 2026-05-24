import type { Claim, Evidence } from "../types";

export function EvidencePanel({ claim, evidence }: { claim?: Claim; evidence: Evidence[] }) {
  const related = (claim ? evidence.filter((item) => claim.evidence_ids.includes(item.evidence_id)) : evidence)
    .sort((a, b) => b.confidence - a.confidence);
  return (
    <section className="rounded border border-line bg-white p-4">
      <h2 className="mb-3 text-lg font-semibold">Evidence Panel</h2>
      {claim && !claim.evidence_ids.length && (
        <div className="mb-3 rounded border border-red-200 bg-red-50 p-3 text-sm font-semibold text-danger">
          当前 Claim 缺少 evidence_ids，无法完成证据溯源。
        </div>
      )}
      <div className="space-y-3">
        {related.map((item) => (
          <div key={item.evidence_id} className={`rounded border p-3 text-sm ${item.confidence < 0.5 ? "border-amber-300 bg-amber-50" : "border-line bg-panel"}`}>
            <div className="font-semibold">{item.evidence_id} · {item.source_type}</div>
            <div className="mt-2 text-slate-700">{item.snippet}</div>
            <div className="mt-2 break-all text-xs text-slate-500">{item.url ?? item.local_ref}</div>
            <div className="mt-2 grid gap-1 text-xs text-slate-600">
              <span>source_domain: {item.source_domain ?? "-"}</span>
              <span>source_quality: {item.source_quality ?? "unknown"}</span>
              <span>confidence: {Math.round(item.confidence * 100)}% · {confidenceLabel(item.confidence)}</span>
              <span>collected_at: {item.collected_at ? new Date(item.collected_at).toLocaleString() : "-"}</span>
            </div>
          </div>
        ))}
        {!related.length && <p className="text-sm text-slate-500">暂无可展示证据</p>}
      </div>
    </section>
  );
}

function confidenceLabel(confidence: number) {
  if (confidence >= 0.8) return "高可信";
  if (confidence >= 0.5) return "中可信";
  return "低可信";
}
