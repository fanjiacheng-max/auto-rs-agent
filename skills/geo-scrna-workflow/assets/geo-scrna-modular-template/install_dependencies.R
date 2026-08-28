cran_packages <- c(
  "Seurat", "Matrix", "data.table", "ggplot2", "patchwork", "dplyr", "tidyr",
  "stringr", "tibble", "ggrepel", "pheatmap", "R.utils", "harmony", "WGCNA"
)
bioc_packages <- c(
  "SingleCellExperiment", "SummarizedExperiment", "SingleR", "celldex", "GEOquery",
  "scDblFinder", "clusterProfiler", "org.Hs.eg.db", "org.Mm.eg.db", "monocle3",
  "slingshot", "edgeR", "limma", "zellkonverter", "ComplexHeatmap"
)
missing_cran <- cran_packages[!vapply(cran_packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing_cran)) install.packages(missing_cran, repos = "https://cloud.r-project.org")
if (!requireNamespace("BiocManager", quietly = TRUE)) install.packages("BiocManager", repos = "https://cloud.r-project.org")
missing_bioc <- bioc_packages[!vapply(bioc_packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing_bioc)) BiocManager::install(missing_bioc, ask = FALSE, update = FALSE)
message("CellChat and hdWGCNA are intentionally not auto-installed because their installation depends on the target environment and version constraints.")
