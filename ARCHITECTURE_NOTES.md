# ARCHITECTURE_NOTES.md
# 考试小抄 — 只记容易忘的事实，不写废话

---

## Agent Loop

**入口：**
`run_agent(run_id, project, user_message)` — `backend/app/agent/loop.py:101`
由 `routes.send_message()` 用 `asyncio.create_task()` 启动，独立于 HTTP 请求存活。
恢复入口：`resume_agent(run_id, project, user_reply)` — 由 `POST /runs/{id}/reply` 触发。

**核心函数：**
- `run_agent()` — 外壳：skill 选择、SKILL.md 加载、workspace 目录创建、异常兜底
- `_llm_loop()` — 内核：反复调 `provider.chat()` → 执行 tool_use → 把结果塞回 messages → 再调
  - 每轮最多 50 次迭代（safety cap），避免无限循环
  - `ask_user` 工具是特殊路径：
    1. `save_pending_state(messages, tool_use_id)` → 持久化到 `run_state` 表
    2. `set_run_pending_question()` → status=`waiting_for_user`，emit `run_question`
    3. break loop，等待 `POST /reply`
    4. `resume_agent()` 从 `run_state` 恢复 messages，注入 tool_result，重进 `_llm_loop`

**状态变化（runs.status）：**
```
pending → running → completed
                 → waiting_for_user  (ask_user 触发)
                 → failed            (异常 / 迭代上限)
                 → interrupted       (cancel_run() 触发，用户手动 stop)
```
状态写到 SQLite `runs` 表，同时 `append_event` 写 `events` 表（前端靠事件表，不靠 runs.status）。

**失败处理：**
- `except Exception` 在 `run_agent()` 最外层：写 `run_failed` event，更新 `runs.status = failed`，然后 re-raise（不吃掉异常）
- `asyncio.CancelledError` 单独捕获：写 `run_interrupted`
- tool 执行失败（exit_code != 0）：结果作为 tool_result 原样送回 LLM，由 LLM 决定是否继续

---

## Run / Message / Artifact / ProjectState

**各自含义：**
- `messages` — 对话历史，属于 Project。role = user | assistant。
- `runs` — 单次执行任务，有独立 status 和生命周期。
- `events` — Run 内细粒度流式事件（id 自增，作为 SSE cursor）。
- `artifacts` — Run 产生的文件记录（path + type + size）。
- `status.json` — Project workspace 根目录下的状态文件。**Gate 确认、模块状态、尝试过的参数的 source of truth。** SQLite 不存这些。

**为什么分开：**
- messages 给 LLM 看，events 给前端看。
- `status.json` 和项目数据在一起，换机器不丢失；人工可直接编辑（比如手动标记 gate 为已确认）。

**`status.json` 字段：**
- `gates` — 5 个 scientific gates，`confirmed` + `value` + `confirmed_at`
- `modules` — 每个 pipeline 模块的 status / checkpoint_path / checkpoint_verified
- `tried_params` — 每个模块尝试过的参数组合 + 是否被选中
- `notes` — Agent 只追加，不覆盖；用户可自由编辑

**写入规则：**
- `notes`：Agent 追加（带时间戳前缀），不覆盖已有内容
- 所有写操作通过 `ProjectState` 类，带 per-project asyncio lock，atomic write（write tmp → replace）

---

## SSE

**为什么不用 WebSocket：**
Agent → 前端是单向推送，不需要双工。用户回复（ask_user 的答案、stop）走 REST POST 就够了。SSE 是 HTTP，断线重连浏览器原生支持，服务端无状态。

**断线怎么恢复：**
1. 客户端连接 `GET /api/runs/{id}/events?cursor=<last_event_id>`
2. 服务端查 `SELECT * FROM events WHERE run_id=? AND id > cursor ORDER BY id`
3. 前端 `EventSource` 会自动发 `Last-Event-ID` header，但我们用 query param `?cursor=` 更明确
4. Run 独立于连接存活（asyncio task 在后台），断线不影响执行

**实现位置：** `routes/__init__.py:stream_events()` — 每 0.4s 轮询 SQLite，yield SSE frame

---

## Executor

