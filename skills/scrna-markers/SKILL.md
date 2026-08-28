---
name: scrna-markers
description: Find marker genes for each cell type in a single-cell RNA-seq dataset using FindAllMarkers. Requires reviewed cell type annotation.
---

# scRNA-seq Marker Gene Discovery

## Prerequisites
- Annotation completed and reviewed (`external_annotation_file` set in config or `accept_auto_labels = TRUE`)

## Steps

### 1. Enable markers module

Set `markers$enabled = TRUE` in config. Recommended settings:
- `markers$min_pct = 0.25`
- `markers$logfc_threshold = 0.25`
- `markers$only_positive = TRUE`

### 2. Run pipeline

```bash
cd {workspace}/scrna_project && Rscript run_pipeline.R config/analysis.R
```

### 3. Report
Read `results/tables/03_celltype_markers.csv` and summarise top markers per cell type.
