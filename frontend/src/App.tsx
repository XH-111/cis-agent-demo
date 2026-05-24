import { Activity, Database, FileText, Info, Play, Plus, SearchCheck, Sparkles } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import type { Claim, Dag, Evidence, QaResult, Report, Task, TraceRecord } from "./api/types";

const statusClass: Record<string, string> = {
  completed: "bg-green-100 text-success border-green-300",
  passed: "bg-green-100 text-success border-green-300",
  failed: "bg-red-100 text-danger border-red-300",
  qa_failed: "bg-amber-100 text-warning border-amber-300",
  manual_review: "bg-amber-100 text-warning border-amber-300",
  running: "bg-blue-100 text-accent border-blue-300",
  pending: "bg-white text-slate-500 border-line",
  created: "bg-white text-slate-500 border-line"
};

const statusLabel: Record<string, string> = {
  completed: "已完成",
  passed: "已通过",
  failed: "失败",
  qa_failed: "QA 未通过",
  manual_review: "需要人工复核",
  running: "运行中",
  pending: "待执行",
  created: "已创建"
};

const categoryLabel: Record<string, string> = {
  positioning: "定位",
  feature: "功能",
  pricing: "定价",
  persona: "用户画像",
  risk: "风险",
  recommendation: "建议"
};

type TaskFormState = {
  taskName: string;
  competitors: string;
  region: string;
  industry: string;
};

const examples: Array<{ label: string; values: TaskFormState }> = [
  {
    label: "使用示例：AI 编程工具",
    values: {
      taskName: "AI 编程工具竞品分析",
      competitors: "Cursor, Trae, GitHub Copilot",
      region: "全球",
      industry: "AI Coding Agent"
    }
  },
  {
    label: "使用示例：企业协作工具",
    values: {
      taskName: "企业协作工具竞品分析",
      competitors: "飞书, 钉钉, 企业微信",
      region: "中国",
      industry: "B2B SaaS"
    }
  },
  {
    label: "使用示例：美妆电商平台",
    values: {
      taskName: "美妆电商平台竞品分析",
      competitors: "Sephora, Ulta Beauty, Watsons",
      region: "全球",
      industry: "Beauty Retail"
    }
  }
];

function Pill({ value }: { value: string }) {
  return <span className={`rounded border px-2 py-0.5 text-xs font-semibold ${statusClass[value] ?? statusClass.pending}`}>{statusLabel[value] ?? value}</span>;
}

function Field({
  label,
  value,
  placeholder,
  helper,
  error,
  onChange
}: {
  label: string;
  value: string;
  placeholder: string;
  helper: string;
  error?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="text-sm font-semibold text-ink">{label}</span>
      <input
        className={`mt-1 w-full rounded border px-3 py-2 ${error ? "border-danger bg-red-50" : "border-line bg-white"}`}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
      <span className="mt-1 block text-xs leading-5 text-slate-500">{helper}</span>
      {error && <span className="mt-1 block text-xs font-semibold text-danger">{error}</span>}
    </label>
  );
}

