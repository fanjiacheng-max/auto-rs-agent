# Adapting the workflow to your data

## 1. Establish the data contract

Record these fields before analysis:

| Field | Required decision |
|---|---|
| Species | Explicit human, mouse, rat, or zebrafish |
| Count source | Raw integer counts and their assay/layer |
| Sample identity | Independent biological replicate identifier |
| Group | Condition used in the formal contrast |
| Donor | Subject identifier for paired or repeated designs |
| Batch | Technical batch, not a synonym for condition |
| Tissue/context | Used to select marker and pathway resources |
| Gene IDs | Symbols versus Ensembl IDs and whether version suffixes are present |

Do not proceed to enrichment or annotation until gene identifiers are understood.

## 2. Input-specific decisions

### 10x directories and H5

The inspector derives a sample name from the parent of generic Cell Ranger folders such as `filtered_feature_bc_matrix`. Confirm these names in the generated sample sheet. For multi-feature matrices, `input.feature_type` defaults to `Gene Expression`.

### Seurat RDS and RData

Set `input.sample_column` and `input.group_column` to existing metadata fields when they differ from `sample` and `group`. Embedded sample identities are preserved; they are not replaced by the filename. Verify that the active assay contains raw counts.

### H5AD

Set `input.h5ad_counts_layer` to the assay containing raw counts. The workflow does not silently treat `X` as counts. Set `input.allow_h5ad_x_as_counts = TRUE` only after confirming that `X` is non-negative and integer-like.

### Dense CSV/TSV/TXT

Use `input.matrix_orientation = "gene_by_cell"` or `"cell_by_gene"` when known. `auto` only uses barcode-like identifiers as a conservative heuristic. Dense input can be memory-intensive; prefer sparse Matrix Market or H5 for large datasets.

## 3. Sample sheet

Required columns:

```text
sample,group
```

Recommended columns:

```text
sample,group,donor,batch,sex,library,chemistry
```

Each sample must occur once. Additional columns are propagated to cell metadata and can be used as pseudobulk covariates. If one file contains several samples, sample names must match the embedded metadata rather than the filename.

## 4. QC adaptation

Start with sample-aware MAD filtering. Review before/after distributions and the per-sample retention table. Set a hard mitochondrial cap only when supported by tissue, species, protocol, and observed distributions. A sample falling below `qc.min_cells_per_sample_after_qc` stops the run by default because silent sample loss changes the experimental design.

Do not relax thresholds to reach a target cell count. Investigate low-complexity libraries, ambient RNA, doublet rates, and sample-specific failures separately.

## 5. Normalization and integration

Leave `integration.dims = NULL` initially. The workflow selects PCs up to the configured explained-variance target and maximum. Review clustering stability and marker coherence before fixing a final range.

`batch_method = "auto"` runs Harmony only when the configured batch field exists, has multiple levels, and is not trivially confounded with group. Use `harmony` explicitly only after reviewing the design. For many studies, donor/sample variation is biological replication and should not automatically be removed.

## 6. Annotation

Built-in markers are broad lineage markers, not tissue-specific truth. Prefer a reviewed CSV:

```csv
celltype,gene
T_cell,CD3D
T_cell,TRAC
Endothelial,VWF
Endothelial,PECAM1
```

Review positive markers, negative markers, cluster-level expression, doublet-like co-expression, tissue context, and expected abundance. Apply final labels through a `seurat_cluster,celltype` mapping file.

## 7. Differential expression

Formal DE uses sample-level pseudobulk within each cell type. Default minimum replication is three samples per group. Add fixed-effect covariates such as `donor`, `sex`, or `batch` only when they are sample-level, complete, and identifiable. The pipeline reports rank-deficient or under-replicated cell types in `05_pseudobulk_eligibility.csv` instead of silently producing a table.

## 8. Pathways and advanced modules

Use a tissue- and species-appropriate GMT or `signature,gene` CSV for pathway scores. Enable pseudotime only for a coherent lineage with an explicit root. Enable CellChat only after annotation review. Enable hdWGCNA only for explicit target cell types with adequate cells and sample coverage.

## 9. First-run strategy

1. Run input inspection and review the sample sheet.
2. Run core intake, QC, normalization, PCA, clustering, and provisional annotation.
3. Review checkpoints and finalize labels.
4. Rerun with the external annotation mapping.
5. Inspect pseudobulk eligibility before interpreting DE.
6. Enable only the advanced modules needed for the biological question.
