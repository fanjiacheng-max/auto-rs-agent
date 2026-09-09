"""Fetch a small public seed corpus for local RAG smoke testing."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from app.rag.vector_store import RagDocument


USER_AGENT = "auto-rs-agent-local-rag/0.1"


def _get_json(url: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fetch_uniprot(accession: str = "P04637") -> list[RagDocument]:
    url = f"https://rest.uniprot.org/uniprotkb/{urllib.parse.quote(accession)}.json"
    record = _get_json(url)
    common = {
        "source": "uniprot",
        "record_id": record.get("primaryAccession", accession),
        "entity_id": record.get("primaryAccession", accession),
        "entity_type": "protein",
        "species_taxid": record.get("organism", {}).get("taxonId", ""),
        "url": f"https://www.uniprot.org/uniprotkb/{accession}",
        "retrieved_at": _now(),
    }
    docs: list[RagDocument] = []
    for index, comment in enumerate(record.get("comments", [])):
        section = str(comment.get("commentType", "")).lower().replace(" ", "_")
        texts = []
        for item in comment.get("texts", []):
            if isinstance(item, dict):
                texts.append(str(item.get("value", "")))
            elif item:
                texts.append(str(item))
        if not texts:
            continue
        text = " ".join(texts).strip()
        docs.append(RagDocument(
            id=f"uniprot:{accession}:{section}:{index}",
            text=f"UniProt {accession} {section}: {text}",
            metadata={**common, "section": section},
        ))
    return docs


def fetch_reactome(stable_id: str = "R-HSA-5633007") -> list[RagDocument]:
    url = f"https://reactome.org/ContentService/data/query/{urllib.parse.quote(stable_id)}"
    record = _get_json(url)
    names = record.get("name") or [record.get("displayName", stable_id)]
    text = (
        f"Reactome event {stable_id}: {record.get('displayName', '')}. "
        f"Names: {', '.join(str(item) for item in names)}. "
        f"Species: {record.get('speciesName', '')}."
    )
    return [RagDocument(
        id=f"reactome:{stable_id}", text=text,
        metadata={
            "source": "reactome", "record_id": stable_id, "entity_id": "TP53",
            "entity_type": "protein", "species_taxid": 9606,
            "section": "event", "url": f"https://reactome.org/content/detail/{stable_id}",
            "retrieved_at": _now(),
        },
    )]


def fetch_open_targets(ensembl_id: str = "ENSG00000141510") -> list[RagDocument]:
    query = {
        "query": """
        query($id: String!) {
          target(ensemblId: $id) {
            id approvedSymbol
            associatedDiseases(page: {index: 0, size: 5}) {
              rows { score disease { id name } }
            }
          }
        }
        """,
        "variables": {"id": ensembl_id},
    }
    record = _get_json("https://api.platform.opentargets.org/api/v4/graphql", payload=query)
    target = (record.get("data") or {}).get("target") or {}
    docs = []
    for row in (target.get("associatedDiseases") or {}).get("rows", []):
        disease = row.get("disease") or {}
        disease_id = disease.get("id", "unknown")
        text = (
            f"Open Targets association: target {target.get('approvedSymbol', ensembl_id)} "
            f"({ensembl_id}) is associated with disease or phenotype "
            f"{disease.get('name', disease_id)} ({disease_id}); "
            f"aggregated association score: {row.get('score', '')}."
        )
        docs.append(RagDocument(
            id=f"open_targets:{ensembl_id}:{disease_id}", text=text,
            metadata={
                "source": "open_targets", "record_id": disease_id,
                "entity_id": ensembl_id, "entity_type": "gene", "species_taxid": 9606,
                "section": "target_disease_association", "disease_id": disease_id,
                "score": row.get("score", ""),
                "url": f"https://platform.opentargets.org/target/{ensembl_id}/associations",
                "retrieved_at": _now(),
            },
        ))
    return docs


def fetch_europe_pmc(query: str = 'TP53 AND cancer', page_size: int = 5) -> list[RagDocument]:
    params = urllib.parse.urlencode({"query": query, "format": "json", "resultType": "core", "pageSize": page_size})
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?{params}"
    record = _get_json(url)
    docs = []
    for index, paper in enumerate((record.get("resultList") or {}).get("result", [])):
        pmid = str(paper.get("pmid") or paper.get("id") or f"result-{index}")
        title = str(paper.get("title", "")).strip()
        abstract = str(paper.get("abstractText", "")).strip()
        text = f"{title}\n{abstract}".strip()
        if not text:
            continue
        docs.append(RagDocument(
            id=f"europe_pmc:{pmid}", text=text,
            metadata={
                "source": "europe_pmc", "record_id": pmid, "entity_id": "TP53",
                "entity_type": "gene", "species_taxid": 9606, "section": "title_abstract",
                "title": title, "doi": paper.get("doi", ""),
                "url": f"https://europepmc.org/article/MED/{pmid}",
                "retrieved_at": _now(),
            },
        ))
    return docs


def fetch_seed_documents() -> list[RagDocument]:
    """Fetch sources independently so one outage does not hide other evidence."""
    fetchers = (fetch_uniprot, fetch_reactome, fetch_open_targets, fetch_europe_pmc)
    documents: list[RagDocument] = []
    errors: list[str] = []
    for fetcher in fetchers:
        try:
            documents.extend(fetcher())
        except Exception as exc:  # preserve partial-source builds
            errors.append(f"{fetcher.__name__}: {type(exc).__name__}: {exc}")
    if not documents:
        raise RuntimeError("No public seed documents were fetched: " + " | ".join(errors))
    return documents
