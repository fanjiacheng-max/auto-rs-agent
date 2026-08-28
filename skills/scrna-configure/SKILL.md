---
name: scrna-configure
description: Bootstrap a scRNA-seq analysis project and generate a configuration file from reviewed input data and sample sheet. Run after scrna-inspect and sample sheet review. Produces a ready-to-run config.R for the R pipeline.
---

# scRNA-seq Project Setup and Configuration

## Purpose
Set up the analysis project directory and generate a validated config.R. Requires a reviewed sample sheet.

## Prerequisites
- Input data inspected (input_inspection.md exists)
- Sample sheet reviewed (no `REVIEW_REQUIRED` entries for formal analysis)
- Species confirmed

## Steps

### 1. Bootstrap project directory

```bash
python skills/geo-scrna-workflow/scripts/bootstrap_project.py \
  {workspace}/scrna_project
```

This copies the R pipeline template into the workspace. **Only bootstrap once per project.**

### 2. Generate configuration

For local data:
```bash
python skills/geo-scrna-workflow/scripts/generate_config.py \
  {workspace}/scrna_project/config/analysis.R \
  --input-dir /path/to/input \
  --sample-sheet {workspace}/inputs/sample_sheet_review.csv \
  --project-name {project_name} \
  --species {species} \
  --contrast {case_group} {control_group}
```

For GEO:
```bash
python skills/geo-scrna-workflow/scripts/generate_config.py \
  {workspace}/scrna_project/config/analysis.R \
  --gse GSE123456 \
  --sample-sheet {workspace}/inputs/sample_sheet_review.csv \
  --project-name {project_name} \
  --species {species} \
  --contrast {case_group} {control_group}
```

Replace all `{...}` placeholders with actual values.

### 3. Run preflight validation

```bash
python skills/geo-scrna-workflow/scripts/preflight.py \
  {workspace}/scrna_project \
  --config {workspace}/scrna_project/config/analysis.R \
  --output {workspace}/scrna_project/preflight.json
```

Read `preflight.json` and report any errors to the user. Do not proceed if critical errors exist.

### 4. Confirm to user
Report:
- Config file location
- Preflight status (pass/warn/fail)
- Next step: run `scrna-qc` to begin analysis

## References
- Config options: `skills/geo-scrna-workflow/references/config-guide.md`
- Data format specifics: `skills/geo-scrna-workflow/references/data-adaptation.md`
