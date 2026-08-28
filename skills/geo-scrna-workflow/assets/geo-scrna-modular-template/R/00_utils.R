`%||%` <- function(x, y) if (!is.null(x)) x else y

assert_true <- function(x, message) {
  if (!isTRUE(x)) stop(message, call. = FALSE)
  invisible(TRUE)
}

safe_file_name <- function(x) {
  x <- gsub("[^A-Za-z0-9_.-]+", "_", as.character(x))
  gsub("_+$", "", x)
}

clean_sample_name <- function(x) {
  x <- basename(x)
  x <- gsub("\\.(txt|csv|tsv|mtx|h5|h5ad|loom|rds|rdata)(\\.gz)?$", "", x, ignore.case = TRUE)
  x <- gsub("^GSM[0-9]+[_-]?", "", x, ignore.case = TRUE)
  x <- safe_file_name(x)
  if (!nzchar(x)) x <- paste0("sample_", sample.int(999999L, 1L))
  x
}

deep_merge <- function(base, override) {
  if (is.null(override)) return(base)
  for (nm in names(override)) {
    if (is.list(base[[nm]]) && is.list(override[[nm]])) {
      base[[nm]] <- deep_merge(base[[nm]], override[[nm]])
    } else {
      base[[nm]] <- override[[nm]]
    }
  }
  base
}

flatten_list <- function(x, prefix = "") {
  out <- list()
  for (nm in names(x)) {
    key <- if (nzchar(prefix)) paste(prefix, nm, sep = ".") else nm
    if (is.list(x[[nm]]) && !is.data.frame(x[[nm]])) {
      out <- c(out, flatten_list(x[[nm]], key))
    } else {
      out[[key]] <- paste(capture.output(dput(x[[nm]])), collapse = "")
    }
  }
  out
}

hash_object <- function(x) {
  f <- tempfile(fileext = ".rds")
  on.exit(unlink(f), add = TRUE)
  saveRDS(x, f, version = 2)
  unname(tools::md5sum(f))
}

file_fingerprint <- function(paths, mode = c("size_mtime", "md5")) {
  mode <- match.arg(mode)
  expanded <- path.expand(paths)
  paths <- unique(expanded[file.exists(expanded)])
  if (!length(paths)) return(data.frame())
  info <- file.info(paths)
  out <- data.frame(
    path = normalizePath(paths, winslash = "/", mustWork = FALSE),
    size = info$size,
    mtime = as.character(info$mtime),
    stringsAsFactors = FALSE
  )
  if (identical(mode, "md5")) out$md5 <- unname(tools::md5sum(paths))
  out
}

object_fingerprint <- function(object) {
  if (inherits(object, "Seurat")) {
    stored <- tryCatch(object@misc$pipeline$stage_key, error = function(e) NULL)
    if (!is.null(stored) && nzchar(stored)) return(stored)
    return(hash_object(list(
      dimensions = dim(object),
      cells = colnames(object),
      features = rownames(object),
      assays = names(object@assays),
      reductions = names(object@reductions),
      metadata_columns = colnames(object@meta.data)
    )))
  }
  hash_object(object)
}

species_key <- function(species) {
  x <- tolower(species)
  if (!x %in% c("human", "mouse", "rat", "zebrafish")) {
    stop("Unsupported species: ", species, call. = FALSE)
  }
  x
}

mt_pattern_for_species <- function(species) {
  switch(species_key(species), human = "^MT-", mouse = "^mt-", rat = "^Mt-", zebrafish = "^mt-")
}

ribo_pattern_for_species <- function(species) {
  if (species_key(species) == "human") "^RP[SL]" else "^Rp[sl]"
}

hb_pattern_for_species <- function(species) {
  if (species_key(species) == "human") "^HB[ABDEGQZ]" else "^Hb[ab]"
}

orgdb_for_species <- function(species) {
  switch(species_key(species), human = "org.Hs.eg.db", mouse = "org.Mm.eg.db", NULL)
}

rbind_fill <- function(items) {
  items <- Filter(function(x) !is.null(x) && nrow(x) > 0L, items)
  if (!length(items)) return(data.frame())
  cols <- unique(unlist(lapply(items, names), use.names = FALSE))
  do.call(rbind, lapply(items, function(x) {
    missing <- setdiff(cols, names(x))
    for (nm in missing) x[[nm]] <- NA
    x[, cols, drop = FALSE]
  }))
}

call_supported <- function(pkg, fun, args) {
  f <- get(fun, envir = asNamespace(pkg))
  formal_names <- names(formals(f))
  do.call(f, args[names(args) %in% formal_names])
}

source_project_modules <- function(project_root) {
  files <- sort(list.files(file.path(project_root, "R"), pattern = "\\.R$", full.names = TRUE))
  for (f in files) sys.source(f, envir = .GlobalEnv)
  invisible(files)
}
