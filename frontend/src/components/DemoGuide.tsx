import { Info } from "lucide-react";

export function DemoGuide() {
  return (
    <section className="rounded border border-line bg-white p-4">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">答辩演示指南</h2>
          <p className="mt-1 text-sm text-slate-600">推荐按下面路径展示评分点。</p>
        </div>
        <Info className="mt-1 text-accent" size={20} />
      </div>
      <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-700">
        <li>选择示例任务</li>
        <li>创建任务</li>
        <li>运行正常 workflow</li>
        <li>查看 DAG</li>
        <li>查看竞品知识</li>
        <li>点击 Claim 查看 Evidence</li>
        <li>查看 Trace</li>
        <li>切换 QA 失败模式</li>
        <li>展示 QA 如何打回对应 Agent</li>
      </ol>
      <div className="mt-4 rounded border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-900">
        当前版本使用 Mock 数据，重点展示多 Agent 协作、结构化 Schema、证据绑定、QA 打回闭环和 Trace 可观测性。后续可替换为真实 LLM、Web Collector 和 LangGraph。
      </div>
    </section>
  );
}
