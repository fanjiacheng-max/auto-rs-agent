---
name: scrna-integration
description: Run normalization, PCA, dimensionality reduction, batch correction (Harmony if needed), and clustering on single-cell RNA-seq data. Produces UMAP embeddings and cluster assignments. Requires QC to be completed first.
---

# scRNA-seq Normalization and Integration

## Purpose
Normalize counts, run PCA, integrate across batches (auto-select Harmony only when batch is not confounded with condition), cluster cells, and generate UMAP embeddings.

## Prerequisites
- QC completed (checkpoint `02_qc` exists in project)
- Config file at `{workspace}/scrna_project/config/analysis.R`

## Steps

### 1. Enable integration in config

Ensure `integration$enabled = TRUE` in `config/analysis.R`. Leave QC enabled to allow incremental execution. Disable advanced modules (annotation onward) to run only up to integration.

### 2. Run pipeline through integration

```bash
cd {workspace}/scrna_project && Rscript run_pipeline.R config/analysis.R
```

The pipeline uses `cache_run` checkpointing — QC will be skipped if already cached.

### 3. Review outputs
Check:
- `results/tables/02_integration_decisions.csv` — batch correction decisions
- `results/figures_pdf/` — UMAP and PCA plots

Report to user:
- Number of PCs selected
- Whether Harmony was applied and why
- Cluster count at current resolution

## Notes
- `batch_method = "auto"` prevents Harmony when batch is confounded with condition.
- To adjust clustering resolution, edit `integration$resolution` in config.R and re-run.

## References
- `skills/geo-scrna-workflow/references/scientific-guardrails.md`
