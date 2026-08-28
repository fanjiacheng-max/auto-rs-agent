---
name: geo-scrna-workflow
description: Configure, run, troubleshoot, and review a data-adaptive single-cell RNA-seq workflow in R for GEO or local 10x/H5/H5AD/loom/RDS/count-matrix inputs. Use for Seurat QC, normalization, clustering, optional Harmony integration, provisional or reviewed cell annotation, markers, sample-level pseudobulk differential expression with covariates, composition, enrichment, pathway scores, pseudotime, CellChat, and hdWGCNA. Especially useful when adapting a reusable workflow to the user's own samples, metadata, tissue markers, count layers, and experimental design.
---

# Data-adaptive scRNA-seq workflow in R

## Core rule

Profile the data before configuring the analysis. Never infer species, biological groups, donors, batches, raw-count layers, or final cell types from filenames alone. The bundled project may run QC and clustering without group metadata, but it must gate formal comparisons until the sample design is reviewed.

## Start every task

1. Identify whether the source is a GEO accession or a local file/directory.
2. Inspect local inputs before copying or editing the project.
3. Resolve species explicitly.
4. Determine where sample, group, donor, and technical batch metadata live.
5. Confirm that raw integer counts are available, especially for H5AD and converted objects.
6. Read [references/data-adaptation.md](references/data-adaptation.md) when fitting the workflow to a new dataset.
7. Read [references/scientific-guardrails.md](references/scientific-guardrails.md) before enabling formal or advanced analyses.

## Inspect local data

Run:

```bash
python scripts/inspect_input.py /path/to/input \
  --sample-sheet-template /path/to/work/sample_sheet_review.csv \
  --format markdown \
  --output /path/to/work/input_inspection.md
```

Review candidate sample names and edit the generated sample sheet. `REVIEW_REQUIRED` is intentionally invalid for formal comparisons. A sample sheet is optional for a single-sample exploratory run, but required for trusted group-level analysis unless equivalent reviewed metadata is already embedded in a Seurat object.

## Bootstrap and configure

Copy the project template:

```bash
python scripts/bootstrap_project.py /path/to/work/scrna_project
```

Generate a local-data configuration:

```bash
python scripts/generate_config.py /path/to/work/scrna_project/config/my_data.R \
  --input-dir /path/to/input \
  --sample-sheet /path/to/work/sample_sheet_review.csv \
  --project-name my_study \
  --species human \
  --contrast Treated Control
```

For GEO, replace `--input-dir` with `--gse GSE...`. Species is always explicit. Do not leave example accessions or example group names in a production configuration.

Read [references/config-guide.md](references/config-guide.md) before changing input layers, matrix orientation, QC, batch correction, DE covariates, or annotation resources.

## Adapt biological resources

- For tissue-specific annotation, provide `annotation.marker_file` as CSV with `celltype,gene`.
- For reviewed labels, provide `annotation.external_annotation_file` as CSV with `seurat_cluster,celltype`.
- For custom pathway scores, provide a GMT file or CSV with `signature,gene`.
- For adjusted pseudobulk models, list sample-level fields in `differential.covariates`; donor can be used as a fixed effect for a paired design.
- Built-in marker and SingleR references are limited to human and mouse. Rat and zebrafish require explicit species-appropriate resources.

## Preflight and run

Run:

```bash
python scripts/preflight.py /path/to/work/scrna_project \
  --config /path/to/work/scrna_project/config/my_data.R \
  --output /path/to/work/scrna_project/preflight.json
```

When preflight passes:

```bash
cd /path/to/work/scrna_project
Rscript run_pipeline.R config/my_data.R
```

If `Rscript` is unavailable, report static validation only. Do not claim runtime validation or successful package-level execution.

## Mandatory review checkpoints

Inspect these before interpreting results:

- `results/tables/00_detected_input_specs.csv`
- `results/tables/00_sample_sheet_review.csv`
- `results/tables/01_QC_summary_by_sample.csv`
- `results/tables/02_integration_decisions.csv`
- `results/tables/02_cluster_annotation_review.csv`
- `results/tables/05_pseudobulk_eligibility.csv`
- `results/reports/module_status.csv`

Stop formal interpretation when samples are unmatched, raw counts are uncertain, a critical module failed, annotations remain implausible, or the pseudobulk eligibility table shows inadequate replication.

## Defaults and gates

- Use sample-aware MAD QC and review per-sample retention.
- Select the usable PCA range from explained variance when `integration.dims = NULL`.
- Use `batch_method = "auto"` to avoid automatic Harmony when the configured batch is absent or confounded with group.
- Keep automatic labels unaccepted until reviewed.
- Use sample-level pseudobulk for formal differential expression.
- Keep cell-level group DE exploratory and disabled by default.
- Keep pseudotime, CellChat, and hdWGCNA disabled until their biological prerequisites are explicit.

## Modify the template

Edit a bootstrapped copy, not `assets/geo-scrna-modular-template/` during an analysis. Preserve explicit `object`, `cfg`, and `ctx` interfaces, configuration-aware checkpoints, status reporting, and smoke tests. Update tests whenever input parsing, configuration semantics, or module interfaces change.

## Reporting

Use [references/output-contract.md](references/output-contract.md). State whether the work was statically validated, runtime validated, partially run, or fully completed. Separate computational output from biological interpretation and list every unresolved metadata or annotation decision.
