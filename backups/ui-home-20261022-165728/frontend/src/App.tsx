import { useEffect, useRef, useState, type ChangeEvent } from "react";
import type { ProgressEvent, Project, ReviewJob, ReviewReport } from "./types";

const SAMPLE = `import os

def calculate(expression):
    return eval(expression)
`;

const severityName = { S0: "极严重", S1: "高", S2: "中", S3: "低" };
const evidenceName = { strong: "强证据", medium: "中等证据", weak: "弱证据" };
const dispositionName = {
  must_fix: "必须修复",
  suggested: "建议检查",
  uncertain: "待核验",
};
const statusName = {
  queued: "排队中", running: "审查中", completed: "已完成",
  failed: "失败", cancelled: "已取消",
};

export default function App() {
  const [user, setUser] = useState<{ username: string; is_admin: boolean } | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [projectName, setProjectName] = useState("");
  const [jobs, setJobs] = useState<ReviewJob[]>([]);
  const [job, setJob] = useState<ReviewJob | null>(null);
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const stream = useRef<EventSource | null>(null);
  const [filename, setFilename] = useState("example.py");
  const [source, setSource] = useState(SAMPLE);
  const [report, setReport] = useState<ReviewReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const lineNumbers = useRef<HTMLDivElement>(null);

  async function api<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await fetch(path, { credentials: "same-origin", ...options });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "请求失败");
    return data as T;
  }

  async function loadProjects() {
    const rows = await api<Project[]>("/api/projects");
    setProjects(rows);
    setProjectId((current) => current || rows[0]?.id || "");
  }

  useEffect(() => {
    api<{ username: string; is_admin: boolean }>("/api/me")
      .then((me) => { setUser(me); void loadProjects(); })
      .catch(() => undefined);
    return () => stream.current?.close();
  }, []);

  useEffect(() => {
    if (!projectId) return;
    api<ReviewJob[]>(`/api/projects/${projectId}/jobs`).then(setJobs).catch(() => setJobs([]));
  }, [projectId]);

  async function login() {
    setError("");
    try {
      const me = await api<{ username: string; is_admin: boolean }>("/api/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      setUser(me); setPassword(""); await loadProjects();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "登录失败"); }
  }

  async function addProject() {
    if (!projectName.trim()) return;
    try {
      const created = await api<Project>("/api/projects", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: projectName.trim() }),
      });
      setProjects((previous) => [...previous, created]);
      setProjectId(created.id); setProjectName(""); setError("");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "创建项目失败"); }
  }

  async function openJob(selected: ReviewJob) {
    stream.current?.close();
    setJob(selected); setReport(selected.report); setEvents([]);
    setEvents(await api<ProgressEvent[]>(`/api/jobs/${selected.id}/events`));
    if (["completed", "failed", "cancelled"].includes(selected.status)) return;
    const updates = new EventSource(`/api/jobs/${selected.id}/stream`);
    stream.current = updates;
    updates.addEventListener("progress", (event) => {
      const row = JSON.parse((event as MessageEvent).data) as ProgressEvent;
      setEvents((previous) => previous.some((item) => item.seq === row.seq) ? previous : [...previous, row]);
    });
    updates.addEventListener("done", async () => {
      updates.close(); setBusy(false);
      const finished = await api<ReviewJob>(`/api/jobs/${selected.id}`);
      setJob(finished); setReport(finished.report);
      if (finished.error) setError(finished.error);
      const rows = await api<ReviewJob[]>(`/api/projects/${finished.project_id}/jobs`);
      setJobs(rows);
    });
    updates.onerror = () => { updates.close(); setError("进度连接已断开，可从任务历史重新打开。"); setBusy(false); };
  }

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".py")) {
      setError("请选择 .py 文件。");
      return;
    }
    if (file.size > 100_000) { setError("文件超过 100 KB 上限。"); return; }
    let decoded: string;
    try { decoded = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer()); }
    catch { setError("文件不是有效的 UTF-8 编码。"); return; }
    setFilename(file.name);
    setSource(decoded.replace(/^\uFEFF/, ""));
    setReport(null);
    setError("");
  }

  async function submit() {
    if (!projectId) { setError("请先创建项目。"); return; }
    setError("");
    setBusy(true);
    setReport(null);
    try {
      const created = await api<ReviewJob>("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId, filename, source }),
      });
      setJobs((previous) => [created, ...previous]);
      await openJob(created);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法连接审查服务");
      setBusy(false);
    }
  }

  async function cancelJob() {
    if (!job || job.status !== "queued") return;
    try {
      const cancelled = await api<ReviewJob>(`/api/jobs/${job.id}/cancel`, { method: "POST" });
      stream.current?.close(); setJob(cancelled); setBusy(false);
      setJobs((previous) => previous.map((item) => item.id === cancelled.id ? cancelled : item));
      setEvents(await api<ProgressEvent[]>(`/api/jobs/${job.id}/events`));
    } catch (caught) { setError(caught instanceof Error ? caught.message : "取消失败"); }
  }

  const lines = source.split("\n");
  if (!user) return <main className="login-shell">
    <div className="login-card">
      <div className="brand"><span className="brandmark">C</span><span>CodeSentinel</span></div>
      <h1>登录审查工作台</h1>
      <p>账户由管理员创建。请使用分配的用户名和密码。</p>
      <label htmlFor="login-name">用户名</label>
      <input id="login-name" value={username} onChange={(event) => setUsername(event.target.value)} />
      <label htmlFor="login-password">密码</label>
      <input id="login-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void login(); }} />
      <button className="primary-button" onClick={login}>登录</button>
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  </main>;
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brandmark" aria-hidden="true">C</span>
          <span>CodeSentinel</span>
        </div>
        <span className="topbar-note">{user.username} · <button className="quiet-button" onClick={async () => { await api("/api/logout", { method: "POST" }); setUser(null); stream.current?.close(); }}>退出</button></span>
      </header>

      <main className="workspace">
        <div className="heading">
          <div>
            <h1>代码审查工作台</h1>
            <p>提交一个 Python 文件，查看发现项、证据和未覆盖范围。</p>
          </div>
          <span className="mode-label">单文件模式</span>
        </div>

        <div className="project-bar">
          <label htmlFor="project">项目</label>
          <select id="project" value={projectId} onChange={(event) => { setProjectId(event.target.value); setJob(null); setReport(null); setEvents([]); }}>
            {projects.length === 0 && <option value="">先创建项目</option>}
            {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select>
          <input aria-label="新项目名称" placeholder="新项目名称" value={projectName} onChange={(event) => setProjectName(event.target.value)} />
          <button className="quiet-button" onClick={addProject}>创建项目</button>
        </div>

        <div className="columns">
          <section className="source-panel" aria-labelledby="source-heading">
            <div className="panel-header">
              <div>
                <h2 id="source-heading">待审查源码</h2>
                <p>仅分析文本，不执行源代码。</p>
              </div>
              <button className="quiet-button" onClick={() => fileInput.current?.click()}>
                选择 .py 文件
              </button>
              <input ref={fileInput} className="sr-only" type="file" accept=".py,text/x-python" onChange={onFile} />
            </div>
            <label className="file-label" htmlFor="filename">文件名</label>
            <input id="filename" className="filename-input" value={filename}
              onChange={(event) => setFilename(event.target.value)} />
            <div className="editor-wrap">
              <div className="line-numbers" ref={lineNumbers} aria-hidden="true">
                {lines.map((_, index) => <span key={index}>{index + 1}</span>)}
              </div>
              <textarea aria-label="Python 源代码" spellCheck={false} value={source}
                onScroll={(event) => {
                  if (lineNumbers.current) lineNumbers.current.scrollTop = event.currentTarget.scrollTop;
                }}
                onChange={(event) => { setSource(event.target.value); setReport(null); }} />
            </div>
            <div className="source-footer">
              <span>{lines.length} 行 · {new Blob([source]).size.toLocaleString()} 字节</span>
              <button className="primary-button" disabled={busy || !source.trim() || !projectId} onClick={submit}>
                {busy ? "审查进行中…" : "开始审查"}
              </button>
            </div>
            {error && <p className="error" role="alert">{error}</p>}
          </section>

          <section className="report-panel" aria-labelledby="report-heading">
            <div className="panel-header">
              <div>
                <h2 id="report-heading">审查报告</h2>
                <p>{report ? `规则版本 ${report.rule_version}` : "审查完成后显示结果"}</p>
              </div>
              {report && <span className={`decision ${report.decision}`}>
                {report.decision === "pass" ? "未发现问题" : report.decision === "request_changes" ? "建议修改" : "需要关注"}
              </span>}
            </div>

            <div className="job-history">
              <strong>最近任务</strong>
              {jobs.map((item) => <button key={item.id} className="quiet-button" onClick={() => void openJob(item)}>{item.filename} · {statusName[item.status]}</button>)}
            </div>
            {job && <div className="progress-list" aria-live="polite">
              <strong>任务状态：{statusName[job.status]}</strong>
              {job.status === "queued" && <button className="quiet-button" onClick={cancelJob}>取消排队任务</button>}
              {events.map((item) => <p key={item.seq}>{item.seq}. {item.detail}</p>)}
            </div>}

            {!report && !busy && <div className="empty-state">
              <div className="empty-graphic" aria-hidden="true"><span /><span /><span /></div>
              <h3>准备好检查代码</h3>
              <p>左侧粘贴源码或选择文件，然后开始审查。</p>
            </div>}
            {busy && <div className="empty-state" role="status">
              <div className="loading-bar" aria-hidden="true" />
              <h3>正在检查</h3>
              <p>工具分析和模型请求可能需要几十秒。</p>
            </div>}
            {report && <div className="report-content">
              <div className="report-summary">
                <strong>{report.findings.length} 项发现</strong>
                <span>{new Date(report.created_at).toLocaleString("zh-CN")}</span>
              </div>
              {report.source_hash && <p className="report-meta">源码 SHA256：{report.source_hash} · 构建 {report.build_version || "未知"} · 模型 {report.model_version || "未配置"}</p>}
              {report.omitted_ranges?.length ? <p className="report-meta">模型上下文省略原始行：{report.omitted_ranges.map(([start, end]) => `${start}-${end}`).join("、")}</p> : null}
              {report.findings.length === 0 && <p className="no-findings">当前检查没有产生发现项。请同时查看下方覆盖范围。</p>}
              <div className="findings">
                {report.findings.map((finding) => (
                  <article className="finding" key={finding.id}>
                    <div className="finding-top">
                      <span className="location">{report.filename}:{finding.line}</span>
                      <span className="severity">{finding.severity} · {severityName[finding.severity]}</span>
                    </div>
                    <h3>{finding.title}</h3>
                    <p>{finding.explanation}</p>
                    {finding.trigger_path && <p className="trigger-path"><strong>静态触发路径：</strong>{finding.trigger_path.replace(/^静态可能路径：/, "")}</p>}
                    <div className="tags">
                      <span>{dispositionName[finding.disposition]}</span>
                      <span>{evidenceName[finding.evidence_level]}</span>
                      <span>{finding.rule_id}</span>
                    </div>
                    <details>
                      <summary>查看证据与建议</summary>
                      {finding.evidence.map((item, index) =>
                        <p key={index}><strong>{item.source === "Architect" ? "架构师" : item.source}：</strong>{item.detail}</p>)}
                      {finding.verification && <p><strong>核验：</strong>{finding.verification.reason}</p>}
                      <p><strong>建议：</strong>{finding.suggestion}</p>
                    </details>
                  </article>
                ))}
              </div>
              <div className="coverage">
                <h3>审查覆盖</h3>
                <p>已完成：{report.coverage.completed.join("、") || "无"}</p>
                {report.coverage.gaps.length > 0 && <>
                  <h4>未覆盖或不可用</h4>
                  <ul>{report.coverage.gaps.map((gap, index) => <li key={index}>{gap}</li>)}</ul>
                </>}
              </div>
            </div>}
          </section>
        </div>
      </main>
    </div>
  );
}
