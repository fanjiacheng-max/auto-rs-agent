# Research Agent 需求文档

---

## 架构决策记录（ADR）

### ADR-001：Agent LLM 后端

**决策**：使用 Claude API + tool_use 实现 Agent loop。

**理由**：
- SKILL.md 已定义明确的"执行命令 → 看输出 → 继续"流程，与 tool_use 循环天然匹配。
- tool_use 边界清晰，便于控制执行权限和超时。

**约束**：
- 引入一个薄的 LLM Provider 抽象层（`LLMProvider` interface），第一版只实现 `AnthropicProvider`，保留接入其他模型的空间。
- tool execution、Skill loading、state 管理、错误处理等核心 Agent 逻辑由我们自己的系统负责，不依赖 Claude Code CLI。
- Agent runtime 不直接耦合 Anthropic SDK，只通过 `LLMProvider` 接口交互。

### ADR-002：Web 实时通信层

**决策**：SSE 推送 + REST 回复。

**约束**：
- Agent Run 独立于 SSE 连接运行，浏览器刷新或断线不终止分析任务。
- 所有运行事件有递增 `event_id`，客户端可通过 `Last-Event-ID` 或 `?cursor=` 断线续传。
- SSE 传输结构化事件（JSON），不依赖解析自然语言日志判断状态。
- stdout/stderr 完整内容写入日志文件；SSE 对 stdout/stderr 做分块推送，避免每行一个 event。
- 用户回复（`/reply`）、停止任务（`/stop`）等操作使用 REST endpoint。
- 第一版不使用 WebSocket。

### ADR-003：前端技术栈

**决策**：React + TypeScript + Vite。

**约束**：
- 第一版不引入 Next.js、Redux、Zustand、TanStack Query 或复杂 UI framework。
- 状态管理只用 React 自带的 `useState` / `useEffect` / `useContext`。
- 前端与 FastAPI 分离开发（Vite dev server proxy → FastAPI），生产环境 Vite build 产物由 FastAPI 或反向代理 serve。
- React 主要解决：三栏组件化、SSE 增量事件消费、Run 状态同步、Artifact Preview 类型切换。

---

### ADR-004：Run 状态与事件持久化

**决策**：SQLite 存储 Agent/Application metadata；科研产物保存在文件系统。

**数据模型**：
- SQLite 负责：`projects`、`runs`、`events`、`messages`，后续需要时加 `checkpoints`
- 文件系统负责：PNG / CSV / RDS / H5AD 等分析产物，路径记录在 SQLite，内容不入库
- `events.id` 使用 SQLite 自增主键，直接作为 SSE cursor

**恢复行为**：
- **页面刷新 / SSE 断线**：必须可恢复当前 Run 的状态和历史事件（`SELECT ... WHERE event_id > cursor`）
- **FastAPI 进程重启**：可恢复历史记录；正在执行中的 Agent/R/Python 进程不要求自动恢复（标记为 `interrupted`）
- 第一版不引入任务队列或 worker 进程

### ADR-005：Agent 工具集

**决策**：第一版 Agent 工具集如下：

```
read_file(path)                   → str
list_dir(path)                    → [entry]
write_file(path, content)         → ok
run_command(command)              → {stdout, stderr, exit_code}
ask_user(question, choices?)      → (异步，见下)
```

**约束**：
- 文件工具（`read_file` / `write_file` / `list_dir`）默认限制在当前 Project workspace；Skill 目录只读。
- `run_command` 底层使用 shell，支持 Python、Rscript 及任意 shell 命令，统一入口；默认以 Project workspace 为 cwd。
- `run_command` 必须返回 `exit_code`、`stdout`、`stderr`，支持 `timeout` 和取消。
- 完整 stdout/stderr 写日志文件，SSE 只推送流式 chunk，不每行一个 event。
- `ask_user` 是 human-in-the-loop 机制，调用后立即将 Run 状态设为 `waiting_for_user`，持久化问题内容，结束当前 Agent loop；用户通过 REST `/reply` 回复后恢复 Agent loop。不使用长轮询或阻塞等待。
- 第一版不拆分 `run_python` / `run_rscript`，避免增加 Skill 适配成本。

