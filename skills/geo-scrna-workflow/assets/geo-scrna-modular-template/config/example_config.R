CFG <- list(
  project = list(
    gse = "GSE155468",
    species = "human",
    work_root = "~/GEO_scRNA_pipeline",
    input_dir = NULL,
    sample_sheet = NULL
  ),
  integration = list(
    batch_method = "harmony",
    resolution = 0.5
  ),
  differential = list(
    contrast = c("Disease", "Control")
  ),
  pseudotime = list(enabled = FALSE),
  cellchat = list(enabled = FALSE),
  hdwgcna = list(enabled = FALSE)
)
