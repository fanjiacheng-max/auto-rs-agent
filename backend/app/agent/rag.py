"""Candidate normalization and evidence assembly for the Agent RAG tool.

The module is deliberately provider agnostic.  ``collect_evidence`` accepts
small async source adapters, so tests can use fixtures while production can
plug in the local Chroma store, UniProt, Reactome, Open Targets, or Europe PMC.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping


def _number(value: Any) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def load_candidates(
    path: str | Path,
    *,
    context: Mapping[str, Any],
    columns: Mapping[str, str],
    fdr_max: float = 0.05,
    min_abs_log2fc: float = 1.0,
) -> dict[str, list[dict[str, Any]]]:
    """Read a differential table and retain statistically interpretable hits."""
    if not math.isfinite(fdr_max) or not 0 <= fdr_max <= 1:
        raise ValueError("fdr_max must be between 0 and 1")
    if not math.isfinite(min_abs_log2fc) or min_abs_log2fc < 0:
        raise ValueError("min_abs_log2fc must be non-negative")
    for required in ("species_taxid", "contrast"):
        if context.get(required) in (None, "", []):
            raise ValueError(f"{required} is required")
    fdr_column = columns.get("padj")
    effect_column = columns.get("effect_size")
    id_column = columns.get("input_id")
    if not fdr_column or not effect_column or not id_column:
        raise ValueError("columns must define input_id, effect_size, and padj")

    table_path = Path(path)
    delimiter = "\t" if table_path.suffix.lower() in {".tsv", ".tab"} else ","
    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    with table_path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream, delimiter=delimiter)
        if not reader.fieldnames or fdr_column not in reader.fieldnames:
            raise ValueError(f"adjusted p-value column {fdr_column!r} (FDR) is missing")
        for row_number, row in enumerate(reader, start=2):
            identifier = (row.get(id_column) or "").strip()
            effect = _number(row.get(effect_column))
            padj = _number(row.get(fdr_column))
            if not identifier or effect is None or padj is None or not 0 <= padj <= 1:
                excluded.append({"input_id": identifier, "row": row_number, "reason": "invalid_statistics"})
                continue
            if padj > fdr_max:
                excluded.append({"input_id": identifier, "row": row_number, "reason": "fdr"})
                continue
            if abs(effect) < min_abs_log2fc:
                excluded.append({"input_id": identifier, "row": row_number, "reason": "effect_size"})
                continue
            contrast = row.get(columns.get("contrast", ""), context.get("contrast"))
            if isinstance(contrast, str) and " vs " in contrast:
                observed = [part.strip() for part in contrast.split(" vs ", 1)]
                expected = list(context["contrast"])
                if observed != expected:
                    raise ValueError("contrast in result row conflicts with analysis context")
            item = deepcopy(dict(context))
            item.update({
                "input_id": identifier,
                "effect_size": effect,
                "effect_measure": "log2_fold_change",
                "padj": padj,
                "direction": "up" if effect > 0 else "down",
                "cell_type": row.get(columns.get("cell_type", "")) or None,
                "n_samples_group1": _integer_or_none(row.get(columns.get("n_samples_group1", ""))),
                "n_samples_group2": _integer_or_none(row.get(columns.get("n_samples_group2", ""))),
                "result_ref": {"path": str(table_path), "row": row_number},
            })
            candidates.append(item)
    return {"candidates": candidates, "excluded": excluded}


def _integer_or_none(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number.is_integer() else None


def resolve_entity(query: Mapping[str, Any], matches: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Resolve exact namespaced IDs/aliases without fuzzy biological guesses."""
    identifier = str(query.get("input_id", "")).casefold()
    namespace = query.get("id_namespace")
    entity_type = query.get("entity_type")
    species = query.get("species_taxid")
    eligible = [m for m in matches if m.get("species_taxid") == species and (not entity_type or m.get("entity_type") == entity_type)]
    exact = [m for m in eligible if m.get("id_namespace") == namespace and str(m.get("canonical_id", "")).casefold() == identifier]
    if not exact:
        exact = [m for m in eligible if str(m.get("symbol", "")).casefold() == identifier or any(str(a).casefold() == identifier for a in m.get("aliases", []))]
    unique = {str(m.get("canonical_id")): m for m in exact}
    if len(unique) == 1:
        return {"status": "resolved", "entity": next(iter(unique.values())), "matches": list(unique.values())}
    if len(unique) > 1:
        return {"status": "ambiguous", "entity": None, "matches": list(unique.values())}
    return {"status": "not_found", "entity": None, "matches": []}


async def collect_evidence(candidate: Mapping[str, Any], *, sources: Iterable[Any]) -> dict[str, Any]:
    """Query independent sources and assemble traceable, deduplicated evidence."""
    if not candidate.get("entity"):
        raise ValueError("candidate entity is required before querying evidence")
    source_status: dict[str, dict[str, Any]] = {}
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    had_error = False
    successful = 0
    for source in sources:
        name = str(getattr(source, "name", source.__class__.__name__))
        try:
            records = await source.search(deepcopy(dict(candidate)))
            source_status[name] = {"status": "ok"}
            successful += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # source failure is isolated from other sources
            had_error = True
            source_status[name] = {"status": "error", "error": str(exc)}
            continue
        for raw in records or []:
            item = deepcopy(raw)
            if item.get("canonical_id") != candidate["entity"].get("canonical_id"):
                rejected.append({"reason": "entity_mismatch", "record": item})
                continue
            if item.get("species_taxid") != candidate.get("species_taxid"):
                rejected.append({"reason": "species_mismatch", "record": item})
                continue
            source_info = item.get("source") or {}
            if not source_info.get("url"):
                rejected.append({"reason": "missing_provenance", "record": item})
                continue
            mismatches = [field for field in ("tissue", "cell_type") if item.get(field) not in (None, candidate.get(field))]
            item["context_mismatches"] = mismatches
            if mismatches and item.get("relation_to_result") == "supporting":
                item["relation_to_result"] = "background"
            item["sources"] = [source_info]
            item["evidence_id"] = hashlib.sha256(
                (str(item.get("claim", "")) + "|" + _publication_key(source_info)).encode("utf-8")
            ).hexdigest()[:20]
            accepted.append(item)

    merged: dict[str, dict[str, Any]] = {}
    for item in accepted:
        key = (str(item.get("claim", "")).strip().casefold(), _publication_key(item["sources"][0]))
        if key in merged:
            merged[key]["sources"].extend(item["sources"])
        else:
            merged[key] = item
    evidence = list(merged.values())
    publications = {
        key
        for item in evidence
        for source in item["sources"]
        for key in (_publication_key(source),)
        if key.startswith(("pmid:", "doi:"))
    }
    if had_error and successful:
        status = "partial"
    elif had_error:
        status = "error"
    elif evidence:
        status = "ok"
    else:
        status = "no_evidence"
    return {
        "status": status,
        "candidate": deepcopy(dict(candidate)),
        "evidence": evidence,
        "source_status": source_status,
        "independent_publications": len(publications),
        "rejected": rejected,
    }


def _publication_key(source: Mapping[str, Any]) -> str:
    if source.get("pmid"):
        return "pmid:" + str(source["pmid"]).strip()
    doi = str(source.get("doi") or "").strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    if doi:
        return "doi:" + doi
    return str(source.get("record_id") or source.get("url") or "")


__all__ = ["load_candidates", "resolve_entity", "collect_evidence"]
