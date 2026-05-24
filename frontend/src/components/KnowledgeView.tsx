import { Database } from "lucide-react";
import type { Report } from "../types";

export function KnowledgeView({ report }: { report?: Report }) {
  const knowledge = report?.json_report.knowledge;
  if (!knowledge) return null;
  return (
    <section className="bg-white p-4">
      <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold"><Database size={18} /> 竞品知识</h2>
      <div className="grid gap-3 md:grid-cols-2">
        {Object.entries(knowledge).map(([key, value]) => (
          <div key={key} className="rounded border border-line bg-panel p-3">
            <div className="mb-2 text-sm font-semibold">{key}</div>
            <pre className="max-h-56 overflow-auto whitespace-pre-wrap text-xs leading-5">{JSON.stringify(value, null, 2)}</pre>
          </div>
        ))}
      </div>
    </section>
  );
}
