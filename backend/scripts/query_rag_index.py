"""Query the local biomedical evidence index without an LLM/API key."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.rag.vector_store import BiomedicalVectorStore


def main() -> int:
    question = " ".join(sys.argv[1:]).strip() or "What is the function and disease relevance of TP53?"
    store = BiomedicalVectorStore(ROOT / "workspace" / "rag" / "index")
    rows = store.query(question, n_results=5)
    print(f"collection_count={store.count()}")
    for index, row in enumerate(rows, start=1):
        print(f"\n[{index}] distance={row['distance']:.4f} source={row['metadata'].get('source')} id={row['id']}")
        print(row["text"][:1000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