**本地 subprocess 怎么启动：**
```python
# executor.py:27
proc = await asyncio.create_subprocess_shell(
    command, cwd=cwd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    env={**os.environ},   # 继承当前环境变量
)
```
stdout 用 `proc.stdout.read(4096)` 分块读，每块调 `stdout_callback(chunk)` → 触发 `emit("stdout_chunk")`

**SSH + rjob 怎么启动：**
```python
# ssh_executor.py
# 1. 提交：command 通过 tee 同时写 GPFS 日志文件
rjob submit ... -- bash -c '( <cmd> ) 2>&1 | tee <log_file>; echo __AGENT_EXIT_$?__ >> <log_file>'
# 解析 stdout 中 "created rjob_name: <actual_name>"

# 2. 实时日志：ssh tail -f <log_file>（无延迟，container 写入即可读）
#    Reader 是权威：看到 __AGENT_EXIT_<code>__ sentinel 才结束
#    Poller 是安全网：job terminal >60s 仍无 sentinel → 强制结束（防 OOM kill 等异常）

# 3. Fallback：若 log_file 未出现（job 启动失败），回落到 rjob logs（有 ~65s 延迟）
```

**延迟说明：**
- Container 冷启动：~40s（不可避免，rjob 分配节点 + pull image）
- 日志实时性：0s 额外延迟（tail -f 直读 GPFS 文件）
- 原方案（rjob logs）：额外 +65s 入库延迟

**怎么 stop：**
- 本地：`cancel_event.set()` → executor 里 `watch_cancel` coroutine 调 `proc.terminate()`
- 远端：`cancel_event.set()` → `ssh ailab "rjob stop <job_name>"`
- 触发点：`POST /runs/{id}/stop` → `cancel_run(run_id)` → `_cancel_events[run_id].set()`

**API key 在哪：**
`ANTHROPIC_AUTH_TOKEN` 环境变量，在 `config.py` 读取，只传给 `anthropic.Anthropic(auth_token=...)` 构造函数。不写文件、不拼进 shell 命令、不出现在 events/logs 里。

---

## Cache（R pipeline 内部）

**cache key 怎么构成：**
`cache_run(ctx, "02_qc", fn, cfg_fragment=cfg$qc, input_fingerprint=object_fingerprint(object))`
key = checkpoint_name + hash(cfg_fragment) + input_fingerprint
存在 `results/checkpoints_adaptive_v2/` 目录下。

**fingerprint 是什么：**
- 输入数据：`cfg$input$fingerprint_mode = "size_mtime"`（文件大小 + 修改时间）
- Seurat object：`object_fingerprint(object)` — 对象内容 hash
- config fragment：序列化后 hash

**stale propagation（上游变了，下游怎么处理）：**
pipeline 是线性执行的（`99_pipeline.R` 顺序调用）。上游 `cache_run` 返回新 object，下游的 `input_fingerprint = object_fingerprint(object)` 就会变，自动 cache miss，重新执行。
- 不自动"向下传播失效"，靠下游 fingerprint 自然对不上
- `output$force_recompute = TRUE` 强制全部重跑

---

## Dependency Resolver

**位置：** `backend/app/agent/resolver.py`，数据来源：`module_registry.yaml` + `status.json`

**computational dependency：**
`DependencyResolver.resolve(target_module, ps)` 做 topo sort，对每个模块检查 `status.json modules[mod].status == "completed"`（+ 可选 SSH 验证 checkpoint 路径）。缺失的模块加入 `plan.modules_to_run`，已完成的进 `plan.already_done`。LLM 不决定依赖关系，Resolver 决定。

**scientific gate：**
对 `to_run` 列表中所有模块收集 `gates`，检查 `status.json gates[gate].confirmed`。未确认的进 `plan.blocking_gates`。Gate 触发时用 `pending_id = "gate:<name>"` 存入 `run_state`，用户回复后 `resume_agent` 调 `ps.confirm_gate()` 写入 `status.json`，然后重新 `run_agent` 从头 resolve。

**required input：**
只检查 target module 的 `required_inputs` 字段，对照 `status.json inputs`。缺失的进 `plan.missing_inputs`，触发 `ask_user`，用 `pending_id = "input:<name>"`。回复后写入 `ps.set_input()`，重新 resolve。

**执行计划注入 system prompt：**
`plan.summary()` 传给 `_build_system()`，LLM 看到"Cached (skip): io, qc / Will run: differential"，不会重跑已缓存模块。
