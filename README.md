# CodeSentinel V1

Python、JavaScript、TypeScript、Java、Go、C、C++、C#、Rust、PHP、Ruby、Kotlin、Swift 源码及 SQL、XML、YAML、Properties 审查工作台。支持单文件和有界的多文件任务；多文件任务逐文件审查并汇总，不进行跨文件调用链分析。React 提交任务，FastAPI 验证身份与项目权限，Redis 通知独立 Worker，Worker 通过 LangGraph 状态图执行 Planner、Scanner、Architect/Reviewer 与条件复审，MySQL 或本地 SQLite 保存任务、事件、审计与报告，SSE 推送进度。提交的源码只用于审查，不会被执行或自动修改。

## Docker Compose 本地启动

1. 将 `.env.example` 复制成 `.env`，更换两个 MySQL 密码。若密码含 URL 保留字符，需在 `CODESENTINEL_DATABASE_URL` 中进行 URL 编码；最简单的是使用长随机字母数字密码。
2. `docker compose up --build -d`
3. 可运行 `docker compose run --rm api python -m app.admin admin` 创建初始管理员，按提示输入密码（至少 12 字符）。管理员账号仍需通过命令行或管理员接口创建。
4. 打开 <http://127.0.0.1:8080>，在登录页注册普通账号或登录，然后创建项目、粘贴代码或上传支持的源码或配置文件并提交审查。管理员可通过 `POST /api/admin/users` 创建其他用户。

Web 仅绑定本机 `127.0.0.1:8080`。计划在外网提供服务前，应部署 HTTPS 反向代理并设置 `CODESENTINEL_SECURE_COOKIE=1`。`/api/health` 是存活检查，`/api/ready` 检查数据库和 Redis。API 文档在容器内 `/docs`；本地开发可运行 `uvicorn app.main:app --reload` 后访问 <http://127.0.0.1:8000/docs>。

## 不使用 Docker 的开发运行

需要 Python 3.12+、uv、Node.js、MySQL 8.4 和 Redis 7。也可以不设置 `CODESENTINEL_DATABASE_URL`，使用本地 SQLite 开发适配器；异步任务仍要求 Redis。

```text
cd backend
uv sync --locked
uv run --locked python -m app.admin admin
uv run --locked python -m uvicorn app.main:app --reload
```

另开终端在 `backend` 运行 `uv run --locked python -m app.worker`；在 `frontend` 运行 `npm ci`、`npm run dev`，打开 <http://localhost:5173>。Vite 将 `/api` 代理到本地 FastAPI。后端版本由 `pyproject.toml` 与 `uv.lock` 锁定，前端版本由 `package-lock.json` 锁定。

可选模型参数：`CODESENTINEL_LLM_URL`、`CODESENTINEL_LLM_MODEL`、`CODESENTINEL_LLM_KEY`。URL 须兼容 OpenAI Chat Completions JSON。密钥仅由后端读取。没有配置模型时，报告明确标出覆盖缺口。Python Semgrep 规则需要将 `CODESENTINEL_SEMGREP_RULES` 指向本地规则文件；Compose 已指向 `backend/rules/python-v1.yaml`。JavaScript/TypeScript 默认使用 `backend/rules/web-v1.yaml`，可通过 `CODESENTINEL_WEB_SEMGREP_RULES` 覆盖。新增十种语言默认使用 `backend/rules/mainstream-v1.yaml`，可通过 `CODESENTINEL_MAINSTREAM_SEMGREP_RULES` 覆盖。

本机 3309 的 MySQL 已迁入现有账号、项目、审查记录和评分。本机重启 API 与 Worker 可双击项目根目录的 `启动后端.py`，或运行 `python .\启动后端.py`；脚本读取 `.env` 中的 MySQL 配置。前端开发服务仍在 `frontend` 运行 `npm run dev`。旧 SQLite 文件保留作回退备份。

## 本地向量知识库

`backend/knowledge/cards.jsonl` 有 51 条可编辑中文知识条目，覆盖上述 17 类语言或文件格式。每条标明 GitHub 参考或本项目编写，并附来源链接（如适用）。审查时先按语言过滤，再用本地 `intfloat/multilingual-e5-small` 模型对源码和工具发现进行向量检索；最多 3 条参考进入模型上下文，并显示在报告中。知识条目是审查提示，不作为独立漏洞证据。未配置聊天模型时，静态审查仍可运行，但不执行这一步知识增强。

首次构建需要联网下载嵌入模型，之后从 `backend/data/knowledge` 读取本地模型。配置 MySQL 时，向量索引从 `knowledge_index` 表读取；SQLite 模式仍读取本地 JSON 索引。可以在 `backend` 目录运行 `uv run --locked python -m app.knowledge build` 预下载并构建索引，或运行 `uv run --locked python -m app.knowledge query --language java --text "Runtime.getRuntime().exec(userInput)"` 检查结果。编辑条目后会自动重建索引；`CODESENTINEL_KNOWLEDGE_CACHE` 可修改缓存目录。具体格式与来源见 `backend/knowledge/README.md`。

## 已实现的 V1 流程

