---
name: scrna-pseudotime
description: Run pseudotime / trajectory analysis on a selected subset of cell types using Slingshot. Requires reviewed annotation, user-specified cell types for the lineage, and a biologically defined root cluster.
---

# scRNA-seq Pseudotime / Trajectory Analysis

## Prerequisites
- Annotation reviewed
- User must specify: target cell types for the trajectory AND root cluster (biology-driven, not automatic)

## Required inputs (ask user if not in status.json)
- `pseudotime.celltypes`: which cell types to include (e.g. `["HSC", "Progenitor", "Mature"]`)
- `pseudotime.root_cluster`: which cluster is the biological starting point

## Steps

### 1. Configure

```r
pseudotime$enabled = TRUE
pseudotime$celltypes = c("{celltype1}", "{celltype2}")
pseudotime$root_cluster = "{root_cluster_id}"
pseudotime$method = "slingshot"
pseudotime$max_cells = 12000
```

### 2. Run pipeline

```bash
cd {workspace}/scrna_project && Rscript run_pipeline.R config/analysis.R
```

### 3. Report
Summarise from `results/tables/pseudotime_*.csv` and figures. Note: pseudotime is an ordering, not chronological time. Discuss branch stability and biological interpretation.

## References
- `skills/geo-scrna-workflow/references/scientific-guardrails.md`