### ADR-006：Skill 发现规则与目录结构

**决策**：固定扫描 `skills/*/SKILL.md`，不做递归扫描，不支持配置路径。

**目录结构**：
```
auto_rs_agent/
├── skills/          ← Skill 能力目录（只读，Agent 不修改）
├── backend/         ← FastAPI + Agent runtime
├── frontend/        ← React + Vite
├── workspace/       ← 运行时生成，Projects 数据在此
├── SPEC.md
└── CLAUDE.md
```

**约束**：
- Skill 目录视为只读；Agent 运行过程中产生或修改的内容写入 Project workspace，不修改 Skill 本身。
- 第一版 Skill 路径不可通过 `.env` 或配置文件修改。

---

### ADR-007：Run 与 Conversation 数据模型

**决策**：每次用户提交消息创建一个新的 Run；Conversation 属于 Project。

**数据模型**：
- `messages` 以 `project_id` 为主，可选关联 `run_id`
- `runs` 记录触发它的 `trigger_message_id`
- 同一 Project 在 UI 上是一条连续对话，后台每次用户请求有独立 Run、status、events、artifacts

**Agent 上下文组织**（第一版）：
```
system prompt
+ 当前 Project state（名称、workspace 路径、已有文件摘要）
+ 最近若干条 conversation messages
+ 当前用户消息
```
- 第一版不实现历史 Run 自动摘要；等上下文长度成为问题后再增加。

**说明**：即使用户只问"为什么 P03 被过滤"，也会创建一个轻量 Run，只读取已有文件并回答，不强制要求执行脚本。

### ADR-008：Artifact 发现与注册

**决策**：系统自动发现和注册 Artifact，不依赖 LLM 声明。

**机制**：
- `write_file` 工具执行成功后，直接注册对应 artifact
- `run_command` 在执行前快照 workspace 相关目录，执行后 diff 识别新增或修改的文件，自动注册为当前 Run 的 artifact
- Run 完成时做一次轻量兜底扫描，防止遗漏

**范围与过滤**：
- 默认监控结果相关目录（`results/`, `figures/`, `tables/`, `objects/`, `reports/`）
- 忽略 `inputs/`, `.cache/`, `tmp/`, `logs/` 等目录
- 不默认对整个 workspace 做递归扫描

**数据模型**：
- Artifact 与 `project_id` 和 `run_id` 关联
- 同一路径被后续 Run 修改时，也记录为当前 Run 的产物
- Artifact 类型由文件扩展名规则确定（不交给 LLM）
- 第一版 SQLite `artifacts` 表简单记录即可，不做版本系统

---

### ADR-009：Skill 选择行为

**决策**：Agent 默认自动选择 Skill，透明告知后立即执行。

**规则**：
1. 用户消息中明确指定 Skill 名称 → 直接使用，无需选择逻辑
2. 只有一个合理候选 → 自动选择，在 Run 第一个事件中告知用户，立即开始执行
3. 存在歧义（多个合理候选 / 需求不明 / 不同 Skill 会产生明显不同分析路线）→ 调用 `ask_user`，返回候选列表和需要澄清的问题

**歧义判断**：Skill selection 返回 `clear` 或 `ambiguous`；`ambiguous` 时附带候选 Skill 列表和向用户询问的问题。不使用 LLM 自报的数值 confidence threshold。

**说明**：Stop 是运行控制能力，不作为 Skill 选择错误的主要纠错机制。

### ADR-010：执行层、并发与 Timeout

**决策**：
- `run_command` 第一版使用宿主机 subprocess；执行层封装为独立 `Executor` 类，接口稳定，后续可替换为 Docker executor
- 同一 Project 同一时间最多允许一个 active Run（status 为 `pending` / `running` / `waiting_for_user`）
- `run_command` 不设全局 timeout；支持可配置 timeout 参数和用户主动取消；默认 timeout 宽松（由 Skill 指定或不设上限）
- Claude API Key 通过环境变量 `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` 获取；支持 `ANTHROPIC_BASE_URL` 中转平台；第一版不做 API Key 管理 UI

---

### ADR-011：Skill 拆分与 Dependency-aware Execution

