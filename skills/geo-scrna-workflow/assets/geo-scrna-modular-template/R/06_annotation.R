default_marker_db <- function(species) {
  key <- species_key(species)
  if (!key %in% c("human", "mouse")) return(list())
  if (key == "mouse") {
    return(list(
      T_cells = c("Cd3d", "Cd3e", "Trac", "Il7r"),
      CD8_T_cells = c("Cd8a", "Cd8b1", "Nkg7", "Gzmb"),
      NK_cells = c("Nkg7", "Klrd1", "Prf1", "Gzma"),
      B_cells = c("Ms4a1", "Cd79a", "Cd79b", "Bank1"),
      Plasma_cells = c("Mzb1", "Jchain", "Sdc1", "Xbp1"),
      Monocytes_Macrophages = c("Lyz2", "Adgre1", "Aif1", "Lpl"),
      Dendritic_cells = c("Fcer1a", "Itgax", "Clec10a", "Siglech"),
      Endothelial_cells = c("Pecam1", "Vwf", "Kdr", "Cldn5"),
      Fibroblasts = c("Dcn", "Lum", "Col1a1", "Col1a2"),
      Smooth_muscle_cells = c("Acta2", "Myh11", "Tagln", "Cnn1"),
      Epithelial_cells = c("Epcam", "Krt8", "Krt18", "Krt19"),
      Mast_cells = c("Tpsab1", "Tpsb2", "Cpa3", "Kit"),
      Neutrophils = c("S100a8", "S100a9", "Csf3r", "Mpo"),
      Pericytes = c("Rgs5", "Pdgfrb", "Cspg4", "Mcam")
    ))
  }
  list(
    T_cells = c("CD3D", "CD3E", "TRAC", "IL7R"),
    CD8_T_cells = c("CD8A", "CD8B", "NKG7", "GZMB"),
    NK_cells = c("NKG7", "GNLY", "KLRD1", "PRF1"),
    B_cells = c("MS4A1", "CD79A", "CD79B", "BANK1"),
    Plasma_cells = c("MZB1", "JCHAIN", "SDC1", "XBP1"),
    Monocytes_Macrophages = c("LYZ", "CD68", "AIF1", "LST1"),
    Dendritic_cells = c("FCER1A", "CLEC10A", "ITGAX", "LILRA4"),
    Endothelial_cells = c("PECAM1", "VWF", "KDR", "CLDN5"),
    Fibroblasts = c("DCN", "LUM", "COL1A1", "COL1A2"),
    Smooth_muscle_cells = c("ACTA2", "MYH11", "TAGLN", "CNN1"),
    Epithelial_cells = c("EPCAM", "KRT8", "KRT18", "KRT19"),
    Mast_cells = c("TPSAB1", "TPSB2", "CPA3", "KIT"),
    Neutrophils = c("S100A8", "S100A9", "FCGR3B", "CSF3R"),
    Pericytes = c("RGS5", "PDGFRB", "CSPG4", "MCAM")
  )
}

read_marker_db <- function(path) {
  tab <- utils::read.csv(path.expand(path), stringsAsFactors = FALSE, check.names = FALSE)
  missing <- setdiff(c("celltype", "gene"), colnames(tab))
  if (length(missing)) stop("Marker file requires columns: celltype, gene")
  tab <- tab[nzchar(tab$celltype) & nzchar(tab$gene), , drop = FALSE]
  split(tab$gene, tab$celltype)
}

marker_db_for_analysis <- function(cfg, ctx) {
  if (!is.null(cfg$annotation$marker_file)) return(read_marker_db(cfg$annotation$marker_file))
  db <- default_marker_db(cfg$project$species)
  if (!length(db)) log_msg(ctx, "No built-in marker database for ", cfg$project$species,
                           "; provide annotation.marker_file", level = "WARN")
  db
}

marker_score_annotation <- function(object, cfg, ctx) {
  db <- lapply(marker_db_for_analysis(cfg, ctx), function(x) intersect(unique(x), rownames(object)))
  db <- db[vapply(db, length, integer(1)) >= 2L]
  if (!length(db)) {
    object$celltype_marker <- "Unknown"
    return(object)
  }
  old_cols <- colnames(object@meta.data)
  object <- Seurat::AddModuleScore(object, features = db, name = "auto_marker_score_", search = FALSE)
  score_cols <- setdiff(colnames(object@meta.data), old_cols)
  score_cols <- score_cols[grepl("^auto_marker_score_", score_cols)]
  score <- object@meta.data[, score_cols, drop = FALSE]
  colnames(score) <- names(db)[seq_len(ncol(score))]
  object$celltype_marker <- colnames(score)[max.col(as.matrix(score), ties.method = "first")]
  object
}