- 访客可通过 `POST /api/register` 注册普通账号；公开注册不能创建管理员。用户登录后仅能访问自己创建的项目、任务、事件与三层记忆。会话 12 小时过期，密码使用 PBKDF2 哈希保存。
- 支持 `.py`、`.js`、`.jsx`、`.ts`、`.tsx`、`.java`、`.go`、`.c`、`.h`、`.cpp`、`.cc`、`.cxx`、`.hpp`、`.cs`、`.rs`、`.php`、`.rb`、`.kt`、`.kts`、`.swift`、`.sql`、`.xml`、`.yml`、`.yaml`、`.properties`；输入上限 100 KB、2000 行；浏览器上传要求有效 UTF-8，服务端校验 Python 语法和 XML 格式并返回错误行号。超过 20000 字符或 800 行时给出建议规模警告。任务状态为 queued、running、completed、failed、cancelled；排队任务可取消。
- 前端可选择 2–12 个文件或一个文件夹中受支持的文件，经 `POST /api/project-reviews` 创建项目审查任务；单文件上限 100 KB、总量上限 300 KB。Worker 逐文件运行现有审查流程，汇总报告保留相对路径与行号，历史记录可切换查看原文。当前不追踪跨文件调用链，也不运行项目。
- 用户可在报告中为发现项保存“确认问题、误报、接受风险”及说明；`GET /api/jobs/{job_id}/feedback` 读取当前任务的判断，仅任务所有者可访问。判断与原始机器报告分开保存，不会改变原报告裁决或自动屏蔽后续任务的同类问题。
- 已完成任务可通过报告页或 `GET /api/jobs/{job_id}/sarif` 下载 SARIF 2.1.0；导出保留规则号、相对文件路径、行号及覆盖缺口。文件夹上传会去掉所选文件夹名称，使路径相对于该文件夹。尚未接入 GitHub 上传或验证仓库中的路径匹配；导出的结果仅包含发现项，覆盖缺口保存在 run 属性中。
- LangGraph 实际运行 `planner → scanner → architect`，出现存疑候选且扫描器失败时走 `recheck → architect` 回边，因此该图不是 DAG。Python Scanner 运行 AST、Ruff、Bandit、Semgrep；其他编程语言运行各自的 Semgrep 规则；SQL、XML、YAML、Properties 使用本地单文件静态规则。各类型也可调用模型生成候选。新增编程语言的内置规则目前每种只覆盖一类风险；C/C++ 在 Semgrep OSS 中属实验性支持。配置文件规则只报告部分可见线索，不会运行数据库或 Spring Boot 服务。Architect 可用单独提示词调用模型复核，最终仍按源码与工具证据裁决。`ScanResult` 和模型候选由 Pydantic 严格校验。
- Python 的 AST 上下文选择在超预算时保留相关函数与原始行号；其他语言按发现行选择带原始行号的源码片段。报告记录源码哈希、选取范围及省略范围；该策略是选择原文，不是摘要或跨文件分析。
- 直接 `eval(input())`/`exec(input())` 的静态模式列为“必须修复”；其他动态执行路径只作建议，LLM 独有发现列为“待核验”。报告提供风险 S0–S3、证据 strong/medium/weak、规则号、行号、修复建议、原始工具条目和未覆盖范围。裁决只是建议，不会阻断用户代码。
- MySQL/SQLite 持久保存任务、事件、报告、审计与任务复审计数，记录源码 SHA256、规则/构建/模型版本。Redis 是通知队列；Worker 重启时从数据库重新入队未完成任务。事件接口支持 `after` 和 SSE `Last-Event-ID` 补读。
- `memory.py` 提供 Task、Project、Experience 三层记忆服务接口，存储来源、候选/已验证/废弃状态、版本及租户边界；高级检索与自主学习不属于 V1 当前执行路径。

当工具失败且存在存疑发现时，Reviewer 可请求针对性复审，重试静态工具并按规则号及行号追加独立佐证；没有新增证据就提前停止，最多 5 次。工具正常而证据仍不足时保持“待核验”。模型输出和静态路径均不构成漏洞真实可达性的证明。

## 验证与限制

```text
cd backend
uv run --locked python -m pytest -q
uv run --locked python -m app.evaluate
uv run --locked python -m app.ablate --dataset evaluation/ablation_cases.json --context-budget 300 --out evaluation/results/ablation-offline.json
# 配置 CODESENTINEL_LLM_* 后才运行模型组；该命令会产生 API 调用费用
uv run --locked python -m app.ablate --dataset evaluation/ablation_cases.json --with-model --context-budget 300 --out evaluation/results/ablation-live.json
cd ../frontend
npm run build
```

`app.evaluate` 的 12 个样本及 `app.ablate` 的 16 个样本均为合成回归样本，只能校验内置动态执行规则及实验流程。A/B/C/D 分别表示静态工具、工具加 Scanner、双角色、双角色加 AST 上下文选择；未配置模型时 B/C/D 明确跳过。当前开发环境没有 Docker，Compose 的 MySQL、Redis 与 Web 全链路需在装有 Docker 的主机上再做启动验收。Worker 恢复策略以单 Worker 部署为前提；多 Worker 租约、数据库迁移和真实项目基准集属于后续工作。

## 可编辑入口

| 领域 | 文件 |
|---|---|
| API 与认证 | `backend/app/main.py`、`backend/app/storage.py` |
| Worker 与任务流程 | `backend/app/worker.py`、`backend/app/orchestrator.py` |
| LLM 与提示词 | `backend/app/llm.py`、`backend/app/prompts/review.md`、`backend/app/prompts/architect.md` |
| AST 上下文 | `backend/app/context.py` |
| 工具与规则 | `backend/app/tools.py`、`backend/rules/python-v1.yaml`、`backend/rules/web-v1.yaml`、`backend/rules/mainstream-v1.yaml` |
| 证据核验 | `backend/app/verifier.py`、`backend/app/review.py` |
| 记忆 | `backend/app/memory.py` |
| React 工作台 | `frontend/src/App.tsx`、`frontend/src/styles.css` |
| 对照评测 | `backend/app/ablate.py`、`backend/evaluation/ablation_cases.json` |

建议下一步：先用真实项目的人工标注样本评估误报和漏报，再增加针对性复审专家与多 Worker 租约，最后进入 V2 的多文件和沙箱验证。



