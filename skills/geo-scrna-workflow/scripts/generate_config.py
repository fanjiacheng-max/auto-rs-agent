#!/usr/bin/env python3
"""Generate a data-aware R configuration override for the modular pipeline."""
from __future__ import annotations

import argparse
from pathlib import Path


def r_string(value: str | None) -> str:
    if value is None:
        return "NULL"
    escaped = value.replace("\\", "/").replace('"', '\\"')
    return f'"{escaped}"'


def r_bool(value: bool) -> str:
    return "TRUE" if value else "FALSE"


def r_vector(values: list[str] | None) -> str:
    if not values:
        return "NULL"
    return "c(" + ", ".join(r_string(value) for value in values) + ")"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--gse")
    source.add_argument("--input-dir")
    parser.add_argument("--project-name", default="scrna_analysis")
    parser.add_argument("--species", choices=("human", "mouse", "rat", "zebrafish"), required=True)
    parser.add_argument("--work-root", default=".")
    parser.add_argument("--sample-sheet")
    parser.add_argument("--sample-column", default="sample")
    parser.add_argument("--group-column", default="group")
    parser.add_argument("--matrix-orientation", choices=("auto", "gene_by_cell", "cell_by_gene"), default="auto")
    parser.add_argument("--h5ad-counts-layer", default="counts")
    parser.add_argument("--allow-h5ad-x-as-counts", action="store_true")
    parser.add_argument("--batch-method", choices=("auto", "harmony", "none"), default="auto")
    parser.add_argument("--batch-variable", default="batch")
    parser.add_argument("--contrast", nargs=2, metavar=("TEST", "REFERENCE"), default=("Disease", "Control"))
    parser.add_argument("--de-covariates", nargs="+")
    parser.add_argument("--sctransform", action="store_true")
    parser.add_argument("--disable-annotation", action="store_true")
    parser.add_argument("--marker-file")
    parser.add_argument("--pathway-signature-file")
    parser.add_argument("--enable-exploratory-cell-de", action="store_true")
    parser.add_argument("--enable-pseudotime", action="store_true")
    parser.add_argument("--pseudotime-method", choices=("slingshot", "monocle3"), default="slingshot")
    parser.add_argument("--trajectory-celltypes", nargs="+")
    parser.add_argument("--root-cluster")
    parser.add_argument("--enable-cellchat", action="store_true")
    parser.add_argument("--enable-hdwgcna", action="store_true")
    parser.add_argument("--hdwgcna-celltypes", nargs="+")
    parser.add_argument("--force-recompute", action="store_true")
    args = parser.parse_args()

    if args.enable_pseudotime and (not args.trajectory_celltypes or args.root_cluster is None):
        raise SystemExit("Pseudotime requires --trajectory-celltypes and --root-cluster.")
    if args.enable_hdwgcna and not args.hdwgcna_celltypes:
        raise SystemExit("hdWGCNA requires --hdwgcna-celltypes.")

    test_group, reference_group = args.contrast
    text = f'''CFG <- list(
  project = list(
    gse = {r_string(args.gse)},
    project_name = {r_string(args.project_name)},
    output_prefix = {r_string(args.project_name)},
    species = {r_string(args.species)},
    work_root = {r_string(args.work_root)},
    input_dir = {r_string(args.input_dir)},
    sample_sheet = {r_string(args.sample_sheet)}
  ),
  input = list(
    sample_column = {r_string(args.sample_column)},
    group_column = {r_string(args.group_column)},
    matrix_orientation = {r_string(args.matrix_orientation)},
    h5ad_counts_layer = {r_string(args.h5ad_counts_layer)},
    allow_h5ad_x_as_counts = {r_bool(args.allow_h5ad_x_as_counts)}
  ),
  integration = list(
    use_sctransform = {r_bool(args.sctransform)},
    batch_method = {r_string(args.batch_method)},
    batch_variable = {r_string(args.batch_variable)},
    dims = NULL
  ),
  annotation = list(
    enabled = {r_bool(not args.disable_annotation)},
    accept_auto_labels = FALSE,
    marker_file = {r_string(args.marker_file)}
  ),
  differential = list(
    exploratory_cell_level = {r_bool(args.enable_exploratory_cell_de)},
    pseudobulk = TRUE,
    contrast = c({r_string(test_group)}, {r_string(reference_group)}),
    covariates = {r_vector(args.de_covariates)}
  ),
  composition = list(
    enabled = TRUE,
    contrast = c({r_string(test_group)}, {r_string(reference_group)})
  ),
  pathway_scores = list(
    enabled = TRUE,
    signature_file = {r_string(args.pathway_signature_file)}
  ),
  pseudotime = list(
    enabled = {r_bool(args.enable_pseudotime)},
    method = {r_string(args.pseudotime_method)},
    celltypes = {r_vector(args.trajectory_celltypes)},
    root_cluster = {r_string(args.root_cluster)}
  ),
  cellchat = list(enabled = {r_bool(args.enable_cellchat)}),
  hdwgcna = list(
    enabled = {r_bool(args.enable_hdwgcna)},
    target_celltypes = {r_vector(args.hdwgcna_celltypes)}
  ),
  output = list(
    force_recompute = {r_bool(args.force_recompute)},
    stop_on_critical_failure = TRUE
  )
)
'''
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
