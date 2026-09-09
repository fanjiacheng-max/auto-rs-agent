"""Build the first local biomedical evidence vector index.

Run from the repository root with the backend on PYTHONPATH:
    PYTHONPATH=backend python backend/scripts/build_rag_index.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.rag.seed_sources import fetch_seed_documents
from app.rag.vector_store import BiomedicalVectorStore


def main() -> int:
    rag_root = ROOT / "workspace" / "rag"
    raw_root = rag_root / "normalized"
    index_root = rag_root / "index"
    raw_root.mkdir(parents=True, exist_ok=True)
    documents = fetch_seed_documents()

    normalized_path = raw_root / "seed_documents.jsonl"
    with normalized_path.open("w", encoding="utf-8") as stream:
        for document in documents:
            stream.write(json.dumps({"id": document.id, "text": document.text, "metadata": dict(document.metadata)}, ensure_ascii=False) + "\n")

    store = BiomedicalVectorStore(index_root)
    inserted = store.upsert(documents)
    manifest = {
        "schema_version": "1",
        "embedding": store.embedding_function.name(),
        "collection": "biomedical_evidence",
        "documents_fetched": len(documents),
        "documents_upserted": inserted,
        "collection_count": store.count(),
        "seed_entity": "TP53",
        "sources": sorted({str(doc.metadata.get("source", "")) for doc in documents}),
    }
    (rag_root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
