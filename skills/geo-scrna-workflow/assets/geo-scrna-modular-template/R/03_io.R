decompress_archives <- function(dir_path, ctx) {
  files <- list.files(dir_path, recursive = TRUE, full.names = TRUE)
  for (f in files) {
    lower <- tolower(basename(f))
    if (grepl("\\.(tar|tar\\.gz|tgz)$", lower)) {
      safe_run(ctx, paste0("untar_", safe_file_name(lower)), function() utils::untar(f, exdir = dirname(f)))
    } else if (grepl("\\.zip$", lower)) {
      safe_run(ctx, paste0("unzip_", safe_file_name(lower)), function() utils::unzip(f, exdir = dirname(f)))
    } else if (grepl("\\.gz$", lower) && !grepl("\\.(mtx|tsv|txt|csv)\\.gz$", lower) && has_package("R.utils")) {
      safe_run(ctx, paste0("gunzip_", safe_file_name(lower)), function() R.utils::gunzip(f, remove = FALSE, overwrite = FALSE))
    }
  }
  invisible(TRUE)
}

download_geo_supp <- function(gse, dir_path, ctx) {
  if (is.null(gse) || !nzchar(gse)) stop("project.gse is required for GEO download")
  if (length(list.files(dir_path, recursive = TRUE, all.files = FALSE)) > 0L) {
    log_msg(ctx, "Raw directory is not empty; GEO download skipped.")
    return(TRUE)
  }
  require_packages("GEOquery", "GEO download", optional = FALSE, ctx = ctx)
  GEOquery::getGEOSuppFiles(gse, baseDir = dir_path, makeDirectory = TRUE)
  TRUE
}

looks_like_10x_dir <- function(path) {
  files <- basename(list.files(path, full.names = FALSE))
  any(grepl("^matrix\\.mtx(\\.gz)?$", files, ignore.case = TRUE)) &&
    any(grepl("^(features|genes)\\.tsv(\\.gz)?$", files, ignore.case = TRUE)) &&
    any(grepl("^barcodes\\.tsv(\\.gz)?$", files, ignore.case = TRUE))
}

find_10x_dirs <- function(root) {
  matrices <- list.files(root, pattern = "matrix\\.mtx(\\.gz)?$", recursive = TRUE,
                         full.names = TRUE, ignore.case = TRUE)
  dirs <- unique(dirname(matrices))
  dirs[vapply(dirs, looks_like_10x_dir, logical(1))]
}

sample_name_from_input <- function(path) {
  generic <- c("filtered_feature_bc_matrix", "raw_feature_bc_matrix",
               "filtered_gene_bc_matrices", "raw_gene_bc_matrices")
  candidate <- path
  if (dir.exists(path) && tolower(basename(path)) %in% generic) candidate <- dirname(path)
  clean_sample_name(candidate)
}

discover_input_specs <- function(dir_path, cfg, ctx) {
  if (isTRUE(cfg$input$decompress_archives)) decompress_archives(dir_path, ctx)
  files <- list.files(dir_path, recursive = TRUE, full.names = TRUE)
  files <- files[!grepl("\\.(tar|tgz|zip|tar\\.gz)$", files, ignore.case = TRUE)]
  specs <- list()
  add_spec <- function(type, sample, path) {
    key <- paste(type, safe_file_name(sample), length(specs) + 1L, sep = "__")
    specs[[key]] <<- list(type = type, sample = sample, path = path)
  }
  tenx_dirs <- find_10x_dirs(dir_path)
  for (d in tenx_dirs) add_spec("10xdir", sample_name_from_input(d), d)
  files <- files[!dirname(files) %in% tenx_dirs]
  for (f in files[grepl("\\.h5$", files, ignore.case = TRUE)]) add_spec("h5", clean_sample_name(f), f)
  for (f in files[grepl("\\.h5ad$", files, ignore.case = TRUE)]) add_spec("h5ad", clean_sample_name(f), f)
  for (f in files[grepl("\\.loom$", files, ignore.case = TRUE)]) add_spec("loom", clean_sample_name(f), f)
  for (f in files[grepl("\\.(rds|rdata)$", files, ignore.case = TRUE)]) add_spec("robj", clean_sample_name(f), f)
  dense <- files[
    grepl("\\.(txt|csv|tsv)(\\.gz)?$", files, ignore.case = TRUE) &
      !grepl("^(barcodes|features|genes)(\\.(txt|csv|tsv))?(\\.gz)?$|matrix\\.mtx|annotation|metadata|sample[_-]?sheet",
             basename(files), ignore.case = TRUE)
  ]
  for (f in dense) add_spec("dense", clean_sample_name(f), f)
  specs
}

