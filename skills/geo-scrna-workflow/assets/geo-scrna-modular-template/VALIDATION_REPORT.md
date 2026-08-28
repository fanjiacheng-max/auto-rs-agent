# Template status and validation scope

This project is a reusable analysis template and decision guide. It has not been validated against every Seurat, Bioconductor, CellChat, hdWGCNA, input-format, tissue, or experimental-design combination.

## Design guarantees

- Analysis stages use explicit `object`, `cfg`, and `ctx` interfaces.
- Input assumptions and sample metadata are surfaced for review.
- H5AD raw-count layers are explicit rather than inferred silently.
- Sample-aware QC, adaptive PCA selection, and guarded batch correction are configurable.
- Formal group DE is sample-level pseudobulk and reports ineligible cell types.
- Automated annotation remains provisional until a reviewed mapping is supplied.
- Optional high-risk modules are disabled by default.

## User responsibility

Before interpreting a real dataset, review sample identities, group assignments, raw-count provenance, gene identifiers, QC retention, annotation markers, replicate structure, and every enabled advanced module. Package-level behavior depends on the target R environment and installed versions.

The included preflight and smoke scripts are optional diagnostics for users who want runtime checks; they are not a substitute for biological review or dataset-specific validation.
