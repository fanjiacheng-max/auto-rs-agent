# Data-adaptive scRNA-seq pipeline in R

This template runs a modular Seurat workflow for GEO or local scRNA-seq data. It keeps input assumptions, biological metadata, automated labels, and formal statistical comparisons explicit.

## First run

1. Inspect the data with the skill-level `scripts/inspect_input.py`.
2. Review a sample sheet with at least `sample,group` for formal comparisons.
3. Copy `config/example_config.R` and replace every example value.
4. Run preflight from the skill directory.
5. Run:

```bash
Rscript run_pipeline.R config/my_config.R
```

## Supported inputs

- 10x Matrix Market directories and 10x H5
- H5AD with an explicit raw-count assay
- loom
- Seurat or SingleCellExperiment RDS/RData
- gene-by-cell or cell-by-gene dense text matrices

## Data-adaptive behavior

- Embedded sample metadata in Seurat objects is preserved.
- Generic Cell Ranger folders use their parent directory as the candidate sample name.
- QC thresholds are calculated within samples.
- PCA dimensions are selected from explained variance when `integration.dims = NULL`.
- Automatic Harmony is disabled when batch metadata is missing or confounded with group.
- Formal DE is sample-level edgeR pseudobulk with optional sample-level covariates.
- Rat and zebrafish require custom annotation markers and pathway signatures.

## Required review files

- `results/tables/00_sample_sheet_review.csv`
- `results/tables/01_QC_summary_by_sample.csv`
- `results/tables/02_integration_decisions.csv`
- `results/tables/02_cluster_annotation_review.csv`
- `results/tables/05_pseudobulk_eligibility.csv`
- `results/reports/module_status.csv`

## Validation

```bash
python tools/static_check.py
Rscript tests/smoke_parse.R
Rscript tests/smoke_config.R
```

Package-level and real-data execution still require a configured R/Bioconductor environment.
