module_packages <- function() {
  list(
    core = c("Seurat", "Matrix", "ggplot2"),
    geo = c("GEOquery"),
    doublet = c("SingleCellExperiment", "SummarizedExperiment", "scDblFinder"),
    harmony = c("harmony"),
    h5ad = c("zellkonverter", "SummarizedExperiment"),
    loom = c("SeuratDisk"),
    annotation = c("SingleR", "celldex", "SummarizedExperiment"),
    pseudobulk = c("edgeR", "limma"),
    enrichment = c("clusterProfiler"),
    slingshot = c("SingleCellExperiment", "SummarizedExperiment", "slingshot"),
    monocle3 = c("SummarizedExperiment", "monocle3"),
    cellchat = c("CellChat"),
    hdwgcna = c("hdWGCNA", "WGCNA")
  )
}

has_package <- function(pkg) requireNamespace(pkg, quietly = TRUE)

require_packages <- function(packages, module, optional = FALSE, ctx = NULL) {
  missing <- packages[!vapply(packages, has_package, logical(1))]
  if (!length(missing)) return(TRUE)
  msg <- paste0("Missing package(s) for ", module, ": ", paste(missing, collapse = ", "))
  if (!is.null(ctx)) log_msg(ctx, msg, level = if (optional) "WARN" else "ERROR")
  if (!optional) stop(msg, call. = FALSE)
  FALSE
}

validate_environment <- function(cfg, ctx) {
  require_packages(module_packages()$core, "core pipeline", optional = FALSE, ctx = ctx)
  optional_checks <- list(
    doublet = isTRUE(cfg$qc$run_doublet),
    harmony = identical(cfg$integration$batch_method, "harmony"),
    annotation = isTRUE(cfg$annotation$use_singler),
    pseudobulk = isTRUE(cfg$differential$pseudobulk),
    enrichment = isTRUE(cfg$enrichment$enabled),
    slingshot = isTRUE(cfg$pseudotime$enabled) && identical(cfg$pseudotime$method, "slingshot"),
    monocle3 = isTRUE(cfg$pseudotime$enabled) && identical(cfg$pseudotime$method, "monocle3"),
    cellchat = isTRUE(cfg$cellchat$enabled),
    hdwgcna = isTRUE(cfg$hdwgcna$enabled)
  )
  for (nm in names(optional_checks)) {
    if (isTRUE(optional_checks[[nm]])) require_packages(module_packages()[[nm]], nm, optional = TRUE, ctx = ctx)
  }
  invisible(TRUE)
}
