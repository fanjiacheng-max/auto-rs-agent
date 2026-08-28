---
name: scrna-enrichment
description: Run Gene Ontology and pathway enrichment analysis on pseudobulk differential expression results from single-cell RNA-seq data. Requires differential expression to be completed first.
---

# scRNA-seq Pathway Enrichment

## Prerequisites
- Differential expression completed (`06_differential` checkpoint exists)

## Steps

### 1. Enable enrichment

Set `enrichment$enabled = TRUE` in config. Default settings:
- `enrichment$ontology = "BP"` (Biological Process)
- `enrichment$p_adjust_cutoff = 0.05`
- `enrichment$logfc_cutoff = 0.25`
- `enrichment$min_genes = 10`

To also compute pathway scores: set `pathway_scores$enabled = TRUE` (runs on all cells, not just DE results).

### 2. Run pipeline

```bash
cd {workspace}/scrna_project && Rscript run_pipeline.R config/analysis.R
```

### 3. Report
Summarise top enriched pathways per cell type from `results/tables/07_enrichment_*.csv`.

**Note:** Describe enrichment results as *associations* — do not claim direct pathway activation without supporting evidence.
