run_enrichment <- function(de_results, cfg, ctx) {
  if (!require_packages("clusterProfiler", "enrichment", optional = TRUE, ctx = ctx)) return(data.frame())
  orgdb_pkg <- orgdb_for_species(cfg$project$species)
  if (is.null(orgdb_pkg) || !require_packages(orgdb_pkg, "organism annotation", optional = TRUE, ctx = ctx)) return(data.frame())
  df <- de_results$pseudobulk
  if (is.null(df) || !nrow(df)) return(data.frame())
  orgdb <- get(orgdb_pkg, envir = asNamespace(orgdb_pkg))
  outputs <- list()
  for (celltype in unique(df$celltype)) {
    part <- df[df$celltype == celltype, , drop = FALSE]
    universe_map <- suppressMessages(clusterProfiler::bitr(unique(part$gene), fromType = "SYMBOL", toType = "ENTREZID", OrgDb = orgdb))
    if (!nrow(universe_map)) next
    for (direction in c("up", "down")) {
      selected <- part$FDR < cfg$enrichment$p_adjust_cutoff &
        if (direction == "up") part$logFC > cfg$enrichment$logfc_cutoff else part$logFC < -cfg$enrichment$logfc_cutoff
      genes <- unique(part$gene[selected])
      if (length(genes) < cfg$enrichment$min_genes) next
      mapped <- suppressMessages(clusterProfiler::bitr(genes, fromType = "SYMBOL", toType = "ENTREZID", OrgDb = orgdb))
      if (nrow(mapped) < cfg$enrichment$min_genes) next
      enriched <- clusterProfiler::enrichGO(
        mapped$ENTREZID,
        universe = unique(universe_map$ENTREZID),
        OrgDb = orgdb,
        ont = cfg$enrichment$ontology,
        pAdjustMethod = "BH",
        pvalueCutoff = cfg$enrichment$p_adjust_cutoff,
        readable = TRUE
      )
      table <- as.data.frame(enriched)
      if (!nrow(table)) next
      table$celltype <- celltype
      table$direction <- direction
      key <- paste(celltype, direction, sep = "__")
      outputs[[key]] <- table
      p <- clusterProfiler::dotplot(enriched, showCategory = cfg$enrichment$show_categories) +
        ggplot2::ggtitle(paste("GO", cfg$enrichment$ontology, direction, "-", celltype))
      save_plot(ctx, p, paste0("05_GO_", direction, "_", safe_file_name(celltype), ".pdf"), 10, 7, cfg)
    }
  }
  result <- if (length(outputs)) do.call(rbind, outputs) else data.frame()
  if (nrow(result)) save_table(ctx, result, "08_GO_enrichment.csv")
  result
}
