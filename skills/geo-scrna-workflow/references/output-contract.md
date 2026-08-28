# Output contract

## Required run summary

Report:

- Input source and detected formats.
- Species, sample count, cell count before and after QC.
- Group counts and biological replicate counts.
- Batch method and clustering parameters.
- Annotation status: provisional or reviewed.
- Enabled modules and module status.
- Formal contrast and whether pseudobulk prerequisites were met.
- Warnings, fallbacks, and failed modules.

## Required files to surface

Prioritize:

- Final Seurat object or checkpoint path.
- `results/reports/module_status.csv`
- `results/reports/parameters.csv`
- `results/tables/00_sample_sheet_review.csv`
- `results/tables/01_QC_summary_by_sample.csv`
- `results/tables/02_cluster_annotation_review.csv`
- Pseudobulk DE table when available.
- Key UMAP and QC PDFs.

## Interpretation wording

Use precise labels:

- `provisional auto-annotation`
- `exploratory cell-level differential expression`
- `sample-level pseudobulk differential expression`
- `predicted ligand-receptor communication`
- `inferred pseudotime ordering`
- `coexpression module`

Do not call a module successful solely because the pipeline continued. Base success on module status and non-empty validated outputs.

## Final response structure

1. **Run status** — completed, partially completed, or blocked.
2. **Data and design** — samples, groups, cells, batch structure.
3. **Completed modules** — concise list with key outputs.
4. **Warnings requiring review** — scientific or technical limitations.
5. **Artifacts** — links to the project, configuration, logs, and result bundle.
