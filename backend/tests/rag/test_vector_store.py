"""Offline contract for the keyless persistent biomedical index."""

import tempfile
from pathlib import Path
import unittest

from app.rag.vector_store import BiomedicalVectorStore, RagDocument


class VectorStoreTests(unittest.TestCase):
    def test_examples_are_persistent_and_keep_provenance(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "index"
            first = BiomedicalVectorStore(path)
            first.upsert([
                RagDocument(
                    id="example:tp53:function",
                    text="TP53 is a transcription factor involved in apoptosis and DNA damage response.",
                    metadata={"source": "fixture", "entity_id": "P04637", "species_taxid": 9606},
                ),
                RagDocument(
                    id="example:brca1:function",
                    text="BRCA1 participates in homologous recombination DNA repair.",
                    metadata={"source": "fixture", "entity_id": "P38398", "species_taxid": 9606},
                ),
            ])
            self.assertEqual(first.count(), 2)
            reopened = BiomedicalVectorStore(path)
            self.assertEqual(reopened.count(), 2)
            hits = reopened.query("TP53 apoptosis DNA damage", n_results=1)
            self.assertEqual(hits[0]["metadata"]["entity_id"], "P04637")
            self.assertEqual(hits[0]["metadata"]["source"], "fixture")

    def test_candidate_query_prioritizes_exact_identity_and_species(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            store = BiomedicalVectorStore(Path(tmp) / "index")
            store.upsert([
                RagDocument("human:tp53", "TP53 apoptosis", {"entity_id": "P04637", "species_taxid": 9606}),
                RagDocument("mouse:tp53", "TP53 apoptosis", {"entity_id": "P04637", "species_taxid": 10090}),
                RagDocument("human:other", "BRCA1 DNA repair", {"entity_id": "P38398", "species_taxid": 9606}),
            ])
            hits = store.query_candidate({
                "species_taxid": 9606,
                "entity": {"canonical_id": "P04637", "symbol": "TP53"},
                "disease": "cancer",
            }, n_results=2)
            self.assertEqual(hits[0]["id"], "human:tp53")
            self.assertEqual(hits[0]["identity_match"], "exact")
            self.assertTrue(all(h["metadata"]["species_taxid"] == 9606 for h in hits))


if __name__ == "__main__":
    unittest.main()
