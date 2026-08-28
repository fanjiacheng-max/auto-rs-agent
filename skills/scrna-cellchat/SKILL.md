---
name: scrna-cellchat
description: Infer cell-cell communication potential using CellChat on single-cell RNA-seq data. Requires reviewed (non-provisional) cell type annotation. Reports ligand-receptor interactions between cell types.
---

# scRNA-seq Cell-Cell Communication (CellChat)

## Prerequisites
- Annotation reviewed and accepted (not provisional)
- Minimum 30 cells per cell type
- At least 2 distinct cell types

## Steps

### 1. Configure

```r
cellchat$enabled = TRUE
cellchat$min_cells = 30
cellchat$max_celltypes = 18
cellchat$max_cells_per_celltype = 700
```

For specific database categories (e.g. `"Secreted Signaling"`):
```r
cellchat$database_category = c("Secreted Signaling")
```

### 2. Run pipeline

```bash
cd {workspace}/scrna_project && Rscript run_pipeline.R config/analysis.R
```

### 3. Report
Summarise top interactions from `results/tables/cellchat_*.csv`.

**Important:** CellChat predicts *communication potential* from expression — it does not demonstrate physical interaction or signaling flux.

## References
- `skills/geo-scrna-workflow/references/scientific-guardrails.md`
