---
name: scrna-annotation
description: Annotate cell types in single-cell RNA-seq data using SingleR reference and/or tissue-specific marker genes. Generates provisional labels that must be reviewed before formal downstream analysis. Requires integration to be completed first.
---

# scRNA-seq Cell Type Annotation

## Purpose
Generate provisional cell type labels using SingleR and/or custom marker scoring. Labels are marked `provisional_auto` until reviewed.

## Prerequisites
- Integration completed (checkpoint `03_integrated` exists)
- Species confirmed in config (required for SingleR reference selection)

## Steps

### 1. Optionally provide tissue-specific markers

If the user has a marker file (CSV with columns `celltype,gene`), set in config:
```
annotation$marker_file = "/path/to/markers.csv"
```

For standard human/mouse tissues, built-in markers are used automatically.

### 2. Enable annotation, disable downstream modules

Ensure `annotation$enabled = TRUE`. Keep QC and integration enabled (for cache reuse).

### 3. Run pipeline through annotation

```bash
cd {workspace}/scrna_project && Rscript run_pipeline.R config/analysis.R
```

### 4. Present annotation review table

Read and summarise `results/tables/02_cluster_annotation_review.csv`:
- Cluster → provisional label mapping
- Top marker genes per cluster
- SingleR score confidence

Inform the user that **labels are provisional** and must be reviewed before:
- Formal differential expression
- CellChat
- Pseudotime
- hdWGCNA

The user must provide a reviewed annotation CSV (`seurat_cluster,celltype`) and set `annotation$external_annotation_file` before running those modules.

## References
- `skills/geo-scrna-workflow/references/scientific-guardrails.md`
