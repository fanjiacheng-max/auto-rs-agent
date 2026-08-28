export_results <- function(object, results, cfg, ctx) {
  if (utils::packageVersion("Seurat") >= "5.0.0") object <- tryCatch(SeuratObject::JoinLayers(object), error = function(e) object)
  saveRDS(object, file.path(ctx$out_dir, "Seurat_final.rds"))
  saveRDS(results, file.path(ctx$out_dir, "analysis_results.rds"))
  capture.output(utils::sessionInfo(), file = file.path(ctx$report_dir, "sessionInfo.txt"))
  summary_path <- file.path(ctx$report_dir, "analysis_summary.txt")
  cat("Modular GEO scRNA-seq pipeline summary\n", file = summary_path)
  cat("===================================\n\n", file = summary_path, append = TRUE)
  cat("GSE: ", cfg$project$gse, "\n", sep = "", file = summary_path, append = TRUE)
  cat("Species: ", cfg$project$species, "\n", sep = "", file = summary_path, append = TRUE)
  cat("Cells: ", ncol(object), "\n", sep = "", file = summary_path, append = TRUE)
  cat("Genes: ", nrow(object), "\n", sep = "", file = summary_path, append = TRUE)
  cat("Samples: ", paste(unique(object$sample), collapse = ", "), "\n", sep = "", file = summary_path, append = TRUE)
  cat("Groups: ", paste(unique(object$group), collapse = ", "), "\n", sep = "", file = summary_path, append = TRUE)
  if ("celltype" %in% colnames(object@meta.data)) {
    cat("Cell types: ", paste(unique(object$celltype), collapse = ", "), "\n", sep = "", file = summary_path, append = TRUE)
  }
  cat("\nReview module_status.csv before interpreting results.\n", file = summary_path, append = TRUE)
  log_msg(ctx, "Final outputs saved to: ", ctx$out_dir)
  TRUE
}
