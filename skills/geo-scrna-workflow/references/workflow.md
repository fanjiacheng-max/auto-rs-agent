# Workflow reference

## 1. Intake

Resolve the source, species, raw-count location, sample identity, group, donor, technical batch, contrast, tissue context, and requested modules. Do not infer final metadata or species from filenames.

For local data, inspect first and generate a review table:

```bash
python scripts/inspect_input.py /path/to/input \
  --sample-sheet-template /path/to/work/sample_sheet_review.csv \
  --format markdown --output /path/to/work/input_inspection.md
```

## 2. Project preparation

```bash
python scripts/bootstrap_project.py /path/to/work/scrna_project
```

Edit the copied project only. Keep the bundled asset unchanged during an analysis.

## 3. Configure the real data

```bash
python scripts/generate_config.py /path/to/work/scrna_project/config/my_data.R \
  --input-dir /path/to/input \
  --sample-sheet /path/to/work/sample_sheet_review.csv \
  --project-name my_study --species human \
  --contrast Treated Control
```

For GEO, use `--gse`. For RDS/H5AD/dense inputs, explicitly review metadata columns, count layers, and orientation as described in [data-adaptation.md](data-adaptation.md).

## 4. Preflight

```bash
python scripts/preflight.py /path/to/work/scrna_project \
  --config /path/to/work/scrna_project/config/my_data.R \
  --output /path/to/work/scrna_project/preflight.json
```

Preflight always runs the Python static checker. When R is present, it also parses all R files, merges the configuration, and runs semantic validation. Distinguish static validation from R runtime validation.

## 5. Core run

```bash
cd /path/to/work/scrna_project
Rscript run_pipeline.R config/my_data.R
```

The core pass should include intake, QC, normalization, PCA, clustering, provisional annotation, markers, design eligibility, and export. Advanced modules remain off.

## 6. Review and rerun

Review input matching, per-sample QC retention, resolved PC/batch decisions, cluster annotation, and pseudobulk eligibility. Create a reviewed `seurat_cluster,celltype` mapping and rerun with `annotation.external_annotation_file` before relying on cell-type-specific downstream analyses.

## 7. Completion criteria

A run is complete only when critical modules are successful, sample/group assignments are reviewed, raw counts are verified, annotation status is explicit, formal DE uses adequate biological replication, and every enabled advanced module satisfies its scientific prerequisites.
