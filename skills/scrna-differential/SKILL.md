---
name: scrna-differential
description: Run pseudobulk differential expression analysis between two groups in single-cell RNA-seq data using edgeR. Requires reviewed annotation and confirmed contrast groups. Also runs exploratory cell-level DE and checks pseudobulk eligibility per cell type.
---

# scRNA-seq Differential Expression

## Prerequisites
- Annotation reviewed
- Contrast groups confirmed (e.g. Disease vs Control) — must match actual group labels in data
- Minimum 3 samples per group per cell type for pseudobulk eligibility

## Steps

### 1. Verify contrast in config

Check `differential$contrast` in `config/analysis.R`. It must match actual group names from the sample sheet (case-sensitive).

### 2. Enable differential module

`differential$pseudobulk = TRUE` (default — do not disable)
`differential$exploratory_cell_level = FALSE` (keep disabled unless explicitly requested)

For paired designs, set `differential$covariates = c("donor")` or equivalent.

### 3. Run pipeline

```bash
cd {workspace}/scrna_project && Rscript run_pipeline.R config/analysis.R
```

### 4. Review outputs

Read and summarise:
- `results/tables/05_pseudobulk_eligibility.csv` — which cell types have adequate replication
- `results/tables/06_pseudobulk_DE_*.csv` — DE results per eligible cell type
- `results/tables/04_DE_exploratory_cell_level.csv` — exploratory only, label as such

**Warn the user** if fewer than 3 samples per group in any cell type — pseudobulk will be skipped for that cell type.

## References
- `skills/geo-scrna-workflow/references/scientific-guardrails.md`
- `skills/geo-scrna-workflow/references/output-contract.md`