select_feature_matrix <- function(x, feature_type, ctx = NULL) {
  if (!is.list(x)) return(x)
  if (!is.null(feature_type) && feature_type %in% names(x)) return(x[[feature_type]])
  sizes <- vapply(x, nrow, integer(1))
  selected <- names(which.max(sizes))
  if (!is.null(ctx)) log_msg(ctx, "Requested feature type unavailable; selected largest matrix: ", selected, level = "WARN")
  x[[selected]]
}

read_dense_matrix <- function(path, cfg) {
  require_packages(c("data.table", "Matrix"), "dense matrix reader")
  sep <- if (grepl("\\.csv(\\.gz)?$", path, ignore.case = TRUE)) "," else "\t"
  tab <- data.table::fread(path, sep = sep, data.table = FALSE, check.names = FALSE, showProgress = FALSE)
  if (ncol(tab) < 2L) tab <- data.table::fread(path, data.table = FALSE, check.names = FALSE, showProgress = FALSE)
  row_ids <- as.character(tab[[1L]])
  mat <- as.matrix(tab[, -1L, drop = FALSE])
  storage.mode(mat) <- "numeric"
  mat[is.na(mat)] <- 0
  rownames(mat) <- make.unique(row_ids)
  colnames(mat) <- make.unique(colnames(tab)[-1L])
  orientation <- cfg$input$matrix_orientation
  if (identical(orientation, "auto")) {
    barcode_pattern <- "^[ACGTN]{8,}(-[0-9]+)?$"
    row_barcode <- mean(grepl(barcode_pattern, rownames(mat), ignore.case = TRUE))
    col_barcode <- mean(grepl(barcode_pattern, colnames(mat), ignore.case = TRUE))
    orientation <- if (row_barcode > col_barcode + 0.2) "cell_by_gene" else "gene_by_cell"
  }
  if (identical(orientation, "cell_by_gene")) mat <- t(mat)
  Matrix::Matrix(mat, sparse = TRUE)
}

read_r_object_as_seurat <- function(path, cfg) {
  if (grepl("\\.rds$", path, ignore.case = TRUE)) {
    object <- readRDS(path)
  } else {
    env <- new.env(parent = emptyenv())
    load(path, envir = env)
    object_names <- ls(env)
    if (!length(object_names)) stop("RData file contains no objects")
    preferred <- object_names[vapply(object_names, function(nm) inherits(get(nm, env), "Seurat"), logical(1))]
    preferred <- c(preferred, object_names[vapply(object_names, function(nm) inherits(get(nm, env), "SingleCellExperiment"), logical(1))])
    object <- get(c(preferred, object_names)[1L], env)
  }
  if (inherits(object, "Seurat")) return(object)
  if (inherits(object, "SingleCellExperiment")) {
    assays <- SummarizedExperiment::assayNames(object)
    if (!"counts" %in% assays) stop("SingleCellExperiment has no counts assay")
    return(Seurat::as.Seurat(object, counts = "counts", data = if ("logcounts" %in% assays) "logcounts" else NULL))
  }
  if (inherits(object, c("matrix", "dgCMatrix", "data.frame"))) {
    mat <- if (is.data.frame(object)) as.matrix(object) else object
    return(Seurat::CreateSeuratObject(Matrix::Matrix(mat, sparse = TRUE),
                                      min.cells = cfg$input$min_cells,
                                      min.features = cfg$input$min_features))
  }
  stop("Unsupported R object class: ", paste(class(object), collapse = ", "))
}

