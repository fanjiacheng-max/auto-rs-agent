run_composition <- function(object, cfg, ctx) {
  meta <- object@meta.data
  counts <- as.data.frame(table(sample = meta$sample, celltype = meta$celltype), stringsAsFactors = FALSE)
  sample_group <- unique(meta[, c("sample", "group"), drop = FALSE])
  counts$group <- sample_group$group[match(counts$sample, sample_group$sample)]
  totals <- aggregate(Freq ~ sample, counts, sum)
  names(totals)[2L] <- "total"
  counts$total <- totals$total[match(counts$sample, totals$sample)]
  counts$proportion <- counts$Freq / counts$total
  save_table(ctx, counts, "06_celltype_proportion_by_sample.csv")
  tests <- data.frame()
  contrast <- cfg$composition$contrast
  if (length(contrast) == 2L && all(contrast %in% counts$group)) {
    tests <- do.call(rbind, lapply(split(counts, counts$celltype), function(df) {
      df <- df[df$group %in% contrast, , drop = FALSE]
      p <- tryCatch(stats::wilcox.test(proportion ~ group, data = df)$p.value, error = function(e) NA_real_)
      data.frame(celltype = df$celltype[1L], p_value = p)
    }))
    tests$p_adjust <- stats::p.adjust(tests$p_value, method = "BH")
    save_table(ctx, tests, "07_celltype_proportion_wilcoxon_exploratory.csv")
  }
  p <- ggplot2::ggplot(counts, ggplot2::aes(x = sample, y = proportion, fill = celltype)) +
    ggplot2::geom_col() + ggplot2::theme_classic() +
    ggplot2::theme(axis.text.x = ggplot2::element_text(angle = 45, hjust = 1)) +
    ggplot2::labs(title = "Cell-type composition by sample", x = NULL, y = "Proportion")
  save_plot(ctx, p, "04_celltype_composition_by_sample.pdf", 12, 7, cfg)
  list(proportions = counts, tests = tests)
}
