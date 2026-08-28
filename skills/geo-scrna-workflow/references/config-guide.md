# Configuration guide

## Project and input

- `project.gse`: GEO accession. Leave `NULL` for local data.
- `project.project_name`: stable project/output name.
- `project.species`: required; `human`, `mouse`, `rat`, or `zebrafish`.
- `project.work_root`: parent output directory.
- `project.input_dir`: local file collection. It is mutually exclusive with `project.gse`.
- `project.sample_sheet`: reviewed CSV with `sample` and `group`. Extra sample-level fields are propagated.
- `input.assay`: preferred RNA assay; the active assay is used when this name is absent.
- `input.feature_type`: 10x feature type, normally `Gene Expression`.
- `input.sample_column` / `input.group_column`: metadata fields in Seurat/SCE inputs.
- `input.matrix_orientation`: `auto`, `gene_by_cell`, or `cell_by_gene` for dense matrices.
- `input.h5ad_counts_layer`: H5AD assay containing raw counts.
- `input.allow_h5ad_x_as_counts`: keep false unless `X` has been verified as raw count-like values.
- `input.fingerprint_mode`: `size_mtime` is efficient; use `md5` when strict content identity is required.

## QC

- `qc.nmads`: sample-aware MAD multiplier; start at 3 and inspect distributions.
- `qc.max_percent_mt`: optional hard cap justified by tissue and protocol.
- `qc.run_doublet`: runs scDblFinder per sample when dependencies are available.
- `qc.min_cells_after_qc`: global minimum after filtering.
- `qc.min_cells_per_sample_after_qc`: per-sample design safeguard.
- `qc.fail_on_sample_loss`: stop rather than silently alter the sample design.

## Normalization and integration

- `integration.use_sctransform`: false uses log normalization; true uses SCTransform.
- `integration.dims`: use `NULL` for data-adaptive PC selection or an explicit integer vector after review.
- `integration.max_npcs`: upper limit for PCA and automatic selection.
- `integration.variance_target`: cumulative PCA variance target used when `dims = NULL`.
- `integration.batch_method`: `auto`, `harmony`, or `none`.
- `integration.batch_variable`: reviewed technical batch field. Default is `batch`, not `sample`.
- `integration.resolution`: tune using cluster stability and marker coherence, not UMAP appearance alone.

`auto` avoids Harmony when the batch field is missing, has one level, or is trivially confounded with group. Explicit `harmony` is an informed override.

## Annotation and markers

- `annotation.marker_file`: optional CSV with `celltype,gene` for tissue-specific marker scoring.
- `annotation.external_annotation_file`: reviewed CSV with `seurat_cluster,celltype`.
- `annotation.use_singler`: built-in reference labeling for human or mouse.
- `annotation.accept_auto_labels`: keep false until cluster-level review.
- `markers.min_pct` and `markers.logfc_threshold`: cluster marker filters.

Rat and zebrafish have no built-in annotation fallback in this template. Supply explicit marker resources.

## Differential analysis

- `differential.pseudobulk`: formal sample-level comparison.
- `differential.exploratory_cell_level`: pseudoreplicated cell-level comparison; disabled by default.
- `differential.contrast`: test group followed by reference group.
- `differential.covariates`: sample-level fixed effects such as donor, sex, or technical batch.
- `differential.min_samples_per_group`: default 3.
- `differential.min_cells_per_sample_celltype`: minimum cells contributing to each pseudobulk sample.

The pipeline skips rank-deficient, incomplete, or under-replicated designs and records the reason.

## Pathways and advanced modules

- `pathway_scores.signature_file`: GMT or CSV with `signature,gene`.
- `pseudotime.enabled`: requires explicit `celltypes` and `root_cluster`.
- `cellchat.enabled`: enable only after annotation review.
- `hdwgcna.enabled`: requires explicit `target_celltypes` and adequate sample coverage.

## Cache and output

- `output.force_recompute`: invalidate all stage checkpoints for an intentional rerun.
- `output.checkpoint_version`: change after output-schema or algorithm changes.
- `output.stop_on_critical_failure`: keep true for intake, QC, integration, and export.