read_h5ad_as_seurat <- function(path, cfg) {
  require_packages(c("zellkonverter", "SummarizedExperiment"), "h5ad reader")
  sce <- zellkonverter::readH5AD(path)
  assays <- SummarizedExperiment::assayNames(sce)
  counts_layer <- cfg$input$h5ad_counts_layer
  if (counts_layer %in% assays) return(Seurat::as.Seurat(sce, counts = counts_layer, data = NULL))
  if (isTRUE(cfg$input$allow_h5ad_x_as_counts) && "X" %in% assays && is_counts_like(SummarizedExperiment::assay(sce, "X"))) {
    return(Seurat::as.Seurat(sce, counts = "X", data = NULL))
  }
  stop("H5AD raw-count layer not found. Available assays: ", paste(assays, collapse = ", "),
       ". Set input.h5ad_counts_layer or explicitly allow count-like X.")
}

standardize_object_metadata <- function(object, spec, cfg) {
  meta <- object@meta.data
  sample_col <- cfg$input$sample_column
  group_col <- cfg$input$group_column
  if (sample_col %in% colnames(meta)) {
    object$sample <- as.character(meta[[sample_col]])
  } else if (isTRUE(cfg$input$preserve_object_metadata) && "sample" %in% colnames(meta)) {
    object$sample <- as.character(meta$sample)
  } else if (isTRUE(cfg$input$preserve_object_metadata) && "orig.ident" %in% colnames(meta)) {
    object$sample <- as.character(meta$orig.ident)
  } else {
    object$sample <- spec$sample
  }
  object$sample[is.na(object$sample) | !nzchar(object$sample)] <- spec$sample
  if (group_col %in% colnames(meta)) object$group <- as.character(meta[[group_col]])
  object$source_file <- spec$path
  object$source_type <- spec$type
  object
}

read_spec_to_seurat <- function(spec, cfg, ctx = NULL) {
  object <- switch(spec$type,
    "10xdir" = {
      x <- select_feature_matrix(Seurat::Read10X(data.dir = spec$path), cfg$input$feature_type, ctx)
      Seurat::CreateSeuratObject(x, project = spec$sample, min.cells = cfg$input$min_cells,
                                 min.features = cfg$input$min_features)
    },
    "h5" = {
      x <- select_feature_matrix(Seurat::Read10X_h5(spec$path), cfg$input$feature_type, ctx)
      Seurat::CreateSeuratObject(x, project = spec$sample, min.cells = cfg$input$min_cells,
                                 min.features = cfg$input$min_features)
    },
    "h5ad" = read_h5ad_as_seurat(spec$path, cfg),
    "loom" = {
      require_packages("SeuratDisk", "loom reader")
      h5seurat <- sub("\\.loom$", ".h5seurat", spec$path, ignore.case = TRUE)
      SeuratDisk::Convert(spec$path, dest = "h5seurat", overwrite = TRUE)
      SeuratDisk::LoadH5Seurat(h5seurat)
    },
    "robj" = read_r_object_as_seurat(spec$path, cfg),
    "dense" = Seurat::CreateSeuratObject(read_dense_matrix(spec$path, cfg), project = spec$sample,
                                          min.cells = cfg$input$min_cells,
                                          min.features = cfg$input$min_features),
    stop("Unsupported input type: ", spec$type)
  )
  standardize_object_metadata(object, spec, cfg)
}

read_sample_sheet <- function(path) {
  if (is.null(path)) return(NULL)
  path <- path.expand(path)
  if (!file.exists(path)) stop("Sample sheet not found: ", path)
  sheet <- utils::read.csv(path, stringsAsFactors = FALSE, check.names = FALSE)
  missing <- setdiff(c("sample", "group"), colnames(sheet))
  if (length(missing)) stop("Sample sheet is missing columns: ", paste(missing, collapse = ", "))
  if (anyDuplicated(sheet$sample)) stop("Sample sheet contains duplicate sample names")
  if (any(!nzchar(sheet$sample)) || any(!nzchar(sheet$group)) || any(sheet$group == "REVIEW_REQUIRED")) stop("Sample sheet contains empty or unreviewed sample/group values")
  sheet
}

