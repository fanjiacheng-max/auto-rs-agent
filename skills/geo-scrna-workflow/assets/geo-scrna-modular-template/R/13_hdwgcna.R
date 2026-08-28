prepare_legacy_assay_copy <- function(object, assay, ctx) {
  copy <- object
  if (utils::packageVersion("Seurat") >= "5.0.0") copy <- tryCatch(SeuratObject::JoinLayers(copy), error = function(e) copy)
  if (!assay %in% names(copy@assays)) stop("Assay not found: ", assay)
  if (inherits(copy[[assay]], c("Assay5", "StdAssay"))) {
    copy[[assay]] <- tryCatch(as(copy[[assay]], "Assay"), error = function(e) {
      stop("Could not convert Assay5 to legacy Assay for hdWGCNA: ", conditionMessage(e))
    })
    log_msg(ctx, "Converted assay to legacy Assay in hdWGCNA working copy")
  }
  copy
}

run_hdwgcna_one <- function(object, celltype, cfg, ctx) {
  require_packages(module_packages()$hdwgcna, "hdWGCNA", optional = FALSE, ctx = ctx)
  if (sum(object$celltype == celltype) < 500L) stop("Too few cells for hdWGCNA cell type: ", celltype)
  work <- prepare_legacy_assay_copy(object, cfg$input$assay, ctx)
  network_name <- safe_file_name(celltype)
  work <- call_supported("hdWGCNA", "SetupForWGCNA", list(
    seurat_obj = work,
    gene_select = "fraction",
    fraction = cfg$hdwgcna$fraction,
    wgcna_name = network_name
  ))
  work <- call_supported("hdWGCNA", "MetacellsByGroups", list(
    seurat_obj = work,
    group.by = c("celltype", "sample"),
    k = cfg$hdwgcna$metacell_k,
    max_shared = cfg$hdwgcna$metacell_max_shared,
    ident.group = "celltype",
    wgcna_name = network_name
  ))
  work <- call_supported("hdWGCNA", "NormalizeMetacells", list(seurat_obj = work, wgcna_name = network_name))
  work <- call_supported("hdWGCNA", "SetDatExpr", list(
    seurat_obj = work,
    group_name = celltype,
    group.by = "celltype",
    assay = cfg$input$assay,
    slot = "data",
    wgcna_name = network_name
  ))
  if (is.null(cfg$hdwgcna$soft_power)) {
    work <- call_supported("hdWGCNA", "TestSoftPowers", list(
      seurat_obj = work,
      networkType = cfg$hdwgcna$network_type,
      wgcna_name = network_name
    ))
  }
  construct_args <- list(
    seurat_obj = work,
    tom_name = network_name,
    networkType = cfg$hdwgcna$network_type,
    minModuleSize = cfg$hdwgcna$min_module_size,
    mergeCutHeight = cfg$hdwgcna$merge_cut_height,
    wgcna_name = network_name,
    overwrite_tom = TRUE
  )
  if (!is.null(cfg$hdwgcna$soft_power)) construct_args$soft_power <- cfg$hdwgcna$soft_power
  work <- call_supported("hdWGCNA", "ConstructNetwork", construct_args)
  work <- call_supported("hdWGCNA", "ModuleEigengenes", list(seurat_obj = work, group.by.vars = "sample", wgcna_name = network_name))
  work <- call_supported("hdWGCNA", "ModuleConnectivity", list(seurat_obj = work, group.by = "celltype", group_name = celltype, wgcna_name = network_name))
  modules <- tryCatch(hdWGCNA::GetModules(work, wgcna_name = network_name), error = function(e) data.frame())
  hubs <- tryCatch(hdWGCNA::GetHubGenes(work, n_hubs = 20, wgcna_name = network_name), error = function(e) data.frame())
  if (nrow(modules)) save_table(ctx, modules, paste0("12_hdwgcna_modules_", network_name, ".csv"))
  if (nrow(hubs)) save_table(ctx, hubs, paste0("12_hdwgcna_hubs_", network_name, ".csv"))
  work
}

run_hdwgcna <- function(object, cfg, ctx) {
  targets <- cfg$hdwgcna$target_celltypes
  if (is.null(targets) || !length(targets)) stop("hdwgcna.target_celltypes must be specified explicitly")
  setNames(lapply(targets, function(celltype) run_hdwgcna_one(object, celltype, cfg, ctx)), targets)
}
