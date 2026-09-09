# 组学分析结果 RAG：测试契约

本轮只新增测试和验收说明，不实现检索、不安装新依赖、不调用真实数据库或模型。
这些测试定义下一步实现要满足的外部行为；函数名和返回字段是本轮提出的接口约定，
不是已有功能。旧 SPEC 的第一阶段暂不做 RAG；本测试套件对应用户新提出的后续扩展。

## 运行

需要 Python 3.10+。从仓库根目录执行：

```powershell
python -B -m unittest discover -s backend/tests -t backend -v
```

仅运行现有工具的回归检查：

```powershell
python -B -m unittest tests.rag.test_tool_integration.ToolIntegrationTests.test_existing_read_file_tool_still_reads_project_artifacts tests.rag.test_tool_integration.ToolIntegrationTests.test_unknown_tool_is_still_reported_as_an_error
```

第二条命令的工作目录是 `backend`。本机 Windows 的 `py` 当前指向 32 位 Python 3.9，
不能运行项目中的 Python 3.10 类型语法；请使用 Python 3.10+ 解释器。
本轮实际运行使用 Codex 自带 Python 3.12，完整命令见 `RED_BASELINE.md`。

测试使用标准库 unittest、临时目录和合成记录。普通 Python socket 联网会直接触发断言；
这不是操作系统级隔离，也不应在测试中调用 shell、HPC、真实 API 或模型 SDK。

## 当前覆盖

| 文件 | 范围 |
| --- | --- |
| `test_candidates.py` | edgeR/Seurat 字段映射、CSV/TSV、上下调、FDR/效应量阈值、背景与结果溯源、无效统计值、探索性标签 |
| `test_entities.py` | 别名、物种、实体类型、歧义、精确 ID、蛋白异构体 |
| `test_evidence.py` | 证据保真、跨库去重、独立论文计数、冲突、上下文不匹配、来源错误与取消 |
| `test_tool_integration.py` | 工具 schema、真实 dispatcher 分发、已有 read_file/未知工具回归 |
| `acceptance_cases.md` | 生物学解释的人工/后续模型评测案例，尚未自动执行 |

`support.py` 中的来源是假想的**归一化适配器接口**，不是 UniProt、Open Targets
或 Europe PMC 原始 API 响应。所有 TEST_* ID、PMID、DOI、疾病和机制陈述均为合成数据；
不对应真实医学知识，不能当作检索报告展示或拿去查询数据库。

## 拟议生产 API

模块：`backend/app/agent/rag.py`（也可以由同名 package 导出以下函数）。
本轮不创建空函数或占位实现。测试通过延迟导入给出清晰的缺失功能断言，
不使用 skip、expectedFailure 或恒定返回的假实现。其他依赖缺失仍作为 ERROR 暴露。

### 1. `load_candidates`

```python
load_candidates(path, *, context, columns, fdr_max, min_abs_log2fc) -> dict
```

- 显式传入列映射；第一版只支持以 log2 fold change 为效应量的差异表。
- 最少需要 context 中的 `species_taxid`、`entity_type`、`id_namespace`、`omics`、
  `contrast`（按比较组、参考组排序的两个元素）、`analysis_type`。
- tissue/disease 可为空，表示未知，禁止猜测。cell_type 优先取每行；缺失时保留未知。
- 必需列或必需背景缺失时抛出 `ValueError`；表内 `contrast` 与 context 冲突时同样拒绝。
- 对已有输出，文本 contrast 是 `"case vs control"`；只接受与显式 context 一致的值。
- 选择规则：`padj <= fdr_max` 且 `abs(log2FC) >= min_abs_log2fc`，阈值边界包含。
  FDR 阈值必须有限且在 [0, 1] 内，效应阈值必须有限且非负。
- 不使用原始 P 值替代校正后的 P 值；NaN/Inf/缺失/越界统计值不能进入候选。
- 不修改原始文件，也不在这里增加 Top K 截断；每行保留独立的组织/细胞/比较背景。
- 返回 `{"candidates": [...], "excluded": [...]}`，顺序与原表一致。
  `excluded` 至少含 `input_id`、`result_ref`、`reason`。
  reason 为 `fdr`、`effect_size` 或 `invalid_statistics`，无效值先于阈值判断。
- candidate 的规范结构见 `support.candidate()`；`result_ref.row` 是一基 CSV/TSV
  逻辑记录序号，表头为 1，首条数据为 2；path 保留传入路径的字符串表示。
  effect_measure 固定为 `log2_fold_change`；direction 为 up/down/unchanged。
- 探索性 Seurat 结果必须保留 `exploratory_cell_level_pseudoreplication_risk` 标签；
  不能添加推断的样本数，也不能升级成样本级或因果证据。

