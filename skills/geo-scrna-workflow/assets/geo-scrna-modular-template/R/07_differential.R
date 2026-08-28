run_markers <- function(object, cfg, ctx) {
  object <- SeuratObject::`Idents<-`(object, value = "celltype")
  markers <- Seurat::FindAllMarkers(object, only.pos = isTRUE(cfg$markers$only_positive),
                                    min.pct = cfg$markers$min_pct,
                                    logfc.threshold = cfg$markers$logfc_threshold)
  save_table(ctx, markers, "03_celltype_markers.csv")
  markers
}

validate_contrast <- function(object, contrast, ctx) {
  if (length(contrast) != 2L) {
    log_msg(ctx, "Contrast must have exactly two group names", level = "WARN")
    return(FALSE)
  }
  groups <- unique(as.character(object$group))
  missing <- setdiff(contrast, groups)
  if (length(missing)) {
    log_msg(ctx, "Formal comparison gated; contrast group(s) not found: ", paste(missing, collapse = ", "), level = "WARN")
    return(FALSE)
  }
  TRUE
}

run_exploratory_cell_level_de <- function(object, cfg, ctx) {
  contrast <- cfg$differential$contrast
  if (!validate_contrast(object, contrast, ctx)) return(data.frame())
  object <- SeuratObject::`Idents<-`(object, value = "group")
  result <- Seurat::FindMarkers(object, ident.1 = contrast[1L], ident.2 = contrast[2L],
                                logfc.threshold = 0, min.pct = 0.1)
  result$gene <- rownames(result)
  result$contrast <- paste(contrast[1L], "vs", contrast[2L])
  result$analysis_type <- "exploratory_cell_level_pseudoreplication_risk"
  save_table(ctx, result, "04_DE_exploratory_cell_level.csv")
  result
}

aggregate_counts_by_sample <- function(counts, metadata, samples) {
  out <- lapply(samples, function(sample_id) {
    cells <- rownames(metadata)[metadata$sample == sample_id]
    Matrix::rowSums(counts[, cells, drop = FALSE])
  })
  matrix <- do.call(cbind, out)
  colnames(matrix) <- samples
  as.matrix(matrix)
}

build_pseudobulk_design <- function(sample_metadata, contrast, covariates = NULL) {
  covariates <- intersect(covariates %||% character(), colnames(sample_metadata))
  sample_metadata$group <- factor(sample_metadata$group, levels = c(contrast[2L], contrast[1L]))
  terms <- c("group", covariates)
  design <- stats::model.matrix(stats::reformulate(terms, intercept = FALSE), data = sample_metadata)
  colnames(design) <- make.names(colnames(design), unique = TRUE)
  group_columns <- grep("^group", colnames(design), value = TRUE)
  reference_col <- group_columns[match(make.names(contrast[2L]), sub("^group", "", group_columns))]
  test_col <- group_columns[match(make.names(contrast[1L]), sub("^group", "", group_columns))]
  if (is.na(reference_col) || is.na(test_col)) stop("Could not construct group contrast columns")
  contrast_vector <- rep(0, ncol(design))
  names(contrast_vector) <- colnames(design)
  contrast_vector[test_col] <- 1
  contrast_vector[reference_col] <- -1
  list(design = design, contrast = contrast_vector, covariates = covariates)
}

