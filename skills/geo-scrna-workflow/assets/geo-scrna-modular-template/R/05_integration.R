choose_pca_dims <- function(object, cfg) {
  available <- ncol(Seurat::Embeddings(object, "pca"))
  if (!is.null(cfg$integration$dims)) {
    dims <- cfg$integration$dims[cfg$integration$dims <= available]
    if (length(dims) < 2L) stop("Configured integration.dims exceed available PCs")
    return(dims)
  }
  stdev <- object[["pca"]]@stdev
  cumulative <- cumsum(stdev^2) / sum(stdev^2)
  selected <- which(cumulative >= cfg$integration$variance_target)[1L]
  selected <- max(2L, min(selected, available, cfg$integration$max_npcs))
  seq_len(selected)
}

resolve_batch_method <- function(object, cfg, ctx) {
  requested <- cfg$integration$batch_method
  variable <- cfg$integration$batch_variable
  if (identical(requested, "none")) return("none")
  if (!variable %in% colnames(object@meta.data)) {
    if (identical(requested, "harmony")) stop("Harmony batch variable not found: ", variable)
    log_msg(ctx, "Auto batch correction disabled; variable not found: ", variable, level = "WARN")
    return("none")
  }
  levels <- unique(stats::na.omit(as.character(object@meta.data[[variable]])))
  if (length(levels) < 2L) return("none")
  confounded <- design_is_confounded(object@meta.data, variable, "group")
  if (identical(requested, "auto") && isTRUE(confounded)) {
    log_msg(ctx, "Auto batch correction disabled because ", variable, " is confounded with group", level = "WARN")
    return("none")
  }
  "harmony"
}

run_integration <- function(object, cfg, ctx) {
  assay <- resolve_assay(object, cfg$input$assay)
  object <- SeuratObject::`DefaultAssay<-`(object, value = assay)
  if (utils::packageVersion("Seurat") >= "5.0.0") object <- tryCatch(SeuratObject::JoinLayers(object), error = function(e) object)
  regress <- intersect(cfg$integration$regress_variables, colnames(object@meta.data))
  regress <- regress[vapply(object@meta.data[, regress, drop = FALSE], function(x) is.numeric(x) && stats::sd(x, na.rm = TRUE) > 0, logical(1))]
  if (isTRUE(cfg$integration$use_sctransform)) {
    object <- Seurat::SCTransform(object, vars.to.regress = regress, verbose = FALSE)
  } else {
    object <- Seurat::NormalizeData(object, verbose = FALSE)
    object <- Seurat::FindVariableFeatures(object, selection.method = "vst", nfeatures = cfg$integration$nfeatures, verbose = FALSE)
    object <- Seurat::ScaleData(object, vars.to.regress = regress, verbose = FALSE)
  }
  max_possible <- min(cfg$integration$max_npcs, ncol(object) - 1L, length(Seurat::VariableFeatures(object)) - 1L)
  if (max_possible < 2L) stop("Too few cells or variable genes for PCA")
  object <- Seurat::RunPCA(object, npcs = max_possible, verbose = FALSE)
  dims <- choose_pca_dims(object, cfg)
  batch_method <- resolve_batch_method(object, cfg, ctx)
  reduction <- "pca"
  if (identical(batch_method, "harmony")) {
    if (!require_packages("harmony", "Harmony", optional = TRUE, ctx = ctx)) {
      if (identical(cfg$integration$batch_method, "harmony")) stop("Harmony was explicitly requested but is unavailable")
      batch_method <- "none"
    } else {
      object <- harmony::RunHarmony(object, group.by.vars = cfg$integration$batch_variable,
                                    reduction.use = "pca", reduction.save = "harmony", verbose = FALSE)
      reduction <- "harmony"
    }
  }
  object <- Seurat::FindNeighbors(object, reduction = reduction, dims = dims, verbose = FALSE)
  object <- Seurat::FindClusters(object, resolution = cfg$integration$resolution, verbose = FALSE)
  object <- Seurat::RunUMAP(object, reduction = reduction, dims = dims, verbose = FALSE)
  if (isTRUE(cfg$integration$run_tsne)) object <- Seurat::RunTSNE(object, reduction = reduction, dims = dims, check_duplicates = FALSE, verbose = FALSE)
  object$cluster <- as.character(object$seurat_clusters)
  object@misc$pipeline <- object@misc$pipeline %||% list()
  object@misc$pipeline$analysis_assay <- assay
  object@misc$pipeline$main_reduction <- reduction
  object@misc$pipeline$integration_config <- cfg$integration
  object@misc$pipeline$resolved_dims <- dims
  object@misc$pipeline$resolved_batch_method <- batch_method
  save_table(ctx, data.frame(assay = assay, n_pcs = length(dims), dims = paste(dims, collapse = ","),
                             batch_method = batch_method, batch_variable = cfg$integration$batch_variable),
             "02_integration_decisions.csv")
  object
}

plot_basic_embeddings <- function(object, cfg, ctx) {
  for (field in intersect(c("sample", "group", "seurat_clusters"), colnames(object@meta.data))) {
    p <- Seurat::DimPlot(object, group.by = field, label = identical(field, "seurat_clusters"), repel = TRUE) +
      ggplot2::ggtitle(paste("UMAP by", field))
    save_plot(ctx, p, paste0("02_UMAP_", field, ".pdf"), 8, 6, cfg)
  }
  invisible(TRUE)
}
