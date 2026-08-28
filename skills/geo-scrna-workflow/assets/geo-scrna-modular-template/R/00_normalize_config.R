normalize_config <- function(cfg) {
  cfg$project$output_prefix <- cfg$project$output_prefix %||%
    cfg$project$project_name %||% cfg$project$gse %||% "scrna_analysis"
  cfg
}