run_pseudobulk_de <- function(object, cfg, ctx) {
  if (!require_packages(module_packages()$pseudobulk, "pseudobulk", optional = TRUE, ctx = ctx)) return(data.frame())
  contrast <- cfg$differential$contrast
  if (!validate_contrast(object, contrast, ctx)) return(data.frame())
  counts <- get_assay_data_safe(object, assay = cfg$input$assay, layer = "counts")
  metadata <- object@meta.data
  results <- list()
  diagnostics <- list()
  for (celltype in unique(metadata$celltype)) {
    status <- "eligible"
    reason <- ""
    cells <- rownames(metadata)[metadata$celltype == celltype]
    if (length(cells) < cfg$differential$min_cells_per_celltype) {
      status <- "skipped"; reason <- "too_few_cells"
    }
    md <- metadata[cells, , drop = FALSE]
    per_sample <- table(md$sample)
    valid_samples <- names(per_sample)[per_sample >= cfg$differential$min_cells_per_sample_celltype]
    md <- md[md$sample %in% valid_samples, , drop = FALSE]
    fields <- unique(c("sample", "group", cfg$differential$covariates %||% character()))
    fields <- intersect(fields, colnames(md))
    sample_meta <- unique(md[, fields, drop = FALSE])
    sample_meta <- sample_meta[sample_meta$group %in% contrast, , drop = FALSE]
    if (anyDuplicated(sample_meta$sample)) {
      status <- "skipped"; reason <- "sample_metadata_not_constant"
    }
    sample_meta <- sample_meta[stats::complete.cases(sample_meta), , drop = FALSE]
    group_counts <- table(factor(sample_meta$group, levels = contrast))
    if (any(group_counts < cfg$differential$min_samples_per_group)) {
      status <- "skipped"; reason <- "insufficient_replicates"
    }
    if (status == "eligible") {
      samples <- sample_meta$sample
      matrix <- aggregate_counts_by_sample(counts, md, samples)
      sample_meta <- sample_meta[match(colnames(matrix), sample_meta$sample), , drop = FALSE]
      design_info <- tryCatch(build_pseudobulk_design(sample_meta, contrast, cfg$differential$covariates),
                              error = function(e) e)
      if (inherits(design_info, "error")) {
        status <- "skipped"; reason <- paste0("design_error: ", conditionMessage(design_info))
      } else if (qr(design_info$design)$rank < ncol(design_info$design)) {
        status <- "skipped"; reason <- "rank_deficient_design"
      } else {
        dge <- edgeR::DGEList(counts = matrix)
        keep <- edgeR::filterByExpr(dge, design = design_info$design)
        dge <- dge[keep, , keep.lib.sizes = FALSE]
        if (nrow(dge) < 50L) {
          status <- "skipped"; reason <- "too_few_expressed_genes"
        } else {
          dge <- edgeR::calcNormFactors(dge)
          dge <- edgeR::estimateDisp(dge, design_info$design)
          fit <- edgeR::glmQLFit(dge, design_info$design)
          qlf <- edgeR::glmQLFTest(fit, contrast = design_info$contrast)
          table <- edgeR::topTags(qlf, n = Inf)$table
          table$gene <- rownames(table)
          table$celltype <- celltype
          table$contrast <- paste(contrast[1L], "vs", contrast[2L])
          table$n_samples_group1 <- sum(sample_meta$group == contrast[1L])
          table$n_samples_group2 <- sum(sample_meta$group == contrast[2L])
          table$covariates <- paste(design_info$covariates, collapse = ";")
          results[[celltype]] <- table
        }
      }
    }
    diagnostics[[celltype]] <- data.frame(
      celltype = celltype, status = status, reason = reason,
      total_cells = length(cells), eligible_samples = length(unique(md$sample)),
      test_samples = unname(group_counts[1L] %||% 0), reference_samples = unname(group_counts[2L] %||% 0),
      stringsAsFactors = FALSE
    )
  }
  diagnostic_table <- rbind_fill(diagnostics)
  save_table(ctx, diagnostic_table, "05_pseudobulk_eligibility.csv")
  result <- if (length(results)) do.call(rbind, results) else data.frame()
  if (nrow(result)) save_table(ctx, result, "05_pseudobulk_edgeR_by_celltype.csv")
  result
}

run_differential_module <- function(object, cfg, ctx) {
  list(
    exploratory = if (isTRUE(cfg$differential$exploratory_cell_level)) run_exploratory_cell_level_de(object, cfg, ctx) else data.frame(),
    pseudobulk = if (isTRUE(cfg$differential$pseudobulk)) run_pseudobulk_de(object, cfg, ctx) else data.frame()
  )
}
