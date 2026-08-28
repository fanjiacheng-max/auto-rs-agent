input_fingerprint_for_pipeline <- function(cfg, ctx) {
  paths <- list.files(ctx$raw_dir, recursive = TRUE, full.names = TRUE)
  file_fingerprint(paths, mode = cfg$input$fingerprint_mode)
}

run_pipeline <- function(cfg) {
  set.seed(cfg$project$seed)
  options(stringsAsFactors = FALSE, timeout = 7200, future.globals.maxSize = 16 * 1024^3)
  Sys.setenv(LANGUAGE = "en")
  ctx <- create_context(cfg)
  validate_environment(cfg, ctx)
  input_fp <- input_fingerprint_for_pipeline(cfg, ctx)
  force <- isTRUE(cfg$output$force_recompute)
  object <- cache_run(
    ctx, "01_combined_raw",
    function() build_combined(cfg, ctx),
    cfg_fragment = list(project = cfg$project, input = cfg$input),
    input_fingerprint = input_fp,
    critical = TRUE, force = force, cfg = cfg
  )
  if (isTRUE(cfg$qc$enabled)) {
    object <- cache_run(ctx, "02_qc", function() run_qc(object, cfg, ctx),
                        cfg_fragment = cfg$qc, input_fingerprint = object_fingerprint(object),
                        default = object, critical = TRUE, force = force, cfg = cfg)
  }
  if (isTRUE(cfg$integration$enabled)) {
    object <- cache_run(ctx, "03_integrated", function() run_integration(object, cfg, ctx),
                        cfg_fragment = cfg$integration, input_fingerprint = object_fingerprint(object),
                        default = object, critical = TRUE, force = force, cfg = cfg)
    safe_run(ctx, "basic_embedding_plots", function() plot_basic_embeddings(object, cfg, ctx), cfg = cfg)
  }
  if (isTRUE(cfg$annotation$enabled)) {
    object <- cache_run(ctx, "04_annotated", function() run_annotation(object, cfg, ctx),
                        cfg_fragment = cfg$annotation, input_fingerprint = object_fingerprint(object),
                        default = object, critical = FALSE, force = force, cfg = cfg)
  } else {
    object$celltype <- paste0("Cluster_", object$seurat_clusters)
  }
  results <- list()
  results$markers <- if (isTRUE(cfg$markers$enabled)) cache_run(
    ctx, "05_markers", function() run_markers(object, cfg, ctx), cfg$markers,
    input_fingerprint = object_fingerprint(object), default = data.frame(), force = force, cfg = cfg
  ) else data.frame()
  results$differential <- cache_run(
    ctx, "06_differential", function() run_differential_module(object, cfg, ctx), cfg$differential,
    input_fingerprint = object_fingerprint(object), default = list(exploratory = data.frame(), pseudobulk = data.frame()),
    force = force, cfg = cfg
  )
  results$composition <- if (isTRUE(cfg$composition$enabled)) cache_run(
    ctx, "07_composition", function() run_composition(object, cfg, ctx), cfg$composition,
    input_fingerprint = object_fingerprint(object), default = NULL, force = force, cfg = cfg
  ) else NULL
  results$enrichment <- if (isTRUE(cfg$enrichment$enabled)) cache_run(
    ctx, "08_enrichment", function() run_enrichment(results$differential, cfg, ctx), cfg$enrichment,
    input_fingerprint = hash_object(results$differential), default = data.frame(), force = force, cfg = cfg
  ) else data.frame()
  if (isTRUE(cfg$pathway_scores$enabled)) {
    object <- cache_run(ctx, "09_pathway_scores", function() run_pathway_scores(object, cfg, ctx), cfg$pathway_scores,
                        input_fingerprint = object_fingerprint(object), default = object, force = force, cfg = cfg)
  }
  results$pseudotime <- if (isTRUE(cfg$pseudotime$enabled)) cache_run(
    ctx, "10_pseudotime", function() run_pseudotime(object, cfg, ctx), cfg$pseudotime,
    input_fingerprint = object_fingerprint(object), default = NULL, force = force, cfg = cfg
  ) else NULL
  results$cellchat <- if (isTRUE(cfg$cellchat$enabled)) cache_run(
    ctx, "11_cellchat", function() run_cellchat(object, cfg, ctx), cfg$cellchat,
    input_fingerprint = object_fingerprint(object), default = list(), force = force, cfg = cfg
  ) else list()
  results$hdwgcna <- if (isTRUE(cfg$hdwgcna$enabled)) cache_run(
    ctx, "12_hdwgcna", function() run_hdwgcna(object, cfg, ctx), cfg$hdwgcna,
    input_fingerprint = object_fingerprint(object), default = list(), force = force, cfg = cfg
  ) else list()
  safe_run(ctx, "final_export", function() export_results(object, results, cfg, ctx), critical = TRUE, cfg = cfg)
  invisible(list(object = object, results = results, context = ctx))
}
