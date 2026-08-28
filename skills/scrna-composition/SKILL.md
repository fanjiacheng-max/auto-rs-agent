---
name: scrna-composition
description: Analyse cell type composition changes between groups in single-cell RNA-seq data. Computes per-sample proportions and runs a Wilcoxon test (exploratory). Requires reviewed annotation and confirmed contrast groups.
---

# scRNA-seq Cell Composition Analysis

## Prerequisites
- Annotation reviewed
- Contrast confirmed

## Steps

### 1. Enable composition

Set `composition$enabled = TRUE` and `composition$contrast = c("{case}", "{control}")` in config.

### 2. Run pipeline

```bash
cd {workspace}/scrna_project && Rscript run_pipeline.R config/analysis.R
```

### 3. Report
Present composition proportions per group. Note that Wilcoxon results are exploratory only — for complex designs recommend a compositional model.
