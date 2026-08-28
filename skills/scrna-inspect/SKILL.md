---
name: scrna-inspect
description: Inspect local single-cell RNA-seq input data (10x, H5, H5AD, loom, RDS, count matrix) or a GEO accession. Generates an input inspection report and a sample sheet template for review. Use this as the first step before configuring any scRNA-seq analysis.
---

# scRNA-seq Input Inspection

## Purpose
Profile the input data before any analysis. Never infer species, group labels, batch, or sample identity from filenames alone.

## Steps

### 1. Identify input source
Ask the user (or read from project state) whether the source is a GEO accession (e.g. `GSE123456`) or a local file/directory.

### 2. Run inspection

```bash
python skills/geo-scrna-workflow/scripts/inspect_input.py /path/to/input \
  --sample-sheet-template {workspace}/inputs/sample_sheet_review.csv \
  --format markdown \
  --output {workspace}/inputs/input_inspection.md
```

Replace `/path/to/input` with the actual input path, and `{workspace}` with the project workspace directory.

For a GEO accession, first ensure the data is downloaded under `{workspace}/inputs/`, then run inspection on that directory.

### 3. Report to user
Read `{workspace}/inputs/input_inspection.md` and summarise:
- Detected format and sample count
- Candidate sample names
- Detected species (if any)
- Any warnings or ambiguities

### 4. Review sample sheet
The generated `{workspace}/inputs/sample_sheet_review.csv` contains `REVIEW_REQUIRED` placeholders. Inform the user which fields need to be filled in before formal analysis can proceed.

## References
- Detailed format guidance: `skills/geo-scrna-workflow/references/data-adaptation.md`
