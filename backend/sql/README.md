# 数据库脚本

## MySQL 8.4

`000_codesentinel.mysql.sql` 是完整建库脚本，包含后端当前使用的 10 张表，包括 `review_scores` 评分表和 `knowledge_index` 向量索引表。默认数据库名为 `codesentinel`，与 `compose.yaml` 一致。脚本只使用 `CREATE ... IF NOT EXISTS`，重复执行不会清空已有数据。

本机 MySQL 服务监听 **3309**。用有建库权限的账号连接后，在 MySQL Workbench 中打开并执行 `000_codesentinel.mysql.sql`。也可用命令行客户端执行：

```text
mysql --host=127.0.0.1 --port=3309 --user=<管理员账号> --password --execute="SOURCE D:/CodeSentinel-codex/backend/sql/000_codesentinel.mysql.sql"
```

导入后，应用需要设置 `CODESENTINEL_DATABASE_URL=mysql://<应用账号>:<URL编码后的密码>@127.0.0.1:3309/codesentinel`。仅有 MySQL 数据库并不会让当前运行中的 SQLite 后端自动切换；修改配置后需重启后端与 Worker。应用账号需有 `codesentinel` 的读写权限。

`002_demo_score.mysql.sql` 是可选的页面演示数据。**先注册至少一个普通账号**，再运行此脚本；它将示例项目和 80 分报告归属到按用户名排序的第一个账号。示例报告不是真实扫描，固定 ID 保证重复执行不会复制记录。不需要演示数据时无需执行此文件。

## SQLite

未设置 `CODESENTINEL_DATABASE_URL` 时，后端使用 `backend/data/reviews.sqlite3`，也可用 `CODESENTINEL_DB` 改变文件路径。后端启动时自动建表。`001_review_scores.sqlite.sql` 可单独补建评分表；注册账号后，`002_demo_score.sqlite.sql` 可选插入演示记录。请勿对 MySQL 执行 SQLite 脚本。

评分从 100 分开始，S0/S1/S2/S3 分别扣 40/20/8/3 分，最低 0 分。弱证据与待核验项暂不扣分；用户标为误报的发现不扣分，标为确认问题的发现参与扣分。分数只反映本次报告覆盖到的问题。
