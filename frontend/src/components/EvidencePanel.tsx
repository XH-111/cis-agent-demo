import type { Claim, Evidence } from "../types";

export function EvidencePanel({ claim, evidence, evidenceIds }: { claim?: Claim; evidence: Evidence[]; evidenceIds?: string[] }) {
  const selectedIds = evidenceIds?.length ? evidenceIds : undefined;
  const related = (claim
    ? evidence.filter((item) => claim.evidence_ids.includes(item.evidence_id))
    : selectedIds
      ? evidence.filter((item) => selectedIds.includes(item.evidence_id))
      : evidence
  ).sort((a, b) => b.confidence - a.confidence);

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
          <div
            key={item.evidence_id}
            className={`rounded border p-3 text-sm ${
              item.relevance_level === "unrelated" || item.confidence < 0.5 ? "border-amber-300 bg-amber-50" : "border-line bg-panel"
            }`}
          >
            <div className="font-semibold">{item.evidence_id} · {item.source_type}</div>
            <div className="mt-1 text-xs text-slate-600">competitor: {item.competitor ?? "-"}</div>
            <div className="mt-2 text-slate-700">{item.snippet}</div>
            <div className="mt-2 break-all text-xs text-slate-500">{item.url ?? item.local_ref}</div>
            <div className="mt-2 grid gap-1 text-xs text-slate-600">
              <span>source_domain: {item.source_domain ?? "-"}</span>
              <span>source_quality: {item.source_quality ?? "unknown"}</span>
              <span>confidence: {Math.round(item.confidence * 100)}% · {confidenceLabel(item.confidence)}</span>
              <span>relevance: {Math.round((item.relevance_score ?? 1) * 100)}% · {item.relevance_level ?? "high"}</span>
              <span>relevance_reason: {item.relevance_reason ?? "-"}</span>
              <span>collected_at: {item.collected_at ? new Date(item.collected_at).toLocaleString() : "-"}</span>
            </div>
            {item.entity_match_signals && (
              <details className="mt-2 text-xs text-slate-600">
                <summary className="cursor-pointer font-semibold">entity_match_signals</summary>
                <pre className="mt-1 whitespace-pre-wrap rounded border border-line bg-white p-2">{JSON.stringify(item.entity_match_signals, null, 2)}</pre>
              </details>
            )}
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
