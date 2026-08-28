create_context <- function(cfg) {
  ctx <- new.env(parent = emptyenv())
  project <- cfg$project
  work_name <- project$output_prefix %||% paste0(project$gse, "_advanced_scRNA")
  ctx$work_dir <- file.path(path.expand(project$work_root), work_name)
  ctx$raw_dir <- path.expand(project$input_dir %||% project$raw_dir %||% file.path(ctx$work_dir, "rawdata"))
  ctx$out_dir <- file.path(ctx$work_dir, "results")
  ctx$fig_dir <- file.path(ctx$out_dir, "figures_pdf")
  ctx$tab_dir <- file.path(ctx$out_dir, "tables")
  ctx$checkpoint_dir <- file.path(ctx$out_dir, paste0("checkpoints_", cfg$output$checkpoint_version))
  ctx$log_dir <- file.path(ctx$out_dir, "logs")
  ctx$report_dir <- file.path(ctx$out_dir, "reports")
  for (d in c(ctx$work_dir, ctx$raw_dir, ctx$out_dir, ctx$fig_dir, ctx$tab_dir,
              ctx$checkpoint_dir, ctx$log_dir, ctx$report_dir)) {
    dir.create(d, recursive = TRUE, showWarnings = FALSE)
  }
  ctx$log_file <- file.path(ctx$log_dir, paste0("pipeline_", format(Sys.time(), "%Y%m%d_%H%M%S"), ".log"))
  ctx$status_file <- file.path(ctx$report_dir, "module_status.csv")
  ctx$parameter_file <- file.path(ctx$report_dir, "parameters.csv")
  ctx$status <- data.frame(
    module = character(), status = character(), message = character(),
    cache_key = character(), time = character(), stringsAsFactors = FALSE
  )
  flat <- flatten_list(cfg)
  utils::write.csv(data.frame(parameter = names(flat), value = unlist(flat), row.names = NULL),
                   ctx$parameter_file, row.names = FALSE)
  ctx
}

log_msg <- function(ctx, ..., level = "INFO") {
  msg <- paste0("[", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "] [", level, "] ", paste0(..., collapse = ""))
  message(msg)
  cat(msg, "\n", file = ctx$log_file, append = TRUE)
  invisible(msg)
}

add_status <- function(ctx, module, status, message = "", cache_key = "") {
  ctx$status <- rbind(ctx$status, data.frame(
    module = module,
    status = status,
    message = as.character(message),
    cache_key = as.character(cache_key),
    time = as.character(Sys.time()),
    stringsAsFactors = FALSE
  ))
  utils::write.csv(ctx$status, ctx$status_file, row.names = FALSE)
  invisible(ctx$status)
}

safe_run <- function(ctx, module, fn, default = NULL, critical = FALSE, cfg = NULL) {
  log_msg(ctx, "Start module: ", module)
  tryCatch({
    value <- fn()
    add_status(ctx, module, "OK", "completed")
    log_msg(ctx, "Finish module: ", module)
    value
  }, error = function(e) {
    msg <- conditionMessage(e)
    status <- if (critical) "FAILED_CRITICAL" else "SKIPPED_OR_FAILED"
    add_status(ctx, module, status, msg)
    log_msg(ctx, "Module failed: ", module, " | ", msg, level = if (critical) "ERROR" else "WARN")
    if (critical && isTRUE(cfg$output$stop_on_critical_failure)) stop(e)
    default
  })
}

cache_run <- function(ctx, module, fn, cfg_fragment, input_fingerprint = NULL,
                      default = NULL, critical = FALSE, force = FALSE, cfg = NULL) {
  key <- hash_object(list(module = module, config = cfg_fragment, input = input_fingerprint))
  value_file <- file.path(ctx$checkpoint_dir, paste0(module, ".rds"))
  meta_file <- file.path(ctx$checkpoint_dir, paste0(module, ".meta.rds"))
  if (!isTRUE(force) && file.exists(value_file) && file.exists(meta_file)) {
    meta <- tryCatch(readRDS(meta_file), error = function(e) NULL)
    if (!is.null(meta) && identical(meta$key, key)) {
      cached <- tryCatch(readRDS(value_file), error = function(e) NULL)
      if (!is.null(cached)) {
        add_status(ctx, module, "CACHED", "loaded valid checkpoint", key)
        log_msg(ctx, "Checkpoint load: ", module)
        return(cached)
      }
    } else {
      log_msg(ctx, "Checkpoint invalidated by input/config change: ", module)
    }
  }
  log_msg(ctx, "Start module: ", module)
  succeeded <- TRUE
  value <- tryCatch(fn(), error = function(e) {
    succeeded <<- FALSE
    msg <- conditionMessage(e)
    status <- if (critical) "FAILED_CRITICAL" else "SKIPPED_OR_FAILED"
    add_status(ctx, module, status, msg, key)
    log_msg(ctx, "Module failed: ", module, " | ", msg, level = if (critical) "ERROR" else "WARN")
    if (critical && isTRUE(cfg$output$stop_on_critical_failure)) stop(e)
    default
  })
  if (!succeeded) return(value)
  if (inherits(value, "Seurat")) {
    value@misc$pipeline <- value@misc$pipeline %||% list()
    value@misc$pipeline$stage_key <- key
  }
  add_status(ctx, module, "OK", "completed", key)
  log_msg(ctx, "Finish module: ", module)
  if (!is.null(value)) {
    saveRDS(value, value_file)
    saveRDS(list(key = key, created = Sys.time(), module = module), meta_file)
    log_msg(ctx, "Checkpoint saved: ", module)
  }
  value
}

is_valid_pdf <- function(path) {
  if (!file.exists(path) || file.info(path)$size < 800) return(FALSE)
  sig <- tryCatch(readBin(path, what = "raw", n = 4), error = function(e) raw())
  length(sig) == 4L && identical(rawToChar(sig), "%PDF")
}

save_plot <- function(ctx, plot, filename, width = 8, height = 6, cfg = NULL) {
  path <- file.path(ctx$fig_dir, filename)
  device_id <- NULL
  ok <- tryCatch({
    grDevices::pdf(path, width = width, height = height,
                   family = cfg$output$pdf_family, useDingbats = FALSE)
    device_id <- grDevices::dev.cur()
    print(plot)
    grDevices::dev.off(which = device_id)
    device_id <- NULL
    TRUE
  }, error = function(e) {
    if (!is.null(device_id) && device_id %in% grDevices::dev.list()) {
      try(grDevices::dev.off(which = device_id), silent = TRUE)
    }
    log_msg(ctx, "Figure failed: ", filename, " | ", conditionMessage(e), level = "WARN")
    FALSE
  })
  if ((!ok || (isTRUE(cfg$output$validate_pdf) && !is_valid_pdf(path))) && file.exists(path)) {
    unlink(path)
    return(invisible(FALSE))
  }
  log_msg(ctx, "Saved figure: ", filename)
  invisible(TRUE)
}

save_table <- function(ctx, x, filename) {
  path <- file.path(ctx$tab_dir, filename)
  tryCatch({
    utils::write.csv(x, path, row.names = FALSE)
    log_msg(ctx, "Saved table: ", filename)
    TRUE
  }, error = function(e) {
    log_msg(ctx, "Table save failed: ", filename, " | ", conditionMessage(e), level = "WARN")
    FALSE
  })
}
