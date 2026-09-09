"""Identity matching must precede biological interpretation."""

from tests.rag.support import OfflineCase, candidate, entity, require_api


class EntityTests(OfflineCase):
    def resolve(self, query, matches):
        return require_api(self, "resolve_entity")(query, matches)

    def test_alias_resolves_only_within_requested_species(self):
        human = entity()
        mouse = entity(canonical_id="TEST_MOUSE_A", species_taxid=10090)
        result = self.resolve(candidate(input_id="TEST_ALIAS_A"), [mouse, human])
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["entity"]["canonical_id"], "TEST_ENSG_A")
        self.assertEqual(result["entity"]["species_taxid"], 9606)

    def test_other_species_only_is_not_a_match(self):
        result = self.resolve(candidate(), [entity(species_taxid=10090)])
        self.assertEqual(result["status"], "not_found")
        self.assertIsNone(result["entity"])

    def test_ambiguous_alias_returns_candidates_without_choosing_first(self):
        matches = [entity(), entity(canonical_id="TEST_ENSG_B", symbol="TEST_GENE_B")]
        result = self.resolve(candidate(input_id="TEST_ALIAS_A"), matches)
        self.assertEqual(result["status"], "ambiguous")
        self.assertIsNone(result["entity"])
        self.assertEqual({m["canonical_id"] for m in result["matches"]},
                         {"TEST_ENSG_A", "TEST_ENSG_B"})

    def test_unknown_identifier_does_not_get_nearest_text_match(self):
        result = self.resolve(candidate(input_id="TEST_GENE_AA"), [entity()])
        self.assertEqual(result["status"], "not_found")
        self.assertIsNone(result["entity"])

    def test_duplicate_records_do_not_create_false_ambiguity(self):
        result = self.resolve(candidate(), [entity(), entity()])
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["entity"]["canonical_id"], "TEST_ENSG_A")

    def test_exact_namespaced_id_takes_precedence_over_alias_collision(self):
        other = entity(canonical_id="TEST_ENSG_B", aliases=["TEST_ENSG_A"])
        result = self.resolve(candidate(input_id="TEST_ENSG_A", id_namespace="ensembl_gene"),
                              [other, entity()])
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["entity"]["canonical_id"], "TEST_ENSG_A")

    def test_protein_isoform_is_not_replaced_by_canonical_protein_or_gene(self):
        query = candidate(input_id="TEST_P00001-2", entity_type="protein", id_namespace="uniprot")
        canonical = entity(canonical_id="TEST_P00001", entity_type="protein", id_namespace="uniprot")
        isoform = entity(canonical_id="TEST_P00001-2", entity_type="protein", id_namespace="uniprot")
        result = self.resolve(query, [entity(), canonical, isoform])
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["entity"]["canonical_id"], "TEST_P00001-2")
