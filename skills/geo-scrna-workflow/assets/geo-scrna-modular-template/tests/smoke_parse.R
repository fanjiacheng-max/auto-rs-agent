args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
this_file <- normalizePath(sub("^--file=", "", file_arg[1L]), mustWork = TRUE)
root <- dirname(dirname(this_file))
files <- c(file.path(root, "config", "default_config.R"),
           sort(list.files(file.path(root, "R"), pattern = "\\.R$", full.names = TRUE)),
           file.path(root, "run_pipeline.R"))
failed <- character()
for (f in files) {
  tryCatch(parse(file = f), error = function(e) failed <<- c(failed, paste(f, conditionMessage(e), sep = ": ")))
}
if (length(failed)) stop(paste(failed, collapse = "\n"))
message("Parsed ", length(files), " R files successfully.")
