#!/usr/bin/env python3
"""Inspect local scRNA-seq inputs and build a reviewable sample-sheet template."""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

SUPPORTED_SUFFIXES = {
    ".h5": "h5",
    ".h5ad": "h5ad",
    ".loom": "loom",
    ".rds": "robj",
    ".rdata": "robj",
    ".csv": "dense",
    ".tsv": "dense",
    ".txt": "dense",
}
ARCHIVE_SUFFIXES = (".zip", ".tar", ".tgz", ".tar.gz")
EXCLUDED_DENSE = re.compile(
    r"^(barcodes|features|genes)(\.tsv|\.txt|\.csv)?(\.gz)?$|matrix\.mtx|annotation|metadata|sample[_-]?sheet",
    re.I,
)
GENERIC_10X_DIRS = {
    "filtered_feature_bc_matrix",
    "raw_feature_bc_matrix",
    "filtered_gene_bc_matrices",
    "raw_gene_bc_matrices",
}


def clean_sample_name(path: Path) -> str:
    candidate = path
    if path.is_dir() and path.name.lower() in GENERIC_10X_DIRS:
        candidate = path.parent
    name = re.sub(
        r"\.(txt|csv|tsv|mtx|h5|h5ad|loom|rds|rdata)(\.gz)?$",
        "",
        candidate.name,
        flags=re.I,
    )
    name = re.sub(r"^GSM[0-9]+[_-]?", "", name, flags=re.I)
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).rstrip("_")
    return name or "sample"


def candidate_paths(root: Path) -> Iterable[Path]:
    if root.is_file():
        yield root
    else:
        yield from root.rglob("*")


def looks_like_10x_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    names = {p.name.lower() for p in path.iterdir() if p.is_file()}
    has_matrix = "matrix.mtx" in names or "matrix.mtx.gz" in names
    has_features = any(x in names for x in ("features.tsv", "features.tsv.gz", "genes.tsv", "genes.tsv.gz"))
    has_barcodes = "barcodes.tsv" in names or "barcodes.tsv.gz" in names
    return has_matrix and has_features and has_barcodes


def inspect_directory(root: Path) -> dict[str, Any]:
    specs: list[dict[str, str]] = []
    archives: list[str] = []
    seen_10x: set[Path] = set()
    matrices = root.rglob("matrix.mtx*") if root.is_dir() else []

    for matrix in matrices:
        directory = matrix.parent
        if directory not in seen_10x and looks_like_10x_dir(directory):
            seen_10x.add(directory)
            specs.append({"type": "10xdir", "sample": clean_sample_name(directory), "path": str(directory)})

    for path in candidate_paths(root):
        if not path.is_file():
            continue
        lower = path.name.lower()
        if lower.endswith(ARCHIVE_SUFFIXES):
            archives.append(str(path))
            continue
        if path.parent in seen_10x:
            continue
        suffix = ".rdata" if lower.endswith(".rdata") else path.suffix.lower()
        kind = SUPPORTED_SUFFIXES.get(suffix)
        if kind is None or (kind == "dense" and EXCLUDED_DENSE.search(lower)):
            continue
        specs.append({"type": kind, "sample": clean_sample_name(path), "path": str(path)})

    specs.sort(key=lambda item: (item["sample"], item["type"], item["path"]))
    counts = Counter(item["type"] for item in specs)
    duplicate_samples = sorted(name for name, n in Counter(item["sample"] for item in specs).items() if n > 1)
    warnings: list[str] = []
    if duplicate_samples:
        warnings.append("Multiple inputs resolve to the same candidate sample name; review sample identifiers.")
    if any(item["type"] == "h5ad" for item in specs):
        warnings.append("H5AD inputs require an explicit raw-count assay/layer; X is not assumed to contain counts.")
    if any(item["type"] == "dense" for item in specs):
        warnings.append("Dense matrices require orientation review and can use substantial memory.")
    return {
        "input_path": str(root),
        "supported_inputs": specs,
        "counts_by_type": dict(sorted(counts.items())),
        "archives": sorted(archives),
        "duplicate_sample_names": duplicate_samples,
        "warnings": warnings,
        "review_required": bool(duplicate_samples or not specs),
    }