singler_annotation <- function(object, cfg, ctx) {
  object$celltype_singleR <- NA_character_
  species <- species_key(cfg$project$species)
  if (!species %in% c("human", "mouse")) {
    log_msg(ctx, "SingleR built-in references are disabled for ", species, level = "WARN")
    return(object)
  }
  if (!isTRUE(cfg$annotation$use_singler) ||
      !require_packages(module_packages()$annotation, "SingleR annotation", optional = TRUE, ctx = ctx)) return(object)
  refs <- if (species == "mouse") {
    ref <- celldex::MouseRNAseqData()
    list(refs = list(MouseRNAseq = ref), labels = list(ref$label.main))
  } else {
    hpca <- celldex::HumanPrimaryCellAtlasData()
    blueprint <- celldex::BlueprintEncodeData()
    list(refs = list(HPCA = hpca, BlueprintEncode = blueprint), labels = list(hpca$label.main, blueprint$label.main))
  }
  data <- get_assay_data_safe(object, layer = "data")
  pred <- SingleR::SingleR(test = data, ref = refs$refs, labels = refs$labels, clusters = object$seurat_clusters)
  map <- setNames(pred$labels, rownames(pred))
  object$celltype_singleR <- unname(map[as.character(object$seurat_clusters)])
  save_table(ctx, data.frame(cluster = rownames(pred), label = pred$labels), "02_cluster_annotation_singleR.csv")
  object
}

apply_external_annotation <- function(object, path) {
  ann <- utils::read.csv(path, stringsAsFactors = FALSE)
  missing <- setdiff(c("seurat_cluster", "celltype"), colnames(ann))
  if (length(missing)) stop("External annotation file requires: seurat_cluster, celltype")
  map <- setNames(ann$celltype, as.character(ann$seurat_cluster))
  object$celltype <- unname(map[as.character(object$seurat_clusters)])
  object$celltype[is.na(object$celltype) | !nzchar(object$celltype)] <- paste0("Cluster_", object$seurat_clusters[is.na(object$celltype) | !nzchar(object$celltype)])
  object$celltype_status <- "reviewed_external"
  object
}

run_annotation <- function(object, cfg, ctx) {
  if (!is.null(cfg$annotation$external_annotation_file)) return(apply_external_annotation(object, path.expand(cfg$annotation$external_annotation_file)))
  object$celltype_marker <- NA_character_
  object$celltype_singleR <- NA_character_
  if (isTRUE(cfg$annotation$use_marker_scores)) object <- marker_score_annotation(object, cfg, ctx)
  object <- singler_annotation(object, cfg, ctx)
  auto <- ifelse(!is.na(object$celltype_singleR) & nzchar(object$celltype_singleR), object$celltype_singleR, object$celltype_marker)
  auto[is.na(auto) | !nzchar(auto)] <- "Unknown"
  votes <- as.data.frame(table(cluster = object$seurat_clusters, label = auto), stringsAsFactors = FALSE)
  votes <- votes[votes$Freq > 0, , drop = FALSE]
  votes <- votes[order(votes$cluster, -votes$Freq), , drop = FALSE]
  majority <- votes[!duplicated(votes$cluster), , drop = FALSE]
  totals <- aggregate(Freq ~ cluster, votes, sum)
  majority$total_cells <- totals$Freq[match(majority$cluster, totals$cluster)]
  majority$proposal_fraction <- majority$Freq / majority$total_cells
  map <- setNames(as.character(majority$label), as.character(majority$cluster))
  object$celltype_auto <- unname(map[as.character(object$seurat_clusters)])
  if (isTRUE(cfg$annotation$accept_auto_labels)) {
    object$celltype <- object$celltype_auto
    object$celltype_status <- "provisional_auto"
  } else {
    object$celltype <- paste0("Cluster_", object$seurat_clusters)
    object$celltype_status <- "review_required"
  }
  review <- data.frame(
    seurat_cluster = majority$cluster,
    proposed_celltype = majority$label,
    proposal_fraction = majority$proposal_fraction,
    cells = majority$total_cells,
    reviewed_celltype = "",
    notes = "",
    stringsAsFactors = FALSE
  )
  save_table(ctx, review, "02_cluster_annotation_review.csv")
  save_table(ctx, stats::setNames(review[, c("seurat_cluster", "reviewed_celltype")], c("seurat_cluster", "celltype")), "02_external_annotation_template.csv")
  save_table(ctx, data.frame(cell = colnames(object), object@meta.data, check.names = FALSE), "02_cell_metadata_annotation.csv")
  p <- Seurat::DimPlot(object, group.by = "celltype", label = TRUE, repel = TRUE) + ggplot2::ggtitle("Cell types requiring review")
  save_plot(ctx, p, "03_UMAP_celltype.pdf", 9, 7, cfg)
  object
}
