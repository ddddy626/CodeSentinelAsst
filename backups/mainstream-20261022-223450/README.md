# CodeSentinel V1

单文件 Python、JavaScript、TypeScript 代码审查工作台。React 提交任务，FastAPI 验证身份与项目权限，Redis 通知独立 Worker，Worker 通过 LangGraph 状态图执行 Planner、Scanner、Architect/Reviewer 与条件复审，MySQL 保存任务、事件、审计与报告，SSE 推送进度。提交的源码只用于审查，不会被执行或自动修改。

## Docker Compose 本地启动

1. 将 `.env.example` 复制成 `.env`，更换两个 MySQL 密码。若密码含 URL 保留字符，需在 `CODESENTINEL_DATABASE_URL` 中进行 URL 编码；最简单的是使用长随机字母数字密码。
2. `docker compose up --build -d`
3. `docker compose run --rm api python -m app.admin admin`，按提示输入初始管理员密码（至少 12 字符）。没有公开注册接口。
4. 打开 <http://127.0.0.1:8080>，登录后创建项目、粘贴代码或上传 `.py`、`.js`、`.jsx`、`.ts`、`.tsx` 文件并提交审查。管理员可通过 `POST /api/admin/users` 创建其他用户。

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

可选模型参数：`CODESENTINEL_LLM_URL`、`CODESENTINEL_LLM_MODEL`、`CODESENTINEL_LLM_KEY`。URL 须兼容 OpenAI Chat Completions JSON。密钥仅由后端读取。没有配置模型时，报告明确标出覆盖缺口。Python Semgrep 规则需要将 `CODESENTINEL_SEMGREP_RULES` 指向本地规则文件；Compose 已指向 `backend/rules/python-v1.yaml`。JavaScript/TypeScript 默认使用 `backend/rules/web-v1.yaml`，可通过 `CODESENTINEL_WEB_SEMGREP_RULES` 覆盖。

## 已实现的 V1 流程

- 管理员创建用户，用户登录后仅能访问自己创建的项目、任务、事件与三层记忆。会话 12 小时过期，密码使用 PBKDF2 哈希保存。
- `.py`、`.js`、`.jsx`、`.ts`、`.tsx` 输入上限 100 KB、2000 行；浏览器上传要求有效 UTF-8，服务端校验 Python 语法并返回错误行号。超过 20000 字符或 800 行时给出建议规模警告。任务状态为 queued、running、completed、failed、cancelled；排队任务可取消。
- LangGraph 实际运行 `planner → scanner → architect`，出现存疑候选且扫描器失败时走 `recheck → architect` 回边，因此该图不是 DAG。Python Scanner 运行 AST、Ruff、Bandit、Semgrep；JavaScript/TypeScript 运行 Semgrep 规则，并可调用模型生成候选。Architect 可用单独提示词调用模型复核，最终仍按源码与工具证据裁决。`ScanResult` 和模型候选由 Pydantic 严格校验。
- Python 的 AST 上下文选择在超预算时保留相关函数与原始行号；JavaScript/TypeScript 按发现行选择带原始行号的源码片段。报告记录源码哈希、选取范围及省略范围；该策略是选择原文，不是摘要或跨文件分析。
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
| 工具与规则 | `backend/app/tools.py`、`backend/rules/python-v1.yaml`、`backend/rules/web-v1.yaml` |
| 证据核验 | `backend/app/verifier.py`、`backend/app/review.py` |
| 记忆 | `backend/app/memory.py` |
| React 工作台 | `frontend/src/App.tsx`、`frontend/src/styles.css` |
| 对照评测 | `backend/app/ablate.py`、`backend/evaluation/ablation_cases.json` |

建议下一步：先用真实项目的人工标注样本评估误报和漏报，再增加针对性复审专家与多 Worker 租约，最后进入 V2 的多文件和沙箱验证。
