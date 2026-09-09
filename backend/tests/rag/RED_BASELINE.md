# RAG 测试首次运行记录

- 日期：2026-09-09
- 分支：`codex/test-biomedical-rag`
- 生产代码基线：`2f9cb78`（Add DEVELOPER_GUIDE.md）
- 解释器：Python 3.12.14，Windows 64 位，Codex 内置运行时
- 阶段：用户要求先写测试，尚未实现 RAG

## 已执行命令

在仓库根目录执行：

```powershell
& 'C:\Users\10166\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest discover -s backend/tests -t backend -v
```

结果：退出码 1，运行 42 个测试，2 个 PASS、40 个 FAIL、0 个 ERROR、0 个 SKIP。

| 失败原因 | 数量 |
| --- | ---: |
| 缺失 `app.agent.rag.load_candidates` | 14 |
| 缺失 `app.agent.rag.resolve_entity` | 7 |
| 缺失 `app.agent.rag.collect_evidence` | 17 |
| `TOOL_SCHEMAS` 未注册 RAG 工具 | 1 |
| `ToolContext` 未实现 RAG handler | 1 |

所有 FAIL 均为缺失功能的明确断言；没有因测试导入、依赖或语法错误而失败。
缺失 API 的用例尚未执行到后面的业务断言；这次 RED 不能证明将来实现后的所有断言
都可通过，必须在实现时继续执行并核对失败原因。

## 已单独复核的现有功能

在 `backend` 目录执行：

```powershell
& 'C:\Users\10166\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest tests.rag.test_tool_integration.ToolIntegrationTests.test_existing_read_file_tool_still_reads_project_artifacts tests.rag.test_tool_integration.ToolIntegrationTests.test_unknown_tool_is_still_reported_as_an_error -v
```

两个测试均通过，退出码 0：已有 read_file 可读取项目文件，未知工具仍返回原有错误。

## 运行边界

- 未修改生产代码，也未创建 RAG 占位实现。
- 未安装依赖、未访问真实数据库、未调用模型或 HPC。
- 解释报告的 12 个验收案例尚未执行。
- 完整原始输出保存在本机被 Git 忽略的 `workspace/test-results/rag-red.log`。
- 本记录是首次运行快照，不代表未来提交或代码版本的测试状态。
