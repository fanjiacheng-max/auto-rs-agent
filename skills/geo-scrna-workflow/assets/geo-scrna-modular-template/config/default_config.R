default_config <- function() {
  list(
    project = list(
      gse = NULL,
      project_name = "scrna_analysis",
      species = NULL,
      work_root = ".",
      output_prefix = NULL,
      input_dir = NULL,
      raw_dir = NULL,
      sample_sheet = NULL,
      seed = 123L
    ),
    input = list(
      assay = "RNA",
      feature_type = "Gene Expression",
      sample_column = "sample",
      group_column = "group",
      matrix_orientation = "auto",
      h5ad_counts_layer = "counts",
      allow_h5ad_x_as_counts = FALSE,
      preserve_object_metadata = TRUE,
      min_cells = 3L,
      min_features = 200L,
      download_geo_if_needed = TRUE,
      decompress_archives = TRUE,
      fingerprint_mode = "size_mtime"
    ),
    qc = list(
      enabled = TRUE,
      nmads = 3,
      max_percent_mt = NULL,
      run_doublet = TRUE,
      min_cells_after_qc = 100L,
      min_cells_per_sample_after_qc = 20L,
      fail_on_sample_loss = TRUE
    ),
    integration = list(
      enabled = TRUE,
      use_sctransform = FALSE,
      nfeatures = 3000L,
      dims = NULL,
      max_npcs = 30L,
      variance_target = 0.9,
      resolution = 0.5,
      batch_method = "auto",
      batch_variable = "batch",
      regress_variables = c("percent.mt"),
      run_tsne = FALSE
    ),
    annotation = list(
      enabled = TRUE,
      use_singler = TRUE,
      use_marker_scores = TRUE,
      marker_file = NULL,
      accept_auto_labels = FALSE,
      external_annotation_file = NULL
    ),
    markers = list(
      enabled = TRUE,
      min_pct = 0.25,
      logfc_threshold = 0.25,
      only_positive = TRUE
    ),
    differential = list(
      exploratory_cell_level = FALSE,
      pseudobulk = TRUE,
      contrast = c("Disease", "Control"),
      covariates = NULL,
      min_cells_per_celltype = 50L,
      min_cells_per_sample_celltype = 20L,
      min_samples_per_group = 3L
    ),
    composition = list(
      enabled = TRUE,
      contrast = c("Disease", "Control")
    ),
    enrichment = list(
      enabled = TRUE,
      ontology = "BP",
      p_adjust_cutoff = 0.05,
      logfc_cutoff = 0.25,
      min_genes = 10L,
      show_categories = 12L
    ),
    pathway_scores = list(
      enabled = TRUE,
      signature_file = NULL
    ),
    pseudotime = list(
      enabled = FALSE,
      method = "slingshot",
      celltypes = NULL,
      root_cluster = NULL,
      max_cells = 12000L
    ),
    cellchat = list(
      enabled = FALSE,
      min_cells = 30L,
      max_celltypes = 18L,
      max_cells_per_celltype = 700L,
      max_cells_total = 25000L,
      database_category = NULL
    ),
    hdwgcna = list(
      enabled = FALSE,
      target_celltypes = NULL,
      fraction = 0.05,
      metacell_k = 25L,
      metacell_max_shared = 10L,
      soft_power = NULL,
      network_type = "signed",
      min_module_size = 30L,
      merge_cut_height = 0.25
    ),
    output = list(
      force_recompute = FALSE,
      stop_on_critical_failure = TRUE,
      pdf_family = "sans",
      validate_pdf = TRUE,
      save_png_copy = FALSE,
      checkpoint_version = "adaptive_v2"
    )
  )
}
