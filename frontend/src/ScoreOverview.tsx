import type { PointerEvent } from "react";
import type { FindingFeedback, ReviewJob } from "./types";
import "./ScoreOverview.css";

const severityLabel = { S0: "极严重", S1: "高风险", S2: "中风险", S3: "低风险" };
const severityWeight = { S0: 40, S1: 20, S2: 8, S3: 3 };

type Props = { job: ReviewJob; feedback: Record<string, FindingFeedback>;
  onDetails: (line?: number, filename?: string | null) => void; onBack: () => void };

function pointLight(event: PointerEvent<HTMLElement>) {
  if (event.pointerType !== "mouse") return;
  const rect = event.currentTarget.getBoundingClientRect();
  event.currentTarget.style.setProperty("--light-x", `${event.clientX - rect.left}px`);
  event.currentTarget.style.setProperty("--light-y", `${event.clientY - rect.top}px`);
}

export default function ScoreOverview({ job, feedback, onDetails, onBack }: Props) {
  const report = job.report;
  const score = job.score;
  if (!report || !score) return null;
  const counts = { S0: 0, S1: 0, S2: 0, S3: 0 };
  report.findings.forEach((finding) => { counts[finding.severity] += 1; });
  const priority = [...report.findings]
    .filter((finding) => feedback[finding.id]?.status !== "false_positive" &&
      (feedback[finding.id]?.status === "confirmed" ||
        (finding.disposition !== "uncertain" && finding.evidence_level !== "weak")))
    .sort((a, b) => severityWeight[b.severity] - severityWeight[a.severity])
    .slice(0, 3);
  const status = score.value >= 85 ? "较稳健" : score.value >= 60 ? "建议修复" : "优先处理";

  return <main className="score-view">
    <div className="score-back-row"><button className="score-back" onClick={onBack}>← 返回首页</button></div>
    <div className="score-page-heading">
      <div><p className="score-context">审查已完成 · {new Date(job.created_at).toLocaleString("zh-CN")}</p>
        <h1>{job.filename === "project.codesentinel-bundle" ? "项目审查概览" : job.filename}</h1>
        <p>先看风险概况，再进入代码和逐条证据。</p></div>
    </div>
    <div className="score-bento">
      <section className="score-tile score-main" onPointerMove={pointLight} aria-label={`审查估分 ${score.value} 分`}>
        <div className="score-tile-content">
          <div className="score-tile-heading"><span>审查估分</span><span className="score-chip">{status}</span></div>
          <div className="score-number"><strong>{score.value}</strong><span>/ 100</span></div>
          <div className="score-meter" role="img" aria-label={`估分 ${score.value} 分，共扣 ${score.deduction} 分`}>
            <span style={{ width: `${score.value}%` }} /></div>
          <p>按本次有中等或强证据的问题扣分，共扣 {score.deduction} 分。分数只反映本次审查范围。</p>
          <button className="score-primary" onClick={() => onDetails()}>查看完整审查详情 <span aria-hidden="true">↗</span></button>
        </div>
      </section>
      <section className="score-tile score-risk" onPointerMove={pointLight}>
        <div className="score-tile-content"><div className="score-tile-heading"><span>发现的问题</span><span>本次报告</span></div>
          <strong className="score-stat">{report.findings.length}<small>项</small></strong>
          <div className="score-severity-list">
            {(["S0", "S1", "S2", "S3"] as const).map((level) => <span key={level} className={counts[level] ? "has-findings" : ""}>{level} {counts[level]}</span>)}
          </div>
        </div>
      </section>
      <section className="score-tile score-pending" onPointerMove={pointLight}>
        <div className="score-tile-content"><div className="score-tile-heading"><span>需要人工核验</span><span>未计入扣分</span></div>
          <strong className="score-stat">{score.pending_findings}<small>项</small></strong>
          <p>弱证据或结论不确定的发现单独列出，进入详情可查看证据并记录判断。</p>
        </div>
      </section>
      <section className="score-tile score-priority" onPointerMove={pointLight}>
        <div className="score-tile-content"><div className="score-tile-heading"><span>优先处理</span><span>按严重程度排序</span></div>
          {priority.length ? <ol>{priority.map((finding) => <li key={finding.id}>
            <button onClick={() => onDetails(finding.line, finding.filename)}><span className="score-finding-level">{finding.severity} · {severityLabel[finding.severity]}</span>
              <strong>{finding.title}</strong><span className="score-finding-location">{finding.filename ? `${finding.filename} · ` : ""}第 {finding.line} 行 <span aria-hidden="true">↗</span></span></button>
          </li>)}</ol> : <p className="score-empty">本次没有可直接扣分的发现。仍请查看覆盖范围和待核验项。</p>}
        </div>
      </section>
      <section className="score-tile score-coverage" onPointerMove={pointLight}>
        <div className="score-tile-content"><div className="score-tile-heading"><span>检查覆盖</span><span>规则 {report.rule_version}</span></div>
          <strong className="score-stat">{report.coverage.completed.length}<small>项检查完成</small></strong>
          <p>{report.coverage.gaps.length ? `${report.coverage.gaps.length} 项未覆盖或不可用；详情中列出具体原因。` : "报告中没有记录未覆盖项。"}</p>
          <p className="score-formula">扣分规则：S0 −40 · S1 −20 · S2 −8 · S3 −3；最低 0 分。误报反馈不计分。</p>
        </div>
      </section>
    </div>
  </main>;
}
