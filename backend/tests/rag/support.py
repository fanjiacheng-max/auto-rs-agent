"""Synthetic fixtures and external-source doubles, not RAG implementations."""

import copy
import importlib
import unittest
from unittest.mock import patch


def require_api(case, name):
    """Keep discovery working while the proposed production API is absent."""
    try:
        module = importlib.import_module("app.agent.rag")
    except ModuleNotFoundError as exc:
        if exc.name != "app.agent.rag":
            raise  # A missing dependency is an environment error, not expected RED.
        case.fail(f"RAG not implemented: app.agent.rag.{name} is required")
    fn = getattr(module, name, None)
    case.assertTrue(callable(fn), f"RAG API not implemented: app.agent.rag.{name}")
    return fn


class OfflineCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        for target in ("socket.create_connection", "socket.socket.connect"):
            guard = patch(target, side_effect=AssertionError("Live network forbidden in offline tests"))
            guard.start()
            self.addCleanup(guard.stop)


class OfflineAsyncCase(OfflineCase, unittest.IsolatedAsyncioTestCase):
    pass


def candidate(**changes):
    value = {
        "input_id": "TEST_GENE_A",
        "id_namespace": "symbol",
        "entity_type": "gene",
        "species_taxid": 9606,
        "omics": "transcriptomics",
        "tissue": "test_tissue",
        "cell_type": "test_cell_type",
        "disease": "test_disease",
        "contrast": ["case", "control"],
        "effect_size": 1.5,
        "effect_measure": "log2_fold_change",
        "direction": "up",
        "padj": 0.01,
        "analysis_type": "pseudobulk_edgeR",
        "n_samples_group1": 4,
        "n_samples_group2": 4,
        "result_ref": {"path": "results/tables/synthetic_de.csv", "row": 2},
    }
    value.update(copy.deepcopy(changes))
    return value


def entity(**changes):
    value = {
        "canonical_id": "TEST_ENSG_A",
        "id_namespace": "ensembl_gene",
        "entity_type": "gene",
        "species_taxid": 9606,
        "symbol": "TEST_GENE_A",
        "aliases": ["TEST_ALIAS_A"],
    }
    value.update(copy.deepcopy(changes))
    return value


def resolved_candidate(**changes):
    value = candidate(entity=entity())
    value.update(copy.deepcopy(changes))
    return value


def evidence(**changes):
    """All biological statements and identifiers here are fictitious."""
    value = {
        "canonical_id": "TEST_ENSG_A",
        "species_taxid": 9606,
        "claim": "Synthetic experiment reported increased RNA abundance.",
        "evidence_type": "experimental",
        "relation_to_result": "supporting",
        "tissue": "test_tissue",
        "cell_type": "test_cell_type",
        "disease": "test_disease",
        "direction": "up",
        "source": {
            "database": "fixture_primary",
            "record_id": "TEST_RECORD_1",
            "url": "https://example.org/synthetic-study-1",
            "pmid": "999999991",
            "doi": "10.0000/synthetic-study-1",
            "retrieved_at": "2026-09-09T00:00:00Z",
            "version": "fixture-v1",
        },
    }
    value.update(copy.deepcopy(changes))
    return value


class FixtureSource:
    """Double for the proposed normalized adapter boundary, not a real API."""
    def __init__(self, name, records=(), error=None):
        self.name = name
        self.records = copy.deepcopy(list(records))
        self.error = error
        self.requests = []

    async def search(self, query):
        self.requests.append(copy.deepcopy(query))
        if self.error is not None:
            raise self.error
        return copy.deepcopy(self.records)