def inspect_sample_sheet(path: Path | None, detected_samples: set[str]) -> dict[str, Any]:
    if path is None:
        return {
            "provided": False,
            "valid": False,
            "errors": ["No sample sheet supplied. QC and clustering may run, but formal group comparisons are gated."],
            "missing_detected_samples": sorted(detected_samples),
        }
    if not path.is_file():
        return {"provided": True, "valid": False, "errors": [f"Sample sheet not found: {path}"]}

    errors: list[str] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        rows = list(reader)
    missing_columns = sorted({"sample", "group"}.difference(fields))
    if missing_columns:
        errors.append("Missing columns: " + ", ".join(missing_columns))
    samples = [str(row.get("sample", "")).strip() for row in rows]
    groups = [str(row.get("group", "")).strip() for row in rows]
    duplicates = sorted(name for name, n in Counter(samples).items() if name and n > 1)
    if duplicates:
        errors.append("Duplicate sample names: " + ", ".join(duplicates))
    if any(not value for value in samples):
        errors.append("One or more rows have an empty sample value")
    if any(not value or value == "REVIEW_REQUIRED" for value in groups):
        errors.append("One or more rows require a reviewed group value")
    sheet_samples = set(samples)
    missing_detected = sorted(detected_samples.difference(sheet_samples))
    extra_sheet = sorted(sheet_samples.difference(detected_samples))
    if missing_detected:
        errors.append("Detected inputs absent from sample sheet: " + ", ".join(missing_detected))
    return {
        "provided": True,
        "path": str(path),
        "valid": not errors,
        "errors": errors,
        "n_rows": len(rows),
        "groups": dict(sorted(Counter(groups).items())),
        "missing_detected_samples": missing_detected,
        "extra_sheet_samples": extra_sheet,
    }


def write_sample_sheet_template(path: Path, samples: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sample", "group", "donor", "batch"])
        for sample in samples:
            writer.writerow([sample, "REVIEW_REQUIRED", "", ""])


def render_markdown(report: dict[str, Any]) -> str:
    directory = report["directory"]
    lines = [
        "# scRNA-seq input inspection",
        "",
        f"- Input path: `{directory['input_path']}`",
        f"- Supported inputs: {len(directory['supported_inputs'])}",
        f"- Review required: {'yes' if report['review_required'] else 'no'}",
        "",
        "## Detected inputs",
        "",
    ]
    if directory["supported_inputs"]:
        lines.extend(["| Type | Candidate sample | Path |", "|---|---|---|"])
        for item in directory["supported_inputs"]:
            lines.append(f"| {item['type']} | {item['sample']} | `{item['path']}` |")
    else:
        lines.append("No supported input was detected.")
    if directory["warnings"]:
        lines.extend(["", "## Input warnings", ""])
        lines.extend(f"- {warning}" for warning in directory["warnings"])
    lines.extend(["", "## Sample sheet", "", f"- Valid: {'yes' if report['sample_sheet'].get('valid') else 'no'}"])
    lines.extend(f"- {error}" for error in report["sample_sheet"].get("errors", []))
    if report.get("sample_sheet_template"):
        lines.append(f"- Template: `{report['sample_sheet_template']}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_path")
    parser.add_argument("--sample-sheet")
    parser.add_argument("--sample-sheet-template")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output")
    args = parser.parse_args()

    root = Path(args.input_path).expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"Input path not found: {root}")
    directory = inspect_directory(root)
    detected = {item["sample"] for item in directory["supported_inputs"]}
    sheet_path = Path(args.sample_sheet).expanduser().resolve() if args.sample_sheet else None
    sample_sheet = inspect_sample_sheet(sheet_path, detected)
    report = {
        "directory": directory,
        "sample_sheet": sample_sheet,
        "review_required": directory["review_required"] or not sample_sheet.get("valid", False),
    }
    if args.sample_sheet_template:
        template = Path(args.sample_sheet_template).expanduser().resolve()
        write_sample_sheet_template(template, sorted(detected))
        report["sample_sheet_template"] = str(template)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n" if args.format == "json" else render_markdown(report)
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if directory["supported_inputs"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
