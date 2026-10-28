import { useEffect, useRef, useState, type ChangeEvent } from "react";
import type { ProgressEvent, Project, ReviewJob, ReviewReport } from "./types";

type LanguageMode = "auto" | "python" | "javascript" | "typescript" | "java" | "go" | "c"
  | "cpp" | "csharp" | "rust" | "php" | "ruby" | "kotlin" | "swift"
  | "sql" | "xml" | "yaml" | "properties" | "custom";

const severityName = { S0: "极严重", S1: "高", S2: "中", S3: "低" };
const evidenceName = { strong: "强证据", medium: "中等证据", weak: "弱证据" };
const dispositionName = { must_fix: "必须修复", suggested: "建议检查", uncertain: "待核验" };
const statusName: Record<ReviewJob["status"], string> = {
  queued: "排队中", running: "审查中", completed: "已完成", failed: "失败", cancelled: "已取消",
};
const languageName: Record<string, string> = {
  python: "Python", javascript: "JavaScript", typescript: "TypeScript",
  java: "Java", go: "Go", c: "C", cpp: "C++", csharp: "C#", rust: "Rust",
  php: "PHP", ruby: "Ruby", kotlin: "Kotlin", swift: "Swift", sql: "SQL",
  xml: "XML / Maven", yaml: "YAML / Spring Boot", properties: "Properties / Spring Boot",
};
const languages = [
  { id: "python", label: "Python" }, { id: "java", label: "Java" },
  { id: "javascript", label: "JavaScript" }, { id: "typescript", label: "TypeScript" },
  { id: "sql", label: "SQL" }, { id: "xml", label: "XML / Maven" },
  { id: "yaml", label: "YAML / Spring Boot" }, { id: "properties", label: "Properties / Spring Boot" },
  { id: "go", label: "Go" }, { id: "c", label: "C" }, { id: "cpp", label: "C++" },
  { id: "csharp", label: "C#" }, { id: "rust", label: "Rust" },
  { id: "php", label: "PHP" }, { id: "ruby", label: "Ruby" },
  { id: "kotlin", label: "Kotlin" }, { id: "swift", label: "Swift" },
  { id: "scala", label: "Scala" },
  { id: "dart", label: "Dart" }, { id: "r", label: "R" },
  { id: "lua", label: "Lua" }, { id: "perl", label: "Perl" },
  { id: "shell", label: "Shell" }, { id: "powershell", label: "PowerShell" },
  { id: "html", label: "HTML" },
  { id: "css", label: "CSS" }, { id: "json", label: "JSON" },
];
const supportedLanguages = new Set(["python", "javascript", "typescript", "java", "go", "c",
  "cpp", "csharp", "rust", "php", "ruby", "kotlin", "swift", "sql", "xml", "yaml", "properties"]);
const fileLanguage = { python: ".py", javascript: ".js", typescript: ".ts", java: ".java",
  go: ".go", c: ".c", cpp: ".cpp", csharp: ".cs", rust: ".rs", php: ".php",
  ruby: ".rb", kotlin: ".kt", swift: ".swift", sql: ".sql", xml: ".xml",
  yaml: ".yml", properties: ".properties" };

