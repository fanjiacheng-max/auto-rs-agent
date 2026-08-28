---
name: scrna-pathway-scores
description: Compute gene signature pathway scores for all cells in single-cell RNA-seq data. Can use built-in curated signatures or a custom GMT/CSV file. Requires integration (not annotation) — can run in parallel with annotation.
---

# scRNA-seq Pathway Scores

## Prerequisites
- Integration completed (`03_integrated` checkpoint exists)
- Optional: custom signature file (GMT or CSV with `signature,gene` columns)

## Steps

### 1. Configure

Set `pathway_scores$enabled = TRUE` in config.

For custom signatures:
```
pathway_scores$signature_file = "/path/to/signatures.csv"
```

### 2. Run pipeline

```bash
cd {workspace}/scrna_project && Rscript run_pipeline.R config/analysis.R
```

### 3. Report
Summarise computed signature scores from `results/tables/pathway_scores_*.csv`.
