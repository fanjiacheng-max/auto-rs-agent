# Legacy-to-module map

| Legacy section | New module | Main changes |
|---|---|---|
| CONFIG / ENV SETUP | `config/*.R`, `R/01_context.R` | Nested configuration; no global output paths |
| PACKAGE UTILS | `R/02_packages.R` | Explicit module dependency checks; no automatic package installation during analysis |
| GENERAL UTILS | `R/00_utils.R`, `R/01_context.R` | Context object, status log, configuration-aware cache key |
| GEO METADATA / DATA READING / MAIN BUILD | `R/03_io.R` | Sample sheet is authoritative; automatic disease/control assignment removed |
| QC MODULE | `R/04_qc.R` | Batch-aware MAD QC retained; minimum remaining-cell guard added |
| NORMALIZE / INTEGRATE | `R/05_integration.R` | Integration method isolated behind configuration |
| ANNOTATION | `R/06_annotation.R` | Auto labels are explicitly marked provisional; review table exported |
| MARKERS / DE / PSEUDOBULK | `R/07_differential.R` | Cell-level DE labeled exploratory; pseudobulk is the formal default |
| CELL COMPOSITION | `R/08_composition.R` | Sample-level proportions retained; test labeled exploratory |
| ENRICHMENT | `R/09_enrichment.R` | Uses pseudobulk results by default |
| PATHWAY SCORES | `R/10_pathway_scores.R` | Curated signatures isolated from pipeline orchestration |
| ADVANCED PSEUDOTIME | `R/11_pseudotime.R` | Requires explicit lineage and root; Monocle2 removed from default implementation |
| CELLCHAT | `R/12_cellchat.R` | Explicit optional module with bounded downsampling |
| hdWGCNA | `R/13_hdwgcna.R` | No namespace monkey-patching; explicit target cell types required |
| FINAL EXPORT | `R/14_export.R` | Final object, result bundle, session info, and status report separated |
| Top-level statements | `R/99_pipeline.R`, `run_pipeline.R` | One orchestrator with dependency-aware checkpoints |