apply_sample_sheet <- function(object, sample_sheet, ctx) {
  if (is.null(sample_sheet)) {
    if (!"group" %in% colnames(object@meta.data)) object$group <- "Unknown"
    object$group[is.na(object$group) | !nzchar(object$group)] <- "Unknown"
    object$group_source <- ifelse(object$group == "Unknown", "missing_sample_sheet", "object_metadata")
    return(object)
  }
  idx <- match(as.character(object$sample), sample_sheet$sample)
  object$group <- sample_sheet$group[idx]
  object$group[is.na(object$group) | !nzchar(object$group)] <- "Unknown"
  object$group_source <- ifelse(is.na(idx), "unmatched", "sample_sheet")
  for (nm in setdiff(colnames(sample_sheet), c("sample", "group"))) object[[nm]] <- sample_sheet[[nm]][idx]
  unmatched <- unique(as.character(object$sample[is.na(idx)]))
  if (length(unmatched)) log_msg(ctx, "Samples missing from sample sheet: ", paste(unmatched, collapse = ", "), level = "WARN")
  object
}

save_design_review <- function(object, sample_sheet, ctx) {
  meta <- object@meta.data
  fields <- intersect(c("sample", "group", "donor", "batch", "group_source"), colnames(meta))
  review <- unique(meta[, fields, drop = FALSE])
  cell_counts <- as.data.frame(table(sample = meta$sample), stringsAsFactors = FALSE)
  names(cell_counts)[2L] <- "cells"
  review$cells <- cell_counts$cells[match(review$sample, cell_counts$sample)]
  review$in_sample_sheet <- if (is.null(sample_sheet)) FALSE else review$sample %in% sample_sheet$sample
  save_table(ctx, review[order(review$sample), , drop = FALSE], "00_sample_sheet_review.csv")
}

build_combined <- function(cfg, ctx) {
  if (is.null(cfg$project$input_dir) && isTRUE(cfg$input$download_geo_if_needed)) download_geo_supp(cfg$project$gse, ctx$raw_dir, ctx)
  specs <- discover_input_specs(ctx$raw_dir, cfg, ctx)
  if (!length(specs)) stop("No supported scRNA-seq inputs detected in: ", ctx$raw_dir)
  spec_table <- do.call(rbind, lapply(names(specs), function(nm) data.frame(spec = nm, as.data.frame(specs[[nm]]))))
  save_table(ctx, spec_table, "00_detected_input_specs.csv")
  objects <- list()
  read_status <- list()
  for (nm in names(specs)) {
    spec <- specs[[nm]]
    object <- safe_run(ctx, paste0("read_", nm), function() read_spec_to_seurat(spec, cfg, ctx), default = NULL)
    if (is.null(object) || !inherits(object, "Seurat") || ncol(object) == 0L) {
      read_status[[nm]] <- data.frame(spec = nm, sample = spec$sample, type = spec$type, status = "failed")
      next
    }
    colnames(object) <- make.unique(paste0(safe_file_name(nm), "__", colnames(object)))
    objects[[nm]] <- object
    read_status[[nm]] <- data.frame(spec = nm, sample = paste(unique(object$sample), collapse = ";"),
                                    type = spec$type, status = "ok", n_genes = nrow(object), n_cells = ncol(object))
  }
  save_table(ctx, rbind_fill(read_status), "00_read_status.csv")
  if (!length(objects)) stop("All input readers failed; inspect logs and input specifications")
  combined <- if (length(objects) == 1L) objects[[1L]] else merge(objects[[1L]], y = objects[-1L], project = project_name_from_config(cfg))
  if (utils::packageVersion("Seurat") >= "5.0.0") combined <- tryCatch(SeuratObject::JoinLayers(combined), error = function(e) combined)
  sample_sheet <- read_sample_sheet(cfg$project$sample_sheet)
  combined <- apply_sample_sheet(combined, sample_sheet, ctx)
  save_design_review(combined, sample_sheet, ctx)
  combined
}
