args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
this_file <- normalizePath(sub("^--file=", "", file_arg[1L]), mustWork = TRUE)
root <- dirname(dirname(this_file))
source(file.path(root, "config", "default_config.R"))
for (f in sort(list.files(file.path(root, "R"), pattern = "\\.R$", full.names = TRUE))) {
  sys.source(f, envir = .GlobalEnv)
}
env <- new.env(parent = .GlobalEnv)
sys.source(file.path(root, "config", "example_config.R"), envir = env)
cfg <- normalize_config(deep_merge(default_config(), env$CFG))
validate_config(cfg)
stopifnot(is.list(cfg), is.null(cfg$integration$dims), length(cfg$differential$contrast) == 2L)
message("Configuration merge and semantic validation passed.")
