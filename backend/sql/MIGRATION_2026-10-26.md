# CodeSentinel 本机 MySQL 迁移记录

- 目标：`127.0.0.1:3309/codesentinel`。应用使用独立的 `codesentinel` 数据库账号。
- 源库：`backend/data/reviews.sqlite3`。停机快照保存在 `D:\Users\29318\Documents\ChatGPT\New project\codesentinel-migrate-20261026\reviews-frozen.sqlite3`；原 `.env` 备份为同目录的 `.env.before`。
- 已导入：用户 2、会话 7、项目 1、审查 2、事件 16、审计 14。记忆和人工反馈原本均为 0。逐表数据比对通过。
- 评分：原 SQLite 表为 0 行；根据两份已完成报告补算并写入 MySQL 2 行。
- RAG：本地向量索引的 51 条 384 维向量已导入 `knowledge_index`，旧索引备份为同目录的 `knowledge-index-before-mysql.json`。本地索引文件已移除，新进程在没有该文件时仍完成了 MySQL 检索。嵌入模型文件和可编辑知识条目仍保留在磁盘。
- MySQL 当前有 10 张应用表。后端测试 83 项通过，`/api/ready` 返回 `ready`，前端返回 HTTP 200。
- 本机启动：从项目根目录运行 `./启动后端.py`，同时启动 API 和 Worker，并读取 `.env` 中的数据库配置。

旧 SQLite 文件保留，便于核对和恢复。切换后新增的数据只写入 MySQL；恢复旧配置前应先核对这部分新数据，避免丢失。
