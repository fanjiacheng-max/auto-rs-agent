---
name: scrna-hdwgcna
description: Build a co-expression gene network using hdWGCNA on a specified cell type subset from single-cell RNA-seq data. Identifies gene modules and hub genes. Requires reviewed annotation and user-specified target cell types.
---

# scRNA-seq Co-expression Network (hdWGCNA)

## Prerequisites
- Annotation reviewed
- User must specify target cell types (recommend ≥200 cells per type)

## Required inputs (ask user if not in status.json)
- `hdwgcna.target_celltypes`: which cell types to build the network on

## Steps

### 1. Configure

```r
hdwgcna$enabled = TRUE
hdwgcna$target_celltypes = c("{celltype1}")
hdwgcna$fraction = 0.05
hdwgcna$metacell_k = 25
hdwgcna$min_module_size = 30
hdwgcna$network_type = "signed"
```

Leave `soft_power = NULL` for automatic selection (inspect power plot output).

### 2. Run pipeline

```bash
cd {workspace}/scrna_project && Rscript run_pipeline.R config/analysis.R
```

### 3. Report
From `results/tables/hdwgcna_*.csv`:
- Module count and sizes
- Top hub genes per module

**Note:** Hub genes are network-central candidates, not automatically causal regulators.

## References
- `skills/geo-scrna-workflow/references/scientific-guardrails.md`
