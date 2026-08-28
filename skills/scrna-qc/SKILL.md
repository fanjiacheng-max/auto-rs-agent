---
name: scrna-qc
description: Run quality control on single-cell RNA-seq data with automatic parameter sweep. Tries multiple MAD threshold and mitochondrial cutoff combinations, selects the configuration with highest cell retention rate. Reads existing sweep results from status.json to avoid redundant runs.
---

# scRNA-seq Quality Control with Parameter Sweep

## Purpose
Run QC and automatically select the best parameters by sweeping `qc.nmads` × `qc.max_percent_mt` combinations. All attempts are recorded in `status.json` to avoid re-running.

## Prerequisites
- Project bootstrapped and config.R generated (scrna-configure completed)
- Config file at `{workspace}/scrna_project/config/analysis.R`

## Parameter sweep protocol

### Step 1: Check already-tried parameters
Read `{workspace}/status.json` → `tried_params.qc`. For each entry, note the combination and its `cell_retention_rate`.

Combinations to sweep (9 total):
- nmads: 2.5, 3.0, 3.5
- max_percent_mt: null (MAD-only), 20, 25

Skip any combination already recorded in `tried_params.qc`.

### Step 2: For each untried combination

**2a. Write a QC-only config variant:**

```python
# Run this inline to create per-sweep config
import re, shutil

base = "{workspace}/scrna_project/config/analysis.R"
sweep_config = "{workspace}/scrna_project/config/qc_sweep_{nmads}_{pct}.R"
shutil.copy(base, sweep_config)

with open(sweep_config) as f:
    content = f.read()

# Enable only QC, disable everything else
for module in ["integration", "annotation", "markers", "differential",
               "composition", "enrichment", "pathway_scores",
               "pseudotime", "cellchat", "hdwgcna"]:
    content = re.sub(
        rf'({module}\s*=\s*list\([^)]*?enabled\s*=\s*)TRUE',
        r'\1FALSE', content, flags=re.DOTALL
    )

# Set QC parameters
content = re.sub(r'(qc\s*=\s*list\([^)]*?enabled\s*=\s*)FALSE', r'\1TRUE', content, flags=re.DOTALL)
content = re.sub(r'(nmads\s*=\s*)[\d.]+', f'\\g<1>{nmads}', content)
if pct is None:
    content = re.sub(r'(max_percent_mt\s*=\s*)[^,\n)]+', r'\1NULL', content)
else:
    content = re.sub(r'(max_percent_mt\s*=\s*)[^,\n)]+', f'\\g<1>{pct}', content)

with open(sweep_config, "w") as f:
    f.write(content)
```

**2b. Run QC:**

```bash
cd {workspace}/scrna_project && Rscript run_pipeline.R config/qc_sweep_{nmads}_{pct}.R
```

**2c. Read retention rate:**

```python
import csv, statistics

summary_file = "{workspace}/scrna_project/results/tables/01_QC_summary_by_sample.csv"
with open(summary_file) as f:
    rows = list(csv.DictReader(f))

# retention = cells_after / cells_before, averaged across samples
rates = []
for row in rows:
    before = float(row.get("cells_before_qc", 0) or row.get("n_cells_before", 0))
    after = float(row.get("cells_after_qc", 0) or row.get("n_cells", 0))
    if before > 0:
        rates.append(after / before)

retention_rate = statistics.mean(rates) if rates else 0.0
print(f"Retention rate for nmads={nmads}, max_pct_mt={pct}: {retention_rate:.3f}")
```

**2d. Record attempt in status.json:**

```python
import json
from datetime import datetime, timezone

status_path = "{workspace}/status.json"
with open(status_path) as f:
    state = json.load(f)

state.setdefault("tried_params", {}).setdefault("qc", [])
state["tried_params"]["qc"].append({
    "nmads": {nmads},
    "max_percent_mt": {pct},
    "cell_retention_rate": retention_rate,
    "selected": False,
    "run_id": "{run_id}",
    "tried_at": datetime.now(timezone.utc).isoformat()
})
state["last_updated"] = datetime.now(timezone.utc).isoformat()

with open(status_path, "w") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)
```

### Step 3: Select best parameters

After all combinations are tried, identify the entry in `tried_params.qc` with the highest `cell_retention_rate`.

```python
import json

with open("{workspace}/status.json") as f:
    state = json.load(f)

attempts = state["tried_params"]["qc"]
best = max(attempts, key=lambda a: a["cell_retention_rate"])

# Mark best as selected
for a in attempts:
    a["selected"] = (a is best)

state["last_updated"] = datetime.now(timezone.utc).isoformat()
with open("{workspace}/status.json", "w") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)

print(f"Best QC params: nmads={best['nmads']}, max_percent_mt={best['max_percent_mt']}, retention={best['cell_retention_rate']:.3f}")
```

### Step 4: Apply best parameters to main config

Update `{workspace}/scrna_project/config/analysis.R` with the winning nmads and max_percent_mt values.

### Step 5: Run final QC with best parameters

```bash
cd {workspace}/scrna_project && Rscript run_pipeline.R config/analysis.R
```

### Step 6: Review checkpoint outputs
Check:
- `results/tables/01_QC_summary_by_sample.csv` — per-sample retention
- `results/figures_pdf/` — QC violin plots

Report cell counts before/after QC to the user.

## Notes
- If all 9 combinations have already been tried (found in `tried_params.qc`), skip the sweep and go directly to Step 4 with the best recorded params.
- Retain all sweep config files for debugging but final analysis uses `config/analysis.R`.

## References
- Guardrails: `skills/geo-scrna-workflow/references/scientific-guardrails.md`