**背景**：`geo-scrna-workflow` 将拆为 ~12 个功能性 Skills，覆盖 scRNA pipeline 的各分析步骤。

**核心原则**：
- Skill 描述"用户想做什么"
- Pipeline module 负责"实际执行什么"（R 模块 + Python 脚本）
- Dependency resolver 负责"当前能不能执行、需要补什么"

**三类 Prerequisites**：

1. **Computational dependencies**：缺失时自动补跑，复用已有 cache checkpoint。依赖 pipeline 的 `cache_run` 机制保证增量执行。

2. **Scientific/human gates**：不能自动绕过，必须通过 `ask_user`；**确认一次后持久化到 Project state，不重复询问**。

   | Gate | 触发时机 | 持久化字段 |
   |------|---------|----------|
   | `sample_sheet_review` | 首次 build_combined 前 | `sample_sheet_path` |
   | `annotation_review` | 首次需要 reviewed annotation 的 downstream 模块前 | `external_annotation_file` |
   | `contrast_confirmation` | 首次运行 differential/composition 前 | `confirmed_contrast` |
   | `pseudotime_config` | 首次运行 pseudotime 前 | `pseudotime_config`（celltypes + root_cluster） |
   | `hdwgcna_celltypes` | 首次运行 hdWGCNA 前 | `hdwgcna_target_celltypes` |

3. **Required inputs**：`species`、`data_source`、`contrast` 等缺失时 ask_user，不猜测。

**QC 策略**：QC 无 human gate。Agent 自动 sweep 参数组合（`nmads` × `max_percent_mt`），选取 **cell retention rate 最高**的结果。QC 运行快，适合 sweep。

**Dependency Registry**：用一个中央 YAML 文件（`backend/app/agent/module_registry.yaml`）声明所有模块的依赖、gates、produces。Dependency resolver 从注册表推断执行计划，不依赖 LLM 推断依赖关系。

### ADR-012：远端执行层（SSH + rjob）

**决策**：所有命令（Python 辅助脚本和 R pipeline）统一通过 rjob 提交到远端服务器执行。

**连接信息**：
- SSH alias：`ailab`（`~/.ssh/config` 已配置，key 认证）
- Remote base：`/mnt/shared-storage-gpfs2/gpfs-aging/huaxi_omics/`
- Project workspace：`{remote_base}/auto_agent_workspace/{project_id}/`

**执行环境**：
- Conda env：统一使用 `r_seurat`
- 激活命令：`source /mnt/shared-storage-user/medeval-share/fanjiacheng/miniconda3/etc/profile.d/conda.sh && conda activate r_seurat`
- Container image：`registry.h.pjlab.org.cn/ailab-medeval-medeval_gpu/omicgpu:jcfan-v-cu128torhc27`
- Storage mounts：`gpfs://gpfs2/gpfs-aging` + `gpfs://gpfs1/medeval-share`
- Charged group：`evalmed_gpu`，`--private-machine=group`

**默认资源规格**（可在 run_command 中覆盖）：
| 任务类型 | CPU | Memory |
|---------|-----|--------|
| Python 辅助脚本（inspect/config/preflight） | 4 | 16 GB |
| R pipeline（QC/integration/annotation/DE）| 16 | 128 GB |
| 高内存模块（CellChat/hdWGCNA）| 16 | 256 GB |

**结果文件回传**：
- PNG / CSV：rjob 完成后 SFTP 拉回本地 `workspace/{project_id}/results/`，前端直接显示
- RDS / H5AD 等大文件：留在远端，不回传

**执行流程**：
```
run_command(cmd)
  → rjob submit ... -- bash -c "source conda && <cmd>"
  → 轮询 rjob get <job_name> 直到 Running/Completed/Failed
  → 流式拉取 rjob logs <job_name>（推送 stdout_chunk 事件）
  → 完成后 SFTP 扫描并拉回新增 PNG/CSV artifact
```

**架构**：`SSHRjobExecutor` 实现与 `Executor` 相同接口，现有 agent loop 不需要改动。

---

