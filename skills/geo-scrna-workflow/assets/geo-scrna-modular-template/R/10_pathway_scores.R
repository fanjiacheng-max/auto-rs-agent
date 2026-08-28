default_pathway_signatures <- function(species) {
  key <- species_key(species)
  if (!key %in% c("human", "mouse")) return(list())
  if (key == "mouse") {
    return(list(
      Inflammation = c("Il1b", "Tnf", "Cxcl2", "Ccl2", "Nfkbia", "Ptgs2"),
      Interferon = c("Isg15", "Ifit1", "Ifit2", "Ifit3", "Mx1", "Oas1a"),
      Fibrosis = c("Col1a1", "Col1a2", "Col3a1", "Fn1", "Postn", "Acta2"),
      Hypoxia = c("Hif1a", "Vegfa", "Ldha", "Eno1", "Slc2a1", "Car9"),
      CellCycle = c("Mki67", "Top2a", "Pcna", "Stmn1", "Ube2c", "Mcm5")
    ))
  }
  list(
    Inflammation = c("IL1B", "TNF", "CXCL8", "CCL2", "NFKBIA", "PTGS2"),
    Interferon = c("ISG15", "IFIT1", "IFIT2", "IFIT3", "MX1", "OAS1"),
    Fibrosis = c("COL1A1", "COL1A2", "COL3A1", "FN1", "POSTN", "ACTA2"),
    Hypoxia = c("HIF1A", "VEGFA", "LDHA", "ENO1", "SLC2A1", "CA9"),
    CellCycle = c("MKI67", "TOP2A", "PCNA", "STMN1", "UBE2C", "MCM5")
  )
}

read_signature_file <- function(path) {
  path <- path.expand(path)
  if (grepl("\\.gmt$", path, ignore.case = TRUE)) {
    lines <- strsplit(readLines(path, warn = FALSE), "\t", fixed = TRUE)
    return(setNames(lapply(lines, function(x) unique(x[-c(1L, 2L)])), vapply(lines, function(x) x[[1L]], character(1))))
  }
  tab <- utils::read.csv(path, stringsAsFactors = FALSE, check.names = FALSE)
  missing <- setdiff(c("signature", "gene"), colnames(tab))
  if (length(missing)) stop("Signature CSV requires columns: signature, gene")
  split(tab$gene[nzchar(tab$gene)], tab$signature[nzchar(tab$gene)])
}

run_pathway_scores <- function(object, cfg, ctx) {
  signatures <- if (is.null(cfg$pathway_scores$signature_file)) {
    default_pathway_signatures(cfg$project$species)
  } else {
    read_signature_file(cfg$pathway_scores$signature_file)
  }
  signatures <- lapply(signatures, function(x) intersect(unique(x), rownames(object)))
  signatures <- signatures[vapply(signatures, length, integer(1)) >= 2L]
  if (!length(signatures)) {
    log_msg(ctx, "No usable pathway signatures matched the object; provide a species-appropriate signature file", level = "WARN")
    return(object)
  }
  old_cols <- colnames(object@meta.data)
  object <- Seurat::AddModuleScore(object, features = signatures, name = "PathwayScore_", search = FALSE)
  score_cols <- setdiff(colnames(object@meta.data), old_cols)
  score_cols <- score_cols[grepl("^PathwayScore_", score_cols)]
  for (i in seq_along(score_cols)) object[[paste0(names(signatures)[i], "_score")]] <- object@meta.data[[score_cols[i]]]
  score_names <- paste0(names(signatures), "_score")
  table <- data.frame(cell = colnames(object), object@meta.data[, c("sample", "group", "celltype", score_names), drop = FALSE])
  save_table(ctx, table, "09_pathway_scores.csv")
  object
}
