is_outlier_mad <- function(x, nmads = 3, direction = c("both", "lower", "higher"), log_transform = FALSE, batch = NULL) {
  direction <- match.arg(direction)
  values <- if (log_transform) log10(x + 1) else x
  groups <- if (is.null(batch)) rep("all", length(values)) else as.character(batch)
  flag <- rep(FALSE, length(values))
  for (g in unique(groups)) {
    idx <- groups == g
    med <- stats::median(values[idx], na.rm = TRUE)
    spread <- stats::mad(values[idx], na.rm = TRUE)
    if (!is.finite(spread) || spread == 0) spread <- 1e-8
    if (direction %in% c("both", "lower")) flag[idx] <- flag[idx] | values[idx] < med - nmads * spread
    if (direction %in% c("both", "higher")) flag[idx] <- flag[idx] | values[idx] > med + nmads * spread
  }
  flag[is.na(flag)] <- TRUE
  flag
}

resolve_assay <- function(object, requested = NULL) {
  if (!is.null(requested) && requested %in% names(object@assays)) return(requested)
  SeuratObject::DefaultAssay(object)
}

get_assay_data_safe <- function(object, assay = NULL, layer = "data") {
  assay <- resolve_assay(object, assay)
  if (utils::packageVersion("Seurat") >= "5.0.0") {
    SeuratObject::GetAssayData(object, assay = assay, layer = layer)
  } else {
    SeuratObject::GetAssayData(object, assay = assay, slot = layer)
  }
}

run_qc <- function(object, cfg, ctx) {
  assay <- resolve_assay(object, cfg$input$assay)
  object <- SeuratObject::`DefaultAssay<-`(object, value = assay)
  object[["percent.mt"]] <- Seurat::PercentageFeatureSet(object, pattern = mt_pattern_for_species(cfg$project$species))
  object[["percent.ribo"]] <- Seurat::PercentageFeatureSet(object, pattern = ribo_pattern_for_species(cfg$project$species))
  object[["percent.hb"]] <- Seurat::PercentageFeatureSet(object, pattern = hb_pattern_for_species(cfg$project$species))
  feature_col <- paste0("nFeature_", assay)
  count_col <- paste0("nCount_", assay)
  assert_true(feature_col %in% colnames(object@meta.data), paste0("Missing QC column: ", feature_col))
  assert_true(count_col %in% colnames(object@meta.data), paste0("Missing QC column: ", count_col))
  meta <- object@meta.data
  if (has_package("ggplot2")) {
    p <- Seurat::VlnPlot(object, features = c(feature_col, count_col, "percent.mt"), group.by = "sample", pt.size = 0, ncol = 3)
    save_plot(ctx, p, "01_QC_violin_before_filter.pdf", 14, 5, cfg)
  }
  object$discard_low_features <- is_outlier_mad(meta[[feature_col]], cfg$qc$nmads, "lower", TRUE, meta$sample) |
    meta[[feature_col]] <= cfg$input$min_features
  object$discard_low_counts <- is_outlier_mad(meta[[count_col]], cfg$qc$nmads, "lower", TRUE, meta$sample)
  object$discard_high_mt <- is_outlier_mad(object$percent.mt, cfg$qc$nmads, "higher", FALSE, meta$sample)
  if (!is.null(cfg$qc$max_percent_mt)) object$discard_high_mt <- object$discard_high_mt | object$percent.mt > cfg$qc$max_percent_mt
  object$doublet_call <- "not_tested"
  if (isTRUE(cfg$qc$run_doublet) && require_packages(module_packages()$doublet, "doublet detection", optional = TRUE, ctx = ctx)) {
    object <- safe_run(ctx, "doublet_detection_scDblFinder", function() {
      counts <- get_assay_data_safe(object, assay, "counts")
      sce <- SingleCellExperiment::SingleCellExperiment(list(counts = counts))
      sce$sample <- object$sample
      sce <- scDblFinder::scDblFinder(sce, samples = sce$sample)
      object$doublet_call <- as.character(SummarizedExperiment::colData(sce)$scDblFinder.class)
      object
    }, default = object)
  }
  object$discard_doublet <- tolower(object$doublet_call) == "doublet"
  object$discard <- object$discard_low_features | object$discard_low_counts | object$discard_high_mt | object$discard_doublet
  meta <- object@meta.data
  summary <- do.call(rbind, lapply(split(seq_len(nrow(meta)), meta$sample), function(idx) {
    data.frame(
      sample = as.character(meta$sample[idx[1L]]),
      group = as.character(meta$group[idx[1L]]),
      cells_before = length(idx),
      discarded_low_features = sum(meta$discard_low_features[idx]),
      discarded_low_counts = sum(meta$discard_low_counts[idx]),
      discarded_high_mt = sum(meta$discard_high_mt[idx]),
      discarded_doublet = sum(meta$discard_doublet[idx]),
      discarded_any = sum(meta$discard[idx]),
      cells_after = sum(!meta$discard[idx]),
      retention_fraction = mean(!meta$discard[idx]),
      median_features = stats::median(meta[[feature_col]][idx]),
      median_counts = stats::median(meta[[count_col]][idx]),
      median_mt = stats::median(meta$percent.mt[idx]),
      stringsAsFactors = FALSE
    )
  }))
  summary$below_minimum <- summary$cells_after < cfg$qc$min_cells_per_sample_after_qc
  save_table(ctx, summary, "01_QC_summary_by_sample.csv")
  if (isTRUE(cfg$qc$fail_on_sample_loss) && any(summary$below_minimum)) {
    stop("Samples below qc.min_cells_per_sample_after_qc: ", paste(summary$sample[summary$below_minimum], collapse = ", "))
  }
  keep_cells <- rownames(meta)[!meta$discard]
  if (length(keep_cells) < cfg$qc$min_cells_after_qc) stop("Too few cells remain after QC: ", length(keep_cells))
  object <- object[, keep_cells]
  if (has_package("ggplot2")) {
    p <- Seurat::VlnPlot(object, features = c(feature_col, count_col, "percent.mt"), group.by = "sample", pt.size = 0, ncol = 3)
    save_plot(ctx, p, "01_QC_violin_after_filter.pdf", 14, 5, cfg)
  }
  object@misc$pipeline <- object@misc$pipeline %||% list()
  object@misc$pipeline$analysis_assay <- assay
  object
}
