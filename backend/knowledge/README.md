# CodeSentinel 本地审查知识库

`cards.jsonl` 是可编辑的知识条目，一行一个 JSON 对象。当前有 51 条，覆盖 13 种编程语言及 SQL、XML、YAML、Properties。`provenance=github` 表示该条参考了 `source_url` 指向的 GitHub 原始资料；`provenance=authored` 表示由本项目编写。条目是中文独立总结，没有复制上游规则代码。

每条含 `id`、`language`、`title`、`guidance`、`keywords`、`provenance`、`source_url`。新增或修改时保持 ID 唯一，并为每个受支持语言保留至少一条。审查器只检索当前文件语言的条目，向量相似度决定排序。检索结果进入 Scanner 与 Architect 的模型上下文，但只作参考；报告仍按当前源码行和工具证据裁决。

本地嵌入模型为 `intfloat/multilingual-e5-small`，由 FastEmbed/ONNX Runtime 运行。首次构建下载模型；模型文件存于 `backend/data/knowledge`（可用 `CODESENTINEL_KNOWLEDGE_CACHE` 覆盖）。使用 MySQL 时，JSON 向量索引存于 `knowledge_index` 表；使用 SQLite 时，索引仍存于 `backend/data/knowledge/index.json`。索引保存模型名、条目 ID、知识库 SHA-256 和 384 维向量；修改条目后自动重建。用户代码不保存到知识索引，嵌入检索也不向外部服务发送代码。

在 `backend` 中运行：

```text
uv run --locked python -m app.knowledge build
uv run --locked python -m app.knowledge query --language java --text "Runtime.getRuntime().exec(userInput)"
```

GitHub 资料主要来自 [Semgrep 规则库](https://github.com/semgrep/semgrep-rules)和 [OWASP CheatSheetSeries](https://github.com/OWASP/CheatSheetSeries)。来源链接记录在各条目中。检索命中不等于规则已经适用于当前代码，也不构成漏洞证据。