以下细节按简单、清晰、可扩展原则自行设计，无需用户拍板：
- SSE 结构化事件类型（`run_started` / `skill_selected` / `tool_call` / `tool_result` / `stdout_chunk` / `artifact_created` / `agent_message` / `run_question` / `run_completed` / `run_failed`）
- REST API 端点设计
- SQLite 表结构（`projects` / `runs` / `messages` / `events` / `artifacts`）
- Agent system prompt 具体内容
- React 组件拆分方式
- `workspace/` 和 SQLite DB 文件创建时机

---



做一个面向科研分析的 Agent。

用户只需要输入科研任务，例如：

> 分析 GSE123456，比较肿瘤组和对照组的单细胞差异。

系统自动：

1. 理解用户任务。
2. 从已有 Skills 中选择合适的 Skill。
3. 读取对应 `SKILL.md`。
4. 执行 Skill 中定义的分析流程和脚本。
5. 展示运行过程。
6. 展示分析产生的文件和结果。
7. 必要时向用户请求确认。
8. 完成后给出结果总结。

---

# 2. 已有基础

我已经有一批科研分析 Skills。

Skill 大致结构：

```text
skills/
├── geo-scrna-workflow/
│   ├── SKILL.md
│   ├── scripts/
│   ├── references/
│   └── assets/
│
├── bulk-rna/
├── enrichment/
├── cellchat/
└── ...
```

这些 Skills 已经包含：

* 分析流程
* 科研规则
* Python / R 脚本
* 参数说明
* 输出说明

**原则：不要重新实现这些分析逻辑。**

Agent 只负责调用它们。

---

# 3. 核心需求

## 3.1 自动发现 Skills

系统启动后自动扫描：

```text
skills/*/SKILL.md
```

获取：

* Skill 名称
* Skill 描述
* Skill 路径

例如：

```text
geo-scrna-workflow
用于 GEO 单细胞 RNA-seq 分析
```

Agent 可以根据用户任务决定使用哪个 Skill。

---

## 3.2 按需加载 Skill

不要一次把所有 `SKILL.md` 加载给 LLM。

Agent 初始只知道：

```text
Skill name
Skill description
```

当 Agent 决定使用某个 Skill 时，再读取：

```text
SKILL.md
```

如果 `SKILL.md` 要求读取：

```text
references/workflow.md
```

再继续读取。

---

# 4. Agent 行为

Agent 的角色是：

> 科研任务调度者。

Agent 需要完成：

```text
用户需求
↓
判断应该使用哪个 Skill
↓
加载 Skill
↓
根据 Skill 指令执行
↓
检查执行结果
↓
决定是否继续
↓
输出结果
```

Agent 不应该自己重新发明分析流程。

优先级：

```text
Skill 自带脚本
>
Skill 指定的命令
>
已有代码
>
Agent 临时写代码
```

---

# 5. 执行能力

Agent 至少需要具备：

* 读取文件
* 写文件
* 查看目录
* 执行 Shell
* 执行 Python
* 执行 Rscript
* 查看 stdout
* 查看 stderr

例如 Skill 中写：

```bash
python scripts/preflight.py ...
```

或者：

```bash
Rscript run_pipeline.R config.R
```

Agent 应该能够直接执行。

---

# 6. Project

每个科研任务作为一个 Project。

例如：

```text
Projects

T cell exhaustion
Lung cancer
Breast cancer scRNA
```

一个 Project 对应一个独立目录。

例如：

```text
workspace/
└── t-cell-exhaustion/
```

---

# 7. Project 文件

每个项目中保存：

```text
workspace/
└── project-name/
    ├── inputs/
    ├── results/
    ├── figures/
    ├── tables/
    ├── objects/
    ├── reports/
    └── logs/
```

Agent 产生的所有结果尽量放在这个目录中。

---

# 8. Web 界面

第一版界面保持简单。

使用三栏布局：

```text
┌──────────────┬────────────────────────────┬──────────────────┐
│ Projects     │ Agent                      │ Files / Results  │
│              │                            │                  │
│ Project A    │ User:                      │ Figures          │
│ Project B    │ 分析 GSE123456             │ Tables           │
│              │                            │ Reports          │
│              │ Agent:                     │ Objects          │
│              │ 正在执行 QC...             │                  │
│              │                            │                  │
└──────────────┴────────────────────────────┴──────────────────┘
```

