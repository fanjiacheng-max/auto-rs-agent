select_trajectory_cells <- function(object, cfg) {
  celltypes <- cfg$pseudotime$celltypes
  if (is.null(celltypes) || !length(celltypes)) stop("pseudotime.celltypes must be specified explicitly")
  cells <- rownames(object@meta.data)[object$celltype %in% celltypes]
  if (length(cells) > cfg$pseudotime$max_cells) cells <- sample(cells, cfg$pseudotime$max_cells)
  if (length(cells) < 100L) stop("Too few selected cells for pseudotime: ", length(cells))
  cells
}

run_slingshot <- function(object, cells, cfg, ctx) {
  if (!require_packages(module_packages()$slingshot, "Slingshot", optional = FALSE, ctx = ctx)) return(NULL)
  sub <- object[, cells]
  counts <- get_assay_data_safe(sub, assay = cfg$input$assay, layer = "counts")
  data <- get_assay_data_safe(sub, layer = "data")
  sce <- SingleCellExperiment::SingleCellExperiment(
    assays = list(counts = counts, logcounts = data),
    colData = sub@meta.data
  )
  sce <- SingleCellExperiment::`reducedDim<-`(sce, "UMAP", value = Seurat::Embeddings(sub, "umap"))
  sce <- slingshot::slingshot(
    sce,
    clusterLabels = "seurat_clusters",
    reducedDim = "UMAP",
    start.clus = cfg$pseudotime$root_cluster
  )
  pt_matrix <- slingshot::slingPseudotime(sce)
  pseudotime <- apply(pt_matrix, 1, function(x) if (all(is.na(x))) NA_real_ else min(x, na.rm = TRUE))
  metadata <- as.data.frame(SummarizedExperiment::colData(sce))
  metadata$cell <- rownames(metadata)
  metadata$pseudotime <- pseudotime[rownames(metadata)]
  save_table(ctx, metadata, "10_slingshot_pseudotime.csv")
  list(object = sce, metadata = metadata)
}

run_monocle3 <- function(object, cells, cfg, ctx) {
  require_packages("monocle3", "Monocle3", optional = FALSE, ctx = ctx)
  sub <- object[, cells]
  counts <- get_assay_data_safe(sub, assay = cfg$input$assay, layer = "counts")
  gene_metadata <- data.frame(gene_short_name = rownames(counts), row.names = rownames(counts))
  cds <- monocle3::new_cell_data_set(counts, cell_metadata = sub@meta.data, gene_metadata = gene_metadata)
  cds <- monocle3::preprocess_cds(cds, num_dim = max(cfg$integration$dims))
  cds <- monocle3::reduce_dimension(cds)
  cds <- monocle3::cluster_cells(cds)
  cds <- monocle3::learn_graph(cds)
  if (is.null(cfg$pseudotime$root_cluster)) stop("Monocle3 requires pseudotime.root_cluster")
  root_cells <- rownames(sub@meta.data)[as.character(sub$seurat_clusters) == as.character(cfg$pseudotime$root_cluster)]
  if (!length(root_cells)) stop("No cells found for root cluster: ", cfg$pseudotime$root_cluster)
  cds <- monocle3::order_cells(cds, root_cells = root_cells)
  metadata <- as.data.frame(SummarizedExperiment::colData(cds))
  metadata$cell <- rownames(metadata)
  metadata$pseudotime <- monocle3::pseudotime(cds)[rownames(metadata)]
  save_table(ctx, metadata, "10_monocle3_pseudotime.csv")
  list(object = cds, metadata = metadata)
}

run_pseudotime <- function(object, cfg, ctx) {
  cells <- select_trajectory_cells(object, cfg)
  method <- tolower(cfg$pseudotime$method)
  if (method == "slingshot") return(run_slingshot(object, cells, cfg, ctx))
  if (method == "monocle3") return(run_monocle3(object, cells, cfg, ctx))
  stop("Supported pseudotime methods in modular_v1: slingshot, monocle3")
}
