import { Play } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "./api/client";
import { DagView } from "./components/DagView";
import { DemoGuide } from "./components/DemoGuide";
import { KnowledgeView } from "./components/KnowledgeView";
import { QaPanel } from "./components/QaPanel";
import { ReportView } from "./components/ReportView";
import { TaskForm } from "./components/TaskForm";
import { TaskList } from "./components/TaskList";
import { TraceViewer } from "./components/TraceViewer";
import type { Claim, Dag, DemoMode, Evidence, LlmStatus, QaResult, Report, Task, TraceRecord, WriterDiagnostics } from "./types";
import { Pill } from "./types";

export default function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [task, setTask] = useState<Task>();
  const [dag, setDag] = useState<Dag>();
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [qa, setQa] = useState<QaResult>();
  const [report, setReport] = useState<Report>();
  const [traces, setTraces] = useState<TraceRecord[]>([]);
  const [selectedClaim, setSelectedClaim] = useState<Claim>();
  const [busy, setBusy] = useState(false);
  const [demoMode, setDemoMode] = useState<DemoMode>("normal");
  const [autoRework, setAutoRework] = useState(false);
  const [writerMode, setWriterMode] = useState<"mock" | "llm">("mock");
  const [llmStatus, setLlmStatus] = useState<LlmStatus>();
  const [llmTesting, setLlmTesting] = useState(false);

  useEffect(() => {
    loadTasks();
    loadLlmStatus();
  }, []);

  async function loadLlmStatus() {
    await api.llmStatus().then(setLlmStatus).catch(() => setLlmStatus(undefined));
  }

  async function loadTasks(selectTaskId?: string) {
    const nextTasks = await api.listTasks();
    setTasks(nextTasks);
    const nextTask = nextTasks.find((item) => item.task_id === selectTaskId) ?? nextTasks[0];
    if (nextTask) {
      setTask(nextTask);
      await refresh(nextTask.task_id);
    }
  }

  async function refresh(taskId: string) {
    const [nextDag, nextEvidence, nextTraces] = await Promise.all([api.dag(taskId), api.evidence(taskId), api.traces(taskId)]);
    setDag(nextDag);
    setEvidence(nextEvidence);
    setTraces(nextTraces);
    await api.qa(taskId).then(setQa).catch(() => setQa(undefined));
    await api.report(taskId).then((nextReport) => {
      setReport(nextReport);
      setSelectedClaim(nextReport.claims[0]);
    }).catch(() => {
      setReport(undefined);
      setSelectedClaim(undefined);
    });
  }

  async function selectTask(nextTask: Task) {
    setTask(nextTask);
    setDag(undefined);
    setEvidence([]);
    setQa(undefined);
    setReport(undefined);
    setTraces([]);
    setSelectedClaim(undefined);
    await refresh(nextTask.task_id);
  }

  async function handleCreated(created: Task) {
    await loadTasks(created.task_id);
  }

  async function run() {
    if (!task) return;
    setBusy(true);
    try {
      const result = await api.runTask(task.task_id, demoMode, autoRework, writerMode) as { report?: Report | null };
      await loadTasks(task.task_id);
      if (!result.report) {
        setReport(undefined);
        setSelectedClaim(undefined);
      }
      if (demoMode === "qa_missing_evidence") {
        setEvidence([]);
      }
    } finally {
      setBusy(false);
    }
  }

  async function testLlm() {
    setLlmTesting(true);
    try {
      setLlmStatus(await api.testLlm());
    } finally {
      setLlmTesting(false);
    }
  }

  const writerDiagnostics = report?.json_report.writer_diagnostics as WriterDiagnostics | undefined;
  const llmStatusLabel = !llmStatus
    ? "LLM 状态未知"
    : !llmStatus.api_key_configured
      ? "未配置 API Key"
      : llmStatus.last_check_status === "success"
        ? "测试成功"
        : llmStatus.last_check_status === "failed"
          ? "测试失败"
          : "已配置，未测试";
  const writerDiagnosticMessage = writerDiagnostics
    ? writerDiagnostics.fallback_used
      ? `已选择 ${writerDiagnostics.writer_mode_requested ?? writerMode} ReportWriter，但本次使用 ${writerDiagnostics.writer_mode_used ?? "mock"}。原因：${writerDiagnostics.llm_fallback_reason ?? writerDiagnostics.llm_error_message ?? "未知"}`
      : writerDiagnostics.writer_mode_used === "llm"
        ? `LLM ReportWriter 调用成功，耗时 ${writerDiagnostics.llm_elapsed_time_ms ?? 0}ms，模型：${writerDiagnostics.llm_model ?? "未记录"}。`
        : `本次使用 ${writerDiagnostics.writer_mode_used ?? "mock"} ReportWriter。`
    : undefined;

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
        <div className="mb-4 grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.65fr)]">
          <TaskForm onCreated={handleCreated} />
          <DemoGuide />
        </div>

        <div className="mb-4">
          <TaskList tasks={tasks} currentTaskId={task?.task_id} onSelect={selectTask} />
        </div>

        {task && (
          <div className="mb-4 flex flex-wrap items-center gap-3 rounded border border-line bg-white p-3 text-sm">
            <span className="font-semibold">当前任务：{task.task_id}</span>
            <Pill value={task.status} />
            <span className="text-slate-600">名称：{task.product_name}</span>
            <span className="text-slate-600">竞品：{task.competitors.join("、")}</span>
          </div>
        )}

        <div className="mb-4 flex flex-wrap items-center gap-3">
          <select
            className="rounded border border-line bg-white px-3 py-2 text-sm"
            value={demoMode}
            onChange={(event) => setDemoMode(event.target.value as DemoMode)}
          >
            <option value="normal">正常流程</option>
            <option value="qa_missing_evidence">QA 失败：缺少证据</option>
            <option value="qa_invalid_extraction">QA 失败：抽取冲突</option>
            <option value="qa_bad_report">QA 失败：报告格式错误</option>
          </select>
          <select
            className="rounded border border-line bg-white px-3 py-2 text-sm"
            value={writerMode}
            onChange={(event) => setWriterMode(event.target.value as "mock" | "llm")}
          >
            <option value="mock">Mock ReportWriter</option>
            <option value="llm">LLM ReportWriter</option>
          </select>
          <span className="rounded border border-line bg-white px-3 py-2 text-sm">
            LLM：{llmStatusLabel}
          </span>
          <button
            type="button"
            onClick={testLlm}
            disabled={llmTesting}
            className="rounded border border-line bg-white px-3 py-2 text-sm font-semibold disabled:opacity-50"
          >
            {llmTesting ? "测试中..." : "测试 LLM 连接"}
          </button>
          <button onClick={run} disabled={!task || busy} className="inline-flex items-center gap-2 rounded bg-accent px-4 py-2 font-semibold text-white disabled:opacity-50">
            <Play size={16} /> 运行 Demo 工作流
          </button>
          <label className="inline-flex items-center gap-2 rounded border border-line bg-white px-3 py-2 text-sm">
            <input
              type="checkbox"
              checked={autoRework}
              onChange={(event) => setAutoRework(event.target.checked)}
            />
            auto_rework=true
          </label>
          <span className="text-sm text-slate-600">执行所选 Mock Agent DAG，并生成 DAG、报告、证据、QA 和 Trace。</span>
        </div>

        {(llmStatus || writerDiagnosticMessage) && (
          <div className="mb-4 rounded border border-line bg-white p-3 text-sm">
            <div className="flex flex-wrap gap-x-5 gap-y-2">
              <span>LLM Provider：{llmStatus?.llm_provider ?? "未读取"}</span>
              <span>模型：{llmStatus?.llm_model ?? "未读取"}</span>
              <span>Base URL：{llmStatus?.base_url_configured ? "已配置" : "未配置"}</span>
              <span>API Key：{llmStatus?.api_key_configured ? "已配置" : "未配置"}</span>
              <span>状态：{llmStatusLabel}</span>
            </div>
            {llmStatus?.last_error && <div className="mt-2 text-danger">测试错误：{llmStatus.last_error}</div>}
            {writerDiagnostics && (
              <div className="mt-2 grid gap-2 md:grid-cols-4">
                <span>requested：{writerDiagnostics.writer_mode_requested ?? "-"}</span>
                <span>used：{writerDiagnostics.writer_mode_used ?? "-"}</span>
                <span>fallback：{writerDiagnostics.fallback_used ? "true" : "false"}</span>
                <span>llm_call：{writerDiagnostics.llm_call_attempted ? (writerDiagnostics.llm_call_success ? "success" : "failed") : "not_attempted"}</span>
              </div>
            )}
            {writerDiagnosticMessage && (
              <div className={`mt-2 rounded border px-3 py-2 ${writerDiagnostics?.fallback_used ? "border-amber-300 bg-amber-50 text-warning" : "border-green-300 bg-green-50 text-success"}`}>
                {writerDiagnosticMessage}
              </div>
            )}
          </div>
        )}

        <div className="space-y-4">
          <DagView dag={dag} traces={traces} qaRouteTo={qa?.route_to} />
          <KnowledgeView report={report} />
          <ReportView report={report} evidence={evidence} selectedClaim={selectedClaim} onSelect={setSelectedClaim} />
          <QaPanel qa={qa} />
          <TraceViewer traces={traces} />
        </div>
      </div>
    </main>
  );
}