当前 R 实现实际产生的伪 bulk 文件为 `05_pseudobulk_edgeR_by_celltype.csv`，
与 module registry 声明的 `06_pseudobulk_DE_*.csv` 不一致。本轮按显式路径和实际
`logFC/FDR` 字段测试，不修改这个既有问题。Seurat 使用 `avg_log2FC/p_val_adj`。

### 2. `resolve_entity`

```python
resolve_entity(candidate, matches) -> dict
```

matches 是来源适配器返回的标准化实体列表，记录格式见 `support.entity()`。
先按 species_taxid 和 entity_type 限定，再匹配相同 namespace 的精确 canonical_id，
否则按 symbol/alias 精确匹配。第一版不做模糊文本替代、不跨物种映射、不合并蛋白异构体。
同一标准 ID 的重复记录不形成歧义。

返回包含 `status`、`entity`、`matches` 的 dict：

- `resolved`：唯一匹配，entity 是记录。
- `ambiguous`：多个不同实体，entity 为 None，matches 保留供用户辨别的候选。
- `not_found`：没有匹配，entity 为 None。

仅 resolved 的实体才能进入证据检索；把 entity 字段附加到 candidate，保留原 input_id。

### 3. `collect_evidence`

```python
async collect_evidence(candidate, *, sources) -> dict
```

candidate 必须带已解析 entity。sources 是具有唯一 `name` 和异步
`search(candidate) -> list[normalized_record]` 的适配器对象。
归一化记录格式见 `support.evidence()`；来源适配器不能生成无来源的机制结论。
collect_evidence 测试运行真实聚合逻辑，只替换外部来源边界。

返回至少包含：

```text
status: ok | partial | no_evidence | error
candidate: 完整原始 candidate（不原地修改）
evidence: 带 evidence_id、claim、evidence_type、relation_to_result、sources 的记录
source_status: {source_name: {status: ok | error, error?: str}}
independent_publications: 去重后的被接纳证据关联论文数
rejected: 被排除记录及 reason
```

- 所有源成功且有证据：ok；全部成功但没有可用证据：no_evidence。
- 一部分来源失败：partial，哪怕成功的来源也没有命中。
- 全部来源失败：error，不能解释成“生物学上不存在关联”。
- asyncio.CancelledError 必须继续向上传递，不转成 no_evidence 或 error。
- 拒绝错误实体/物种及缺失来源的记录，分别标为 entity_mismatch/species_mismatch/
  missing_provenance；rejected 中保留原记录，避免无痕丢弃。
- source 至少保存 database、record_id、url、retrieved_at；有版本时保存 version，
  没有版本时可为 None。PMID/DOI 可为空，数据库注释本身是合法来源，不能伪造论文。
- 接纳的证据保留原 claim、证据类型和研究背景；tissue/cell_type 与当前候选明确
  不匹配的，标为 background，并列出 context_mismatches；未知背景不等于匹配。
- sources 是原 source 记录列表。同一论文、相同实体/物种/陈述/证据类型/关系/背景
  的重复项合并来源。不同陈述、冲突、方向或实验背景不能因为 PMID 相同而丢失。
- DOI 身份比较去除 DOI URL 前缀并忽略大小写；原始引用记录保留。
  independent_publications 按共享 PMID 或归一化 DOI 识别论文，不按数据库数量计数；
  没有论文标识的数据库注释不计入论文数。标识完全不相交时不能猜测是同一篇论文。
- source_score 保留原有种类与值；不改名为 confidence 或 causal_probability。
- evidence_id 在同一响应中唯一，供报告绑定引用；返回结果须能严格 JSON 序列化。

### 4. Agent 工具边界

`TOOL_SCHEMAS` 新增 `retrieve_biomedical_evidence(candidate)`，对应异步
`ToolContext.retrieve_biomedical_evidence` handler。candidate 为含分析背景和已解析
entity 的对象；未解析、歧义实体必须在前一步处理。

分发测试只验证真实 `ToolContext.execute` 是否按参数调用 handler、是否完整返回结果；
它不宣称已验证 LLM 阅读、实际数据库连接、报告生成或 SSE 展示。

## 后续验证与限制

按用户要求，本轮停在 TDD RED。新增功能未实现导致的 FAIL 是预期状态，不能称作测试通过。
两个既有工具回归应 PASS；测试发现/环境问题应修复，不能冒充功能缺失。
完成实现后须重跑，最终要求所有自动化用例通过。

下一阶段还需要：真实数据库响应快照的适配器契约测试（含限流和分页）、Agent 完整
tool_use/tool_result 循环、落盘与前端显示，以及 `acceptance_cases.md` 的解释评测。
缓存、Top K 排序、富集统计输入和其他组学专用标识符在本轮没有实现或测试。
