prepare_cellchat_object <- function(object, cfg) {
  meta <- object@meta.data
  keep_types <- names(sort(table(meta$celltype), decreasing = TRUE))
  keep_types <- head(keep_types, cfg$cellchat$max_celltypes)
  cells <- rownames(meta)[meta$celltype %in% keep_types]
  sampled <- unlist(lapply(split(cells, meta[cells, "celltype"]), function(x) {
    if (length(x) > cfg$cellchat$max_cells_per_celltype) sample(x, cfg$cellchat$max_cells_per_celltype) else x
  }), use.names = FALSE)
  if (length(sampled) > cfg$cellchat$max_cells_total) sampled <- sample(sampled, cfg$cellchat$max_cells_total)
  object[, sampled]
}

run_cellchat_one <- function(object, cfg, ctx, label = "all") {
  require_packages("CellChat", "CellChat", optional = FALSE, ctx = ctx)
  sub <- prepare_cellchat_object(object, cfg)
  if (length(unique(sub$celltype)) < 2L) stop("CellChat requires at least two cell types")
  data <- get_assay_data_safe(sub, assay = cfg$input$assay, layer = "data")
  chat <- CellChat::createCellChat(data, meta = sub@meta.data, group.by = "celltype")
  database <- if (species_key(cfg$project$species) == "mouse") CellChat::CellChatDB.mouse else CellChat::CellChatDB.human
  if (!is.null(cfg$cellchat$database_category)) database <- CellChat::subsetDB(database, search = cfg$cellchat$database_category)
  chat@DB <- database
  chat <- CellChat::subsetData(chat)
  chat <- CellChat::identifyOverExpressedGenes(chat)
  chat <- CellChat::identifyOverExpressedInteractions(chat)
  chat <- CellChat::computeCommunProb(chat, type = "truncatedMean", trim = 0.1)
  chat <- CellChat::filterCommunication(chat, min.cells = cfg$cellchat$min_cells)
  chat <- CellChat::computeCommunProbPathway(chat)
  chat <- CellChat::aggregateNet(chat)
  communications <- CellChat::subsetCommunication(chat)
  save_table(ctx, communications, paste0("11_cellchat_", safe_file_name(label), ".csv"))
  chat
}

run_cellchat <- function(object, cfg, ctx) {
  result <- list(all = run_cellchat_one(object, cfg, ctx, "all"))
  contrast <- cfg$differential$contrast
  if (length(contrast) == 2L && all(contrast %in% object$group)) {
    for (group in contrast) {
      cells <- rownames(object@meta.data)[object$group == group]
      if (length(cells) >= 200L) result[[group]] <- run_cellchat_one(object[, cells], cfg, ctx, group)
    }
  }
  result
}
