# Scientific guardrails

## Sample metadata

Never assign Disease, Control, Treatment, donor, sex, or batch from filenames as final truth. Filename parsing may produce a candidate review table only. Require an explicit sample sheet before formal comparisons.

## QC

Apply thresholds per sample when sample quality differs. Inspect total counts, detected genes, mitochondrial fraction, and doublet calls jointly. Do not use one universal mitochondrial cutoff across all tissues and protocols without justification.

## Batch correction

Check whether batch is confounded with condition. If every disease sample is in one batch and every control sample in another, correction cannot separate technical and biological effects reliably. Report this design limitation rather than presenting corrected clusters as proof.

## Annotation

Validate each label with positive markers, negative markers, cluster-level expression, tissue context, and expected abundance. Preserve `provisional_auto` labels until review. Avoid interpreting CellChat or lineage results from unreviewed labels.

## Differential expression

Use sample-level pseudobulk for formal condition comparisons. Cells are not independent biological replicates. Report the number of samples per group and per cell type. Treat cell-level `FindMarkers` as exploratory only.

## Composition

A Wilcoxon test on per-sample proportions can be exploratory. For complex designs, repeated measures, or covariates, recommend an appropriate compositional model rather than overclaiming from simple tests.

## Enrichment

Use a defined gene universe when possible. Separate up- and downregulated genes. Do not describe pathway enrichment as direct pathway activation without supporting evidence.

## Pseudotime

Pseudotime is an ordering, not measured chronological time. Restrict to a coherent lineage, define the root using biology, inspect branch stability, and avoid mixing unrelated mature cell types.

## CellChat

CellChat predicts communication potential from expression and curated databases. It does not demonstrate physical interaction or signaling flux. Compare matched groups with adequate replicate structure and stable annotations.

## hdWGCNA

Build networks within a justified cell type. Ensure adequate cells and samples, inspect soft-power behavior, module sizes, eigengenes, and sample-level consistency. Hub genes are network-central candidates, not automatically causal regulators.

## Failure handling

Optional modules may fail softly, but a generated PDF is not evidence that the upstream analysis succeeded. Always check `module_status.csv`, logs, and result tables before interpretation.