function detectLanguage(source: string, filename: string): string | null {
  const code = source.trim();
  const extension = filename.toLowerCase().split(".").pop();
  const byExtension = ({ py: "python", js: "javascript", jsx: "javascript", ts: "typescript",
    tsx: "typescript", java: "java", go: "go", c: "c", h: "c", cpp: "cpp", cc: "cpp",
    cxx: "cpp", hpp: "cpp", cs: "csharp", rs: "rust", php: "php", rb: "ruby",
    kt: "kotlin", kts: "kotlin", swift: "swift", sql: "sql", xml: "xml",
    yml: "yaml", yaml: "yaml", properties: "properties" } as Record<string, string>)[extension || ""];
  if (byExtension) return byExtension;
  if (/\b(interface\s+\w+|type\s+\w+\s*=|:\s*(string|number|boolean)\b)/.test(code)) return "typescript";
  if (/\b(const|let|function|export\s+default|import\s+.+\s+from)\b|=>|console\.log\s*\(/.test(code)) return "javascript";
  if (/\bpublic\s+(static\s+)?class\b|System\.out\.println/.test(code)) return "java";
  if (/\bpackage\s+main\b|\bfunc\s+main\s*\(/.test(code)) return "go";
  if (/\bfn\s+main\s*\(|\blet\s+mut\b/.test(code)) return "rust";
  if (/\busing\s+System\b|\bnamespace\s+\w+\s*\{/.test(code)) return "csharp";
  if (/#include\s*<iostream>|\bstd::|\bcout\s*<</.test(code)) return "cpp";
  if (/#include\s*<stdio\.h>|\bprintf\s*\(/.test(code)) return "c";
  if (/^\s*<\?php\b/.test(code)) return "php";
  if (/\bfun\s+main\s*\(|\bval\s+\w+\s*=/.test(code)) return "kotlin";
  if (/\bimport\s+Foundation\b|\bfunc\s+main\s*\(|\bguard\s+let\b/.test(code)) return "swift";
  if (/\bputs\s+['"]|\bend\s*$/m.test(code)) return "ruby";
  if (/^\s*(?:<\?xml\b|<project\b|<beans\b)/.test(code)) return "xml";
  if (/^\s*(?:spring|management|server)\s*:/m.test(code)) return "yaml";
  if (/^\s*(?:spring\.|management\.|server\.port\s*=)/m.test(code)) return "properties";
  if (/\b(SELECT|INSERT INTO|CREATE TABLE)\b/i.test(code)) return "sql";
  if (/\bdef\s+\w+\s*\(|\bfrom\s+\w+\s+import\b|\bimport\s+\w+|\bprint\s*\(|\bif\s+__name__\s*==/.test(code)) return "python";
  return null;
}

function MenuIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
  </svg>;
}

function BrandMark() {
  return <span className="brandmark" aria-hidden="true"><svg viewBox="0 0 28 28" fill="none">
    <path d="M10 6H6v4m12-4h4v4M6 18v4h4m12-4v4h-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    <path d="m11 14 2 2 4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg></span>;
}

export default function App() {
  const [user, setUser] = useState<{ username: string; is_admin: boolean } | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [projectName, setProjectName] = useState("");
  const [creatingProject, setCreatingProject] = useState(false);
  const [jobs, setJobs] = useState<ReviewJob[]>([]);
  const [job, setJob] = useState<ReviewJob | null>(null);
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [report, setReport] = useState<ReviewReport | null>(null);
  const [view, setView] = useState<"home" | "review">("home");
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth > 900);
  const [draftSource, setDraftSource] = useState("");
  const [draftFilename, setDraftFilename] = useState("");
  const [languageMode, setLanguageMode] = useState<LanguageMode>("auto");
  const [customLanguage, setCustomLanguage] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeLine, setActiveLine] = useState<number | null>(null);
  const [error, setError] = useState("");
  const stream = useRef<EventSource | null>(null);
  const activeJobId = useRef("");
  const fileInput = useRef<HTMLInputElement>(null);
  const codeViewer = useRef<HTMLDivElement>(null);

  const detectedLanguage = detectLanguage(draftSource, draftFilename);
  const customChoice = languages.find((item) => item.label.toLowerCase() === customLanguage.trim().toLowerCase());
  const language = languageMode === "auto" ? detectedLanguage
    : languageMode === "custom" ? customChoice?.id || null : languageMode;
  const languageLabel = language ? languageName[language] || customChoice?.label || language : "尚未识别";

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
    if (!projectId) { setJobs([]); return; }
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

  async function logout() {
    try { await api("/api/logout", { method: "POST" }); }
    catch { setError("退出失败，请稍后重试。"); return; }
    stream.current?.close(); setUser(null); setJob(null); setReport(null); setView("home");
  }

  async function addProject() {
    if (!projectName.trim()) return;
    try {
      const created = await api<Project>("/api/projects", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: projectName.trim() }),
      });
      setProjects((previous) => [...previous, created]);
      setProjectId(created.id); setProjectName(""); setCreatingProject(false); setError("");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "创建项目失败"); }
  }

  async function openJob(selected: ReviewJob, submittedSource?: string) {
    stream.current?.close();
    activeJobId.current = selected.id;
    setJob(selected); setReport(selected.report); setEvents([]);
    setSelectedSource(submittedSource ?? null); setView("review"); setError("");
    setActiveLine(null);
    if (window.innerWidth <= 900) setSidebarOpen(false);
    try {
      const [saved, history] = await Promise.all([
        api<{ filename: string; source: string }>(`/api/jobs/${selected.id}/source`),
        api<ProgressEvent[]>(`/api/jobs/${selected.id}/events`),
      ]);
      if (activeJobId.current !== selected.id) return;
      setSelectedSource(saved.source); setEvents(history);
      if (["completed", "failed", "cancelled"].includes(selected.status)) { setBusy(false); return; }
      const updates = new EventSource(`/api/jobs/${selected.id}/stream`);
      stream.current = updates;
      updates.addEventListener("progress", (event) => {
        const row = JSON.parse((event as MessageEvent).data) as ProgressEvent;
        setEvents((previous) => previous.some((item) => item.seq === row.seq) ? previous : [...previous, row]);
      });
      updates.addEventListener("done", async () => {
        updates.close(); setBusy(false);
        if (activeJobId.current !== selected.id) return;
        const finished = await api<ReviewJob>(`/api/jobs/${selected.id}`);
        setJob(finished); setReport(finished.report);
        if (finished.error) setError(finished.error);
        setJobs(await api<ReviewJob[]>(`/api/projects/${finished.project_id}/jobs`));
      });
      updates.onerror = () => { updates.close(); setBusy(false); setError("进度连接已断开，可从历史记录重新打开。"); };
    } catch (caught) {
      setBusy(false); setError(caught instanceof Error ? caught.message : "无法读取这条审查记录");
    }
  }

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 100_000) { setError("文件超过 100 KB 上限。"); return; }
    try {
      const decoded = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer());
      setDraftSource(decoded.replace(/^\uFEFF/, "")); setDraftFilename(file.name);
      setLanguageMode("auto"); setError("");
    } catch { setError("文件不是有效的 UTF-8 编码。"); }
    event.target.value = "";
  }

  async function submit() {
    if (!draftSource.trim()) { setError("请先输入代码。"); return; }
    if (!language) { setError(languageMode === "custom" ? "请从搜索列表中选择编程语言。" : "无法可靠识别语言，请在下拉框中选择。"); return; }
    if (!supportedLanguages.has(language)) {
      setError(`识别为 ${languageLabel}。当前支持列表中的代码、SQL 和 Spring Boot 配置文件，暂不能提交该类型。`); return;
    }
    if (!projectId) { setSidebarOpen(true); setError("请先在左侧创建项目。"); return; }
    setError(""); setBusy(true);
    try {
      const created = await api<ReviewJob>("/api/jobs", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId,
          filename: detectLanguage("", draftFilename) === language ? draftFilename : `snippet${fileLanguage[language as keyof typeof fileLanguage]}`,
          source: draftSource, language }),
      });
      setJobs((previous) => [created, ...previous]);
      await openJob(created, draftSource);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法连接审查服务"); setBusy(false);
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

  function newReview() {
    activeJobId.current = ""; stream.current?.close();
    setView("home"); setJob(null); setReport(null); setSelectedSource(null);
    setDraftSource(""); setDraftFilename(""); setLanguageMode("auto"); setCustomLanguage("");
    setEvents([]); setBusy(false); setError("");
    setActiveLine(null);
    if (window.innerWidth <= 900) setSidebarOpen(false);
  }

  function jumpToLine(line: number) {
    setActiveLine(line);
    const row = codeViewer.current?.querySelector<HTMLElement>(`[data-line="${line}"]`);
    row?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "center" });
    codeViewer.current?.focus({ preventScroll: true });
  }

  if (!user) return <main className="login-shell">
    <div className="login-card">
      <div className="brand"><BrandMark /><span>CodeSentinel</span></div>
      <h1>登录代码审查</h1>
      <p>输入账号后，开始检查你的代码。</p>
      <label htmlFor="login-name">用户名</label>
      <input id="login-name" value={username} onChange={(event) => setUsername(event.target.value)} />
      <label htmlFor="login-password">密码</label>
      <input id="login-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void login(); }} />
      <button className="primary-button" onClick={login}>登录</button>
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  </main>;

  return <div className={`app-shell ${sidebarOpen ? "sidebar-open" : "sidebar-closed"}`}>
    {sidebarOpen && <button className="sidebar-scrim" aria-label="关闭历史记录" onClick={() => setSidebarOpen(false)} />}
    <aside className="sidebar" aria-label="审查历史记录">
      <div className="sidebar-heading">
        <div className="brand"><BrandMark /><span>CodeSentinel</span></div>
        <button className="icon-button sidebar-close" aria-label="收起历史记录" onClick={() => setSidebarOpen(false)}><MenuIcon /></button>
      </div>
      <button className="new-review-button" onClick={newReview}>
        <span aria-hidden="true">＋</span> 新建审查
      </button>
      <div className="history-heading"><span>历史审查</span><span>{jobs.length}</span></div>
      <nav className="history-list" aria-label="最近审查任务">
        {jobs.length === 0 && <p className="history-empty">还没有审查记录。提交代码后会显示在这里。</p>}
        {jobs.map((item) => <button key={item.id}
          className={`history-item ${job?.id === item.id && view === "review" ? "is-active" : ""}`}
          onClick={() => void openJob(item)}>
          <span className="history-filename">{item.filename}</span>
          <span className="history-meta">{new Date(item.created_at).toLocaleDateString("zh-CN")} · {statusName[item.status]}</span>
        </button>)}
      </nav>
      <div className="sidebar-bottom">
        <label htmlFor="project">当前项目</label>
        <div className="project-row">
          <select id="project" value={projectId} onChange={(event) => {
            activeJobId.current = ""; stream.current?.close();
            setProjectId(event.target.value); setJob(null); setReport(null); setView("home");
          }}>
            {projects.length === 0 && <option value="">尚无项目</option>}
            {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select>
          <button className="icon-button" aria-label="创建项目" title="创建项目" onClick={() => setCreatingProject((open) => !open)}>＋</button>
        </div>
        {creatingProject && <div className="create-project">
          <input aria-label="新项目名称" placeholder="项目名称" value={projectName}
            onChange={(event) => setProjectName(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter") void addProject(); }} />
          <button onClick={addProject} disabled={!projectName.trim()}>创建</button>
        </div>}
      </div>
    </aside>

    <div className="main-area">
      <header className="topbar">
        <div className="topbar-left">
          <button className="icon-button" aria-label={sidebarOpen ? "收起历史记录" : "展开历史记录"}
            aria-expanded={sidebarOpen} onClick={() => setSidebarOpen((open) => !open)}><MenuIcon /></button>
          <span className="topbar-title">CodeSentinel</span>
        </div>
        <div className="account"><span>{user.username}</span><button onClick={() => void logout()}>退出</button></div>
      </header>

      {view === "home" ? <main className="home-view">
        <div className="home-content">
          <h1>有什么代码需要检查？</h1>
          <div className={`composer ${busy ? "is-scanning" : ""}`} aria-busy={busy}>
            <textarea aria-label="输入要审查的代码" placeholder="在这里粘贴代码…" spellCheck={false}
              value={draftSource} onChange={(event) => { setDraftSource(event.target.value); setError(""); }} />
            {draftFilename && <div className="attached-file">{draftFilename}<button aria-label="移除文件名" onClick={() => setDraftFilename("")}>×</button></div>}
            <div className="composer-bottom">
              <div className="composer-controls">
                <button className="upload-button" onClick={() => fileInput.current?.click()} title="上传代码文件">上传文件</button>
                <input ref={fileInput} className="sr-only" type="file" accept=".py,.js,.jsx,.ts,.tsx,.java,.go,.c,.h,.cpp,.cc,.cxx,.hpp,.cs,.rs,.php,.rb,.kt,.kts,.swift,.sql,.xml,.yml,.yaml,.properties,.html,.css,.json,.txt" onChange={onFile} />
                <label className="sr-only" htmlFor="language">编程语言</label>
                <select id="language" value={languageMode} onChange={(event) => { setLanguageMode(event.target.value as LanguageMode); setError(""); }}>
                  <option value="auto">自动识别</option>
                  <option value="python">Python</option>
                  <option value="java">Java</option>
                  <option value="javascript">JavaScript</option>
                  <option value="typescript">TypeScript</option>
                  <option value="sql">SQL</option>
                  <option value="xml">XML / Maven (pom.xml)</option>
                  <option value="yaml">YAML / Spring Boot</option>
                  <option value="properties">Properties / Spring Boot</option>
                  <option value="go">Go</option>
                  <option value="c">C</option>
                  <option value="cpp">C++</option>
                  <option value="csharp">C#</option>
                  <option value="rust">Rust</option>
                  <option value="php">PHP</option>
                  <option value="ruby">Ruby</option>
                  <option value="kotlin">Kotlin</option>
                  <option value="swift">Swift</option>
                  <option value="custom">自定义选择…</option>
                </select>
                {languageMode === "custom" && <>
                  <input className="custom-language" type="search" list="language-list" aria-label="搜索编程语言"
                    placeholder="搜索并选择语言" value={customLanguage}
                    onChange={(event) => { setCustomLanguage(event.target.value); setError(""); }} />
                  <datalist id="language-list">{languages.map((item) => <option key={item.id} value={item.label}
                    label={supportedLanguages.has(item.id) ? "支持审查" : "暂不支持"} />)}</datalist>
                </>}
              </div>
              <button className="primary-button submit-button" disabled={busy || !draftSource.trim()}
                onClick={() => void submit()}>{busy ? "提交中…" : "开始审查"}</button>
            </div>
          </div>
          <div className="composer-hint" aria-live="polite">
            {languageMode === "auto" && draftSource.trim() ? `自动识别：${languageLabel}` : languageMode !== "auto" ? `当前选择：${languageLabel}` : "支持 13 种编程语言，以及 SQL、XML、YAML、Properties"}
            {draftSource.trim() && <span>{draftSource.split("\n").length} 行 · {new Blob([draftSource]).size.toLocaleString()} 字节</span>}
          </div>
          {error && <p className="error" role="alert">{error}</p>}
        </div>
      </main> : <main className="review-view">
        <div className="review-heading">
          <div><span className="review-overline">审查记录</span><h1>{job?.filename || "代码审查"}</h1>
            <p>{job ? `${new Date(job.created_at).toLocaleString("zh-CN")} · ${statusName[job.status]}` : ""}</p></div>
          <button className="secondary-button" onClick={newReview}>新建审查</button>
        </div>
        {error && <p className="error review-error" role="alert">{error}</p>}
        <div className="review-grid">
          <section className="code-pane" aria-labelledby="code-heading">
            <div className="pane-heading"><div><h2 id="code-heading">提交的代码</h2><p>审查时保存的原文 · 只读</p></div>
              <span className="pane-count">{selectedSource?.split("\n").length || 0} 行</span></div>
            <div className="code-viewer" ref={codeViewer} role="region" aria-label="提交的代码" tabIndex={0}>
              {selectedSource === null ? <p className="loading-copy">正在读取代码…</p>
                : selectedSource.split("\n").map((line, index) => <div className={`code-line ${activeLine === index + 1 ? "is-target" : ""}`} data-line={index + 1} key={index}>
                    <span className="code-number">{index + 1}</span><span className="code-text">{line || " "}</span>
                  </div>)}
            </div>
          </section>

          <section className="report-pane" aria-labelledby="report-heading">
            <div className="pane-heading"><div><h2 id="report-heading">审查结果与建议</h2>
              <p>{report ? `规则版本 ${report.rule_version}` : "完成后在这里查看报告"}</p></div>
              {report && <span className={`decision ${report.decision}`}>
                {report.decision === "pass" ? "未发现问题" : report.decision === "request_changes" ? "建议修改" : "需要关注"}
              </span>}
            </div>
            {job && !report && <div className="progress-list" role="status" aria-live="polite">
              {job.status === "running" && <div className="scan-track" aria-hidden="true"><span /></div>}
              <strong>{statusName[job.status]}</strong>
              {job.status === "queued" && <button className="secondary-button" onClick={() => void cancelJob()}>取消排队任务</button>}
              {events.map((item) => <p key={item.seq}>{item.seq}. {item.detail}</p>)}
            </div>}
            {report && <div className="report-content">
              <div className="report-summary"><strong>{report.findings.length} 项发现</strong><span>{new Date(report.created_at).toLocaleString("zh-CN")}</span></div>
              {report.findings.length === 0 && <p className="no-findings">当前检查没有产生发现项。请同时查看下方覆盖范围。</p>}
              <div className="findings">{report.findings.map((finding) => <article className="finding" key={finding.id}>
                <div className="finding-top"><button className="location location-button" type="button" title="在左侧定位代码" onClick={() => jumpToLine(finding.line)}>第 {finding.line} 行 · {finding.rule_id}</button>
                  <span className={`severity severity-${finding.severity.toLowerCase()}`}>{finding.severity} · {severityName[finding.severity]}</span></div>
                <h3>{finding.title}</h3><p>{finding.explanation}</p>
                {finding.trigger_path && <p className="trigger-path"><strong>静态触发路径：</strong>{finding.trigger_path.replace(/^静态可能路径：/, "")}</p>}
                <div className="tags"><span>{dispositionName[finding.disposition]}</span><span>{evidenceName[finding.evidence_level]}</span></div>
                <details><summary>证据与修复建议</summary>
                  {finding.evidence.map((item, index) => <p key={index}><strong>{item.source === "Architect" ? "架构师" : item.source}：</strong>{item.detail}</p>)}
                  {finding.verification && <p><strong>核验：</strong>{finding.verification.reason}</p>}
                  <p><strong>建议：</strong>{finding.suggestion}</p>
                </details>
              </article>)}</div>
              <div className="coverage"><h3>审查覆盖</h3><p>已完成：{report.coverage.completed.join("、") || "无"}</p>
                {report.coverage.gaps.length > 0 && <><h4>未覆盖或不可用</h4><ul>{report.coverage.gaps.map((gap, index) => <li key={index}>{gap}</li>)}</ul></>}
                {(report.knowledge_refs?.length || 0) > 0 && <><h4>检索到的知识参考</h4><ul>{report.knowledge_refs?.map((item) =>
                  <li key={item.id}>{item.source_url ? <a href={item.source_url} target="_blank" rel="noopener noreferrer">{item.title}</a> : item.title}
                    {item.provenance === "authored" ? " · 本项目编写" : " · GitHub 参考"}</li>)}</ul>
                  <p>知识条目用于辅助审查，不构成问题已被证实的证据。</p></>}
              </div>
            </div>}
          </section>
        </div>
      </main>}
    </div>
  </div>;
}
