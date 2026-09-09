"""Evidence assembly tests. Only external source adapters are replaced."""

import asyncio
import copy
import json

from tests.rag.support import (
    FixtureSource, OfflineAsyncCase, evidence, require_api, resolved_candidate,
)


class EvidenceTests(OfflineAsyncCase):
    async def collect(self, sources, query=None):
        fn = require_api(self, "collect_evidence")
        return await fn(query or resolved_candidate(), sources=sources)

    async def test_evidence_retains_source_and_analysis_provenance(self):
        query = resolved_candidate()
        hit = evidence()
        source = FixtureSource("fixture_primary", [hit])
        result = await self.collect([source], query)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["candidate"], query)
        self.assertEqual(len(result["evidence"]), 1)
        item = result["evidence"][0]
        self.assertTrue(item["evidence_id"])
        self.assertEqual(item["claim"], hit["claim"])
        self.assertEqual(item["sources"], [hit["source"]])
        self.assertEqual(item["evidence_type"], "experimental")
        self.assertEqual(item["relation_to_result"], "supporting")
        for field in ("tissue", "cell_type", "disease", "direction", "canonical_id", "species_taxid"):
            self.assertEqual(item[field], hit[field], field)
        self.assertEqual(source.requests, [query])
        json.dumps(result, allow_nan=False)  # Can be sent back as a real tool_result.

    async def test_same_claim_and_paper_across_databases_merges_provenance(self):
        first = evidence()
        second = evidence()
        second["source"].update(database="fixture_secondary", record_id="TEST_RECORD_2",
                                url="https://example.org/secondary-record")
        result = await self.collect([
            FixtureSource("fixture_primary", [first]),
            FixtureSource("fixture_secondary", [second]),
        ])
        self.assertEqual(len(result["evidence"]), 1)
        self.assertEqual(result["independent_publications"], 1)
        self.assertCountEqual(result["evidence"][0]["sources"], [first["source"], second["source"]])

    async def test_doi_url_and_case_variants_do_not_double_count_a_paper(self):
        first = evidence()
        first["source"].update(pmid=None, doi="10.0000/Synthetic-Study-1")
        second = evidence()
        second["source"].update(database="fixture_secondary", pmid=None,
                                doi="https://doi.org/10.0000/synthetic-study-1")
        result = await self.collect([
            FixtureSource("fixture_primary", [first]),
            FixtureSource("fixture_secondary", [second]),
        ])
        self.assertEqual(len(result["evidence"]), 1)
        self.assertEqual(result["independent_publications"], 1)

    async def test_conflicting_claims_from_same_paper_are_preserved(self):
        support = evidence()
        conflict = evidence(claim="Synthetic experiment reported decreased RNA abundance.",
                            relation_to_result="conflicting", direction="down")
        conflict["source"]["record_id"] = "TEST_RECORD_CONFLICT"
        result = await self.collect([FixtureSource("fixture_primary", [support, conflict])])
        self.assertEqual(len(result["evidence"]), 2)
        self.assertEqual(len({r["evidence_id"] for r in result["evidence"]}), 2)
        self.assertEqual({r["relation_to_result"] for r in result["evidence"]},
                         {"supporting", "conflicting"})
        self.assertEqual({r["claim"] for r in result["evidence"]},
                         {support["claim"], conflict["claim"]})
        self.assertEqual(result["independent_publications"], 1)

    async def test_same_claim_from_two_independent_papers_counts_as_two(self):
        first = evidence()
        second = evidence()
        second["source"].update(record_id="TEST_RECORD_3", pmid="999999992",
                                doi="10.0000/synthetic-study-2",
                                url="https://example.org/synthetic-study-2")
        result = await self.collect([FixtureSource("fixture_primary", [first, second])])
        self.assertEqual(len(result["evidence"]), 2)
        self.assertEqual(result["independent_publications"], 2)

    async def test_wrong_entity_and_species_cannot_support_this_candidate(self):
        wrong_gene = evidence(canonical_id="TEST_ENSG_OTHER")
        wrong_species = evidence(species_taxid=10090)
        result = await self.collect([FixtureSource("fixture_primary", [wrong_gene, wrong_species])])
        self.assertEqual(result["evidence"], [])
        self.assertEqual(result["status"], "no_evidence")
        self.assertEqual({r["reason"] for r in result["rejected"]},
                         {"entity_mismatch", "species_mismatch"})

    async def test_untraceable_record_is_rejected_without_inventing_a_citation(self):
        hit = evidence()
        del hit["source"]["url"]
        result = await self.collect([FixtureSource("fixture_primary", [hit])])
        self.assertEqual(result["evidence"], [])
        self.assertEqual(result["rejected"][0]["reason"], "missing_provenance")

    async def test_other_tissue_is_retained_as_background_not_direct_support(self):
        hit = evidence(tissue="other_tissue", cell_type="other_cell_type")
        result = await self.collect([FixtureSource("fixture_primary", [hit])])
        item = result["evidence"][0]
        self.assertEqual(item["tissue"], "other_tissue")
        self.assertEqual(item["cell_type"], "other_cell_type")
        self.assertEqual(item["relation_to_result"], "background")
        self.assertIn("tissue", item["context_mismatches"])
        self.assertIn("cell_type", item["context_mismatches"])

    async def test_prediction_and_association_score_are_not_promoted_to_confidence(self):
        hit = evidence(evidence_type="prediction", relation_to_result="background",
                       source_score={"value": 0.92, "kind": "association_score"})
        result = await self.collect([FixtureSource("fixture_primary", [hit])])
        item = result["evidence"][0]
        self.assertEqual(item["evidence_type"], "prediction")
        self.assertEqual(item["source_score"], hit["source_score"])
        self.assertNotIn("confidence", item)
        self.assertNotIn("causal_probability", item)
        self.assertNotIn("confidence", result)

    async def test_successful_empty_search_is_no_evidence(self):
        result = await self.collect([FixtureSource("fixture_primary")])
        self.assertEqual(result["status"], "no_evidence")
        self.assertEqual(result["evidence"], [])
        self.assertEqual(result["independent_publications"], 0)
        self.assertEqual(result["source_status"]["fixture_primary"]["status"], "ok")

    async def test_database_annotation_without_paper_is_valid_but_not_a_publication(self):
        hit = evidence(evidence_type="curated_annotation", relation_to_result="background")
        hit["source"].update(pmid=None, doi=None)
        result = await self.collect([FixtureSource("fixture_primary", [hit])])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["evidence"]), 1)
        self.assertEqual(result["independent_publications"], 0)
        self.assertEqual(result["evidence"][0]["sources"][0]["url"], hit["source"]["url"])

    async def test_unresolved_identity_is_rejected_before_any_source_query(self):
        query = resolved_candidate()
        del query["entity"]
        source = FixtureSource("fixture_primary", [evidence()])
        fn = require_api(self, "collect_evidence")
        with self.assertRaisesRegex(ValueError, "entity"):
            await fn(query, sources=[source])
        self.assertEqual(source.requests, [])

    async def test_one_source_timeout_keeps_other_evidence_and_reports_partial_result(self):
        result = await self.collect([
            FixtureSource("fixture_primary", [evidence()]),
            FixtureSource("fixture_secondary", error=TimeoutError("fixture timeout")),
        ])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["evidence"]), 1)
        status = result["source_status"]["fixture_secondary"]
        self.assertEqual(status["status"], "error")
        self.assertIn("timeout", status["error"].lower())
        self.assertEqual(result["source_status"]["fixture_primary"]["status"], "ok")

    async def test_all_sources_failing_is_not_a_negative_biological_result(self):
        result = await self.collect([
            FixtureSource("fixture_primary", error=TimeoutError("fixture timeout")),
            FixtureSource("fixture_secondary", error=ConnectionError("fixture unavailable")),
        ])
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["evidence"], [])
        self.assertEqual(set(result["source_status"]), {"fixture_primary", "fixture_secondary"})
        self.assertTrue(all(r["status"] == "error" for r in result["source_status"].values()))

    async def test_timeout_plus_successful_empty_search_still_reports_incomplete_search(self):
        result = await self.collect([
            FixtureSource("fixture_primary"),
            FixtureSource("fixture_secondary", error=TimeoutError("fixture timeout")),
        ])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["evidence"], [])

    async def test_user_cancellation_propagates_instead_of_becoming_no_evidence(self):
        fn = require_api(self, "collect_evidence")
        with self.assertRaises(asyncio.CancelledError):
            await fn(resolved_candidate(), sources=[
                FixtureSource("fixture_primary", error=asyncio.CancelledError()),
            ])

    async def test_collecting_evidence_does_not_mutate_analysis_results(self):
        query = resolved_candidate()
        original = copy.deepcopy(query)
        await self.collect([FixtureSource("fixture_primary", [evidence()])], query)
        self.assertEqual(query, original)
