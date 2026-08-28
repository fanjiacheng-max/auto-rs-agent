validate_config <- function(cfg) {
  errors <- character()
  add_error <- function(message) errors <<- c(errors, message)
  if (is.null(cfg$project$species)) {
    add_error("project.species is required; do not infer species from gene-name capitalization")
  } else {
    tryCatch(species_key(cfg$project$species), error = function(e) add_error(conditionMessage(e)))
  }
  has_local <- !is.null(cfg$project$input_dir) && nzchar(cfg$project$input_dir)
  has_geo <- !is.null(cfg$project$gse) && nzchar(cfg$project$gse)
  if (!has_local && !has_geo) add_error("Set project.input_dir or project.gse")
  if (has_local && has_geo) add_error("Set only one primary source: project.input_dir or project.gse")
  if (!cfg$input$matrix_orientation %in% c("auto", "gene_by_cell", "cell_by_gene")) {
    add_error("input.matrix_orientation must be auto, gene_by_cell, or cell_by_gene")
  }
  if (!cfg$integration$batch_method %in% c("auto", "harmony", "none")) {
    add_error("integration.batch_method must be auto, harmony, or none")
  }
  if (!is.null(cfg$integration$dims) && (any(cfg$integration$dims < 1L) || anyDuplicated(cfg$integration$dims))) {
    add_error("integration.dims must contain unique positive integers or NULL")
  }
  if (length(cfg$differential$contrast) != 2L || any(!nzchar(cfg$differential$contrast))) {
    add_error("differential.contrast must contain test and reference group names")
  }
  for (path in c(cfg$annotation$marker_file, cfg$annotation$external_annotation_file,
                 cfg$pathway_scores$signature_file)) {
    if (!is.null(path) && !file.exists(path.expand(path))) add_error(paste0("Configured file not found: ", path))
  }
  if (length(errors)) stop(paste(errors, collapse = "\n"), call. = FALSE)
  invisible(TRUE)
}

project_name_from_config <- function(cfg) {
  cfg$project$output_prefix %||% cfg$project$project_name %||% cfg$project$gse %||% "scrna_analysis"
}

is_counts_like <- function(x, tolerance = 1e-8, max_values = 100000L) {
  values <- if (inherits(x, "sparseMatrix")) x@x else as.numeric(x)
  if (!length(values)) return(FALSE)
  if (length(values) > max_values) values <- values[seq_len(max_values)]
  all(is.finite(values)) && all(values >= 0) && all(abs(values - round(values)) < tolerance)
}

design_is_confounded <- function(metadata, batch_variable, group_variable = "group") {
  if (!all(c(batch_variable, group_variable) %in% colnames(metadata))) return(NA)
  part <- unique(metadata[, c(batch_variable, group_variable), drop = FALSE])
  part <- part[stats::complete.cases(part), , drop = FALSE]
  if (nrow(part) < 2L) return(NA)
  table <- table(part[[batch_variable]], part[[group_variable]])
  all(rowSums(table > 0) <= 1L)
}
