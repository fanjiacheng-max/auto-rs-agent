# Troubleshooting

## No supported inputs detected

- Confirm archives were extracted or enable archive decompression.
- Confirm a 10x directory contains matrix, feature or gene, and barcode sidecars in the same directory.
- Confirm H5 filenames contain a recognizable matrix-related term.
- Confirm dense files are gene-by-cell matrices with gene identifiers in the first column.

## Sample-sheet mismatch

Compare names in `00_detected_input_specs.csv` with the `sample` column. Rename sheet entries or adjust input filenames/directories; do not silently fuzzy-match biological samples.

## Seurat v5 layer errors

Use the provided `get_assay_layer` and `JoinLayers` compatibility helpers. Do not patch the SeuratObject namespace.

## Harmony unavailable

Install `harmony` or set `integration.batch_method = "none"`. Report that no batch correction was applied.

## SingleR or celldex unavailable

Continue with marker-score candidates only and mark annotations provisional. Do not treat missing reference annotation as a pipeline-wide failure.

## Pseudobulk skipped

Check:

- At least two groups are present.
- Each group has enough independent samples.
- Each sample-cell-type stratum meets the minimum cell count.
- `sample` and `group` metadata are correct.

## Pseudotime blocked

Specify target cell types and root cluster. Verify the subset contains enough cells and a connected trajectory. Do not bypass the gate by choosing the largest cluster arbitrarily.

## CellChat memory issues

Reduce maximum cell types, cells per cell type, or total cells while keeping stratified representation. Run group-specific analyses separately.

## hdWGCNA failure

Check target-cell-type sample coverage, normalized data availability, metacell size, and package compatibility. Prefer a supported hdWGCNA and Seurat version combination rather than namespace monkey-patching.

## Stale output suspected

Set `output.force_recompute = TRUE` or change `output.checkpoint_version`. Confirm the config and upstream input fingerprints changed as expected.