function TaskForm({ onCreated }: { onCreated: (task: Task) => void }) {
  const [form, setForm] = useState<TaskFormState>({
    taskName: "企业协作工具竞品分析",
    competitors: "飞书, 钉钉, 企业微信",
    region: "中国",
    industry: "B2B SaaS"
  });
  const [errors, setErrors] = useState<Partial<Record<keyof TaskFormState, string>>>({});
  const [busy, setBusy] = useState(false);

  function update(field: keyof TaskFormState, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
  }

  function parseCompetitors(value: string) {
    return value.split(/[,，]/).map((item) => item.trim()).filter(Boolean);
  }

  function validate() {
    const nextErrors: Partial<Record<keyof TaskFormState, string>> = {};
    const competitorList = parseCompetitors(form.competitors);
    if (!form.taskName.trim()) nextErrors.taskName = "请输入分析任务名称。";
    if (competitorList.length < 2) nextErrors.competitors = "请至少输入 2 个竞品名称。";
    if (!form.region.trim()) nextErrors.region = "请输入分析区域。";
    if (!form.industry.trim()) nextErrors.industry = "请输入行业或产品类型。";
    setErrors(nextErrors);
    return { valid: Object.keys(nextErrors).length === 0, competitorList };
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const { valid, competitorList } = validate();
    if (!valid) return;
    setBusy(true);
    try {
      const task = await api.createTask({
        product_name: form.taskName.trim(),
        competitors: competitorList,
        region: form.region.trim(),
        industry: form.industry.trim()
      });
      onCreated(task);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded border border-line bg-white p-4">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">创建分析任务</h2>
          <p className="mt-1 text-sm text-slate-600">创建任务只保存分析目标；点击“运行 Demo 工作流”后才会执行 Mock Agent DAG。</p>
        </div>
        <Sparkles className="mt-1 text-accent" size={20} />
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {examples.map((example) => (
          <button
            key={example.label}
            type="button"
            onClick={() => {
              setForm(example.values);
              setErrors({});
            }}
            className="rounded border border-line bg-panel px-3 py-2 text-sm font-semibold text-ink hover:border-accent hover:text-accent"
          >
            {example.label}
          </button>
        ))}
      </div>

      <form onSubmit={submit} className="grid gap-4 md:grid-cols-2">
        <Field
          label="Task Name / 分析任务名称"
          value={form.taskName}
          placeholder="例如：企业协作工具竞品分析"
          helper="用于标识本次分析任务，方便后续查看 Trace 和报告。"
          error={errors.taskName}
          onChange={(value) => update("taskName", value)}
        />
        <Field
          label="Competitors / 竞品名称"
          value={form.competitors}
          placeholder="例如：飞书, 钉钉, 企业微信"
          helper="多个竞品请用中文逗号或英文逗号分隔。"
          error={errors.competitors}
          onChange={(value) => update("competitors", value)}
        />
        <Field
          label="Region / 分析区域"
          value={form.region}
          placeholder="例如：中国 / 全球 / 北美"
          helper="用于限定信息采集范围和市场分析口径。"
          error={errors.region}
          onChange={(value) => update("region", value)}
        />
        <Field
          label="Industry / 行业或产品类型"
          value={form.industry}
          placeholder="例如：B2B SaaS / 电商平台 / AI 编程工具"
          helper="用于选择竞品知识 Schema 和分析维度。"
          error={errors.industry}
          onChange={(value) => update("industry", value)}
        />
        <div className="md:col-span-2">
          <button className="inline-flex items-center justify-center gap-2 rounded bg-accent px-4 py-2 font-semibold text-white disabled:opacity-50" disabled={busy}>
            <Plus size={16} /> 创建任务
          </button>
          <span className="ml-3 align-middle text-sm text-slate-600">只创建任务，不运行 Agent。</span>
        </div>
      </form>
    </section>
  );
}

function DemoGuide() {
  return (
    <section className="rounded border border-line bg-white p-4">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">本 Demo 会做什么</h2>
          <p className="mt-1 text-sm text-slate-600">模拟一次可追溯的多 Agent 竞品分析链路。</p>
        </div>
        <Info className="mt-1 text-accent" size={20} />
      </div>
      <div className="space-y-2 text-sm text-slate-700">
        <p><strong>PlannerAgent：</strong>识别分析目标并生成 DAG</p>
        <p><strong>CollectorAgent：</strong>生成 Mock 证据并绑定来源</p>
        <p><strong>AnalystAgent：</strong>抽取竞品知识结构</p>
        <p><strong>ReportWriterAgent：</strong>生成带证据 ID 的报告</p>
        <p><strong>QaAgent：</strong>检查 Schema、证据覆盖和报告格式</p>
        <p><strong>FinalReport：</strong>输出最终 Markdown / JSON 报告</p>
      </div>
      <div className="mt-4 rounded border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-900">
        当前版本使用 Mock 数据，不调用真实大模型、不执行真实爬虫，重点展示多 Agent 协作、Schema 校验、证据绑定、QA 反馈闭环和 Trace 可观测性。
      </div>
    </section>
  );
}

function DagView({ dag }: { dag?: Dag }) {
  if (!dag) return null;
  return (
    <section className="bg-white p-4">
      <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold"><Activity size={18} /> DAG 执行状态</h2>
      <div className="grid gap-3 md:grid-cols-6">
        {dag.nodes.map((node) => (
          <div key={node.id} className="min-h-28 rounded border border-line bg-panel p-3">
            <div className="text-sm font-semibold">{node.id}</div>
            <p className="mt-2 min-h-10 text-xs text-slate-600">{node.label}</p>
            <Pill value={node.status} />
          </div>
        ))}
      </div>
      <div className="mt-3 text-xs text-slate-600">{dag.edges.map((edge) => `${edge.source} -> ${edge.target}（${edge.label}）`).join(" | ")}</div>
    </section>
  );
}

function KnowledgeView({ report }: { report?: Report }) {
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

function ReportView({ report, selectedClaim, onSelect }: { report?: Report; selectedClaim?: Claim; onSelect: (claim: Claim) => void }) {
  if (!report) return null;
  return (
    <section className="grid gap-4 bg-white p-4 lg:grid-cols-[1fr_420px]">
      <div>
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold"><FileText size={18} /> 分析报告</h2>
        <pre className="max-h-[460px] overflow-auto rounded border border-line bg-panel p-4 whitespace-pre-wrap text-sm leading-6">{report.markdown}</pre>
      </div>
      <div>
        <h3 className="mb-3 text-sm font-semibold">关键结论</h3>
        <div className="space-y-2">
          {report.claims.map((claim) => (
            <button
              key={claim.claim_id}
              onClick={() => onSelect(claim)}
              className={`block w-full rounded border p-3 text-left text-sm ${selectedClaim?.claim_id === claim.claim_id ? "border-accent bg-blue-50" : "border-line bg-panel"}`}
            >
              <div className="font-semibold">{categoryLabel[claim.category] ?? claim.category} · 置信度 {Math.round(claim.confidence * 100)}%</div>
              <div className="mt-1">{claim.text}</div>
              <div className="mt-2 text-xs text-slate-600">证据：{claim.evidence_ids.join(", ")}</div>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function EvidencePanel({ claim, evidence }: { claim?: Claim; evidence: Evidence[] }) {
  const related = claim ? evidence.filter((item) => claim.evidence_ids.includes(item.evidence_id)) : evidence;
  return (
    <section className="bg-white p-4">
      <h2 className="mb-3 text-lg font-semibold">证据 / 来源面板</h2>
      <div className="grid gap-3 md:grid-cols-2">
        {related.map((item) => (
          <div key={item.evidence_id} className="rounded border border-line bg-panel p-3 text-sm">
            <div className="font-semibold">{item.evidence_id} · {item.source_type}</div>
            <div className="mt-1 text-slate-700">{item.snippet}</div>
            <div className="mt-2 break-all text-xs text-slate-500">{item.url ?? item.local_ref}</div>
            <div className="mt-2 text-xs">置信度 {Math.round(item.confidence * 100)}%</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function QaPanel({ qa }: { qa?: QaResult }) {
  if (!qa) return null;
  return (
    <section className="bg-white p-4">
      <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold"><SearchCheck size={18} /> 质检结果</h2>
      <div className="mb-3 flex items-center gap-3"><Pill value={qa.status} /><span className="text-sm">返工次数：{qa.rework_count}</span></div>
      <div className="grid gap-3 md:grid-cols-3">
        <List title="硬错误" items={qa.hard_errors} />
        <List title="优化建议" items={qa.soft_suggestions} />
        <List title="返工指令" items={qa.rework_instructions.map((item) => `${item.target_agent}: ${item.suggested_action}`)} />
      </div>
    </section>
  );
}

function List({ title, items }: { title: string; items: string[] }) {
  return <div className="rounded border border-line bg-panel p-3"><div className="mb-2 text-sm font-semibold">{title}</div>{items.length ? items.map((item) => <p key={item} className="text-sm text-slate-700">{item}</p>) : <p className="text-sm text-slate-500">暂无</p>}</div>;
}

function TraceViewer({ traces }: { traces: TraceRecord[] }) {
  const [agent, setAgent] = useState("全部");
  const agents = useMemo(() => ["全部", ...Array.from(new Set(traces.map((trace) => trace.agent_name)))], [traces]);
  const filtered = agent === "全部" ? traces : traces.filter((trace) => trace.agent_name === agent);
  return (
    <section className="bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Trace 查看器</h2>
        <select className="rounded border border-line px-3 py-2 text-sm" value={agent} onChange={(event) => setAgent(event.target.value)}>
          {agents.map((item) => <option key={item}>{item}</option>)}
        </select>
      </div>
      <div className="overflow-auto rounded border border-line">
        <table className="w-full min-w-[900px] border-collapse text-left text-sm">
          <thead className="bg-panel">
            <tr><th className="p-2">Agent</th><th className="p-2">Trace</th><th className="p-2">输入摘要</th><th className="p-2">输出摘要</th><th className="p-2">校验结果</th><th className="p-2">耗时(ms)</th><th className="p-2">重试</th></tr>
          </thead>
          <tbody>
            {filtered.map((trace) => (
              <tr key={trace.trace_id} className="border-t border-line">
                <td className="p-2 font-semibold">{trace.agent_name}</td>
                <td className="p-2 text-xs">{trace.trace_id}</td>
                <td className="p-2">{trace.input_summary}</td>
                <td className="p-2">{trace.output_summary}</td>
                <td className="p-2"><Pill value={trace.schema_validation_result} /></td>
                <td className="p-2">{trace.elapsed_time_ms}</td>
                <td className="p-2">{trace.retry_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function App() {
  const [task, setTask] = useState<Task>();
  const [dag, setDag] = useState<Dag>();
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [qa, setQa] = useState<QaResult>();
  const [report, setReport] = useState<Report>();
  const [traces, setTraces] = useState<TraceRecord[]>([]);
  const [selectedClaim, setSelectedClaim] = useState<Claim>();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listTasks().then((tasks) => {
      if (tasks[0]) {
        setTask(tasks[0]);
        refresh(tasks[0].task_id);
      }
    }).catch(() => undefined);
  }, []);

  async function refresh(taskId: string) {
    const [nextDag, nextEvidence, nextTraces] = await Promise.all([api.dag(taskId), api.evidence(taskId), api.traces(taskId)]);
    setDag(nextDag);
    setEvidence(nextEvidence);
    setTraces(nextTraces);
    await api.qa(taskId).then(setQa).catch(() => setQa(undefined));
    await api.report(taskId).then((nextReport) => {
      setReport(nextReport);
      setSelectedClaim(nextReport.claims[0]);
    }).catch(() => setReport(undefined));
  }

  async function run() {
    if (!task) return;
    setBusy(true);
    try {
      await api.runTask(task.task_id);
      await refresh(task.task_id);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen">
      <header className="border-b border-line bg-ink px-5 py-4 text-white">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">CIS 多 Agent 竞品分析系统</h1>
            <p className="text-sm text-slate-300">基于结构化 Schema、证据绑定、QA 打回和 Trace 回放的竞品分析 Demo</p>
          </div>
          {task && <div className="flex items-center gap-3 text-sm"><span>当前任务：{task.task_id}</span><Pill value={task.status} /></div>}
        </div>
      </header>
      <div className="p-4">
        <div className="mb-4 grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.65fr)]">
          <TaskForm onCreated={(created) => { setTask(created); setDag(undefined); setReport(undefined); setEvidence([]); setQa(undefined); setTraces([]); }} />
          <DemoGuide />
        </div>

        {task && (
          <div className="mb-4 flex flex-wrap items-center gap-3 rounded border border-line bg-white p-3 text-sm">
            <span className="font-semibold">当前任务：{task.task_id}</span>
            <Pill value={task.status} />
            <span className="text-slate-600">名称：{task.product_name}</span>
            <span className="text-slate-600">竞品：{task.competitors.join("、")}</span>
          </div>
        )}

        <button onClick={run} disabled={!task || busy} className="mb-4 inline-flex items-center gap-2 rounded bg-accent px-4 py-2 font-semibold text-white disabled:opacity-50">
          <Play size={16} /> 运行 Demo 工作流
        </button>
        <span className="ml-3 align-middle text-sm text-slate-600">执行 Mock Agent DAG，并生成 DAG、报告、证据、QA 和 Trace。</span>

        <div className="mt-4 space-y-4">
          <DagView dag={dag} />
          <KnowledgeView report={report} />
          <ReportView report={report} selectedClaim={selectedClaim} onSelect={setSelectedClaim} />
          <EvidencePanel claim={selectedClaim} evidence={evidence} />
          <QaPanel qa={qa} />
          <TraceViewer traces={traces} />
        </div>
      </div>
    </main>
  );
}