---

# 9. 左侧：Projects

支持：

* 创建 Project
* 查看 Project
* 切换 Project
* 删除 Project
* 修改 Project 名称

第一版做到这些即可。

---

# 10. 中间：Agent

中间区域类似聊天界面。

用户可以输入：

```text
分析 GSE123456。
```

Agent 返回：

```text
已识别任务为 GEO 单细胞分析。

正在使用：
geo-scrna-workflow

当前步骤：
正在检查输入数据。
```

执行过程中展示简单状态：

```text
✓ 检查输入
✓ 生成配置
● 正在运行分析
○ 结果检查
```

不需要展示 Agent 的完整思考过程。

只展示：

* 当前在做什么
* 调用了哪个 Skill
* 执行了什么命令
* 成功 / 失败
* 产生了什么文件
* 是否需要用户确认

---

# 11. 右侧：结果文件

右侧展示当前 Project 产生的文件。

例如：

```text
Figures
- qc_violin.png
- umap.png

Tables
- qc_summary.csv
- markers.csv

Objects
- seurat.rds

Reports
- report.html
```

点击后可以预览常见文件。

第一版优先支持：

* PNG
* JPG
* CSV
* TSV
* TXT
* Markdown
* HTML
* JSON

RDS 等文件只显示文件名和大小即可。

---

# 12. 用户确认

部分科研步骤不能完全自动决定。

Agent 可以暂停并询问用户。

例如：

```text
检测到 8 个样本。

Tumor:
P01
P02
P03
P04

Control:
P05
P06
P07
P08

是否确认这个分组？

[确认]
[修改]
```

用户确认后 Agent 继续。

第一版不需要设计复杂审批系统。

只需要支持：

```text
Agent 暂停
↓
用户回答
↓
Agent 继续
```

---

# 13. 错误处理

如果脚本执行失败：

不要假装成功。

需要展示：

```text
分析失败

Skill:
geo-scrna-workflow

Command:
Rscript run_pipeline.R

Error:
...
```

用户可以继续问 Agent：

> 为什么失败？

或者：

> 修复后继续。

Agent 可以根据 Skill 的 troubleshooting 说明处理。

---

# 14. 第一版必须实现

第一版只做以下功能：

* [ ] Web 页面
* [ ] Project 创建和切换
* [ ] 简单聊天界面
* [ ] 自动扫描 Skills
* [ ] LLM 根据任务选择 Skill
* [ ] 按需读取 `SKILL.md`
* [ ] 执行 Skill 中的 Python / R / Shell
* [ ] 显示执行状态
* [ ] 显示 stdout / stderr
* [ ] 展示生成的结果文件
* [ ] 用户可以中途回答 Agent
* [ ] Project 数据持久化

---

# 15. 第一版暂时不做

暂时不要做：

* 多 Agent
* 拖拽式工作流
* Skill Marketplace
* Kubernetes
* 分布式任务
* Kafka
* Temporal
* 向量数据库
* RAG
* 知识图谱
* 用户权限系统
* 团队协作
* 计费系统
* 复杂审批流

先保证最核心流程跑通。

---

# 16. 第一阶段 Demo

第一阶段必须跑通这个例子：

用户：

```text
使用 geo-scrna-workflow 分析这个数据。
```

系统：

```text
发现 geo-scrna-workflow
↓
读取 SKILL.md
↓
按照 Skill 指令执行
↓
运行 Python / R 脚本
↓
展示执行过程
↓
找到生成的 PNG / CSV / RDS
↓
右侧显示结果
↓
Agent 总结本次分析
```

只要这个流程完整跑通，第一版就算成功。

---

# 17. 最终产品体验

最终希望用户看到的是：

```text
用户：
分析这个 GEO 数据。

Agent：
正在使用 GEO scRNA-seq Skill。

✓ 数据检查
✓ 样本信息读取
✓ Preflight
● QC 分析
○ Annotation
○ Differential expression

生成文件：

qc_summary.csv
qc_violin.png
seurat_qc.rds
```

用户不需要知道后面具体执行了多少 Python / R 脚本。

核心体验是：

> **用户提出科研任务，Agent 自动调用已有 Skills 完成分析。**

