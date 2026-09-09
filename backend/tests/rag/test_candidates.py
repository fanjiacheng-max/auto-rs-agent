"""Result-to-candidate contracts using the existing pipeline's column names."""

import csv
import tempfile
from pathlib import Path

from tests.rag.support import OfflineCase, require_api


class CandidateTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "differential.csv"
        self.context = {
            "species_taxid": 9606,
            "entity_type": "gene",
            "id_namespace": "symbol",
            "omics": "transcriptomics",
            "tissue": "test_tissue",
            "disease": "test_disease",
            "contrast": ["case", "control"],
            "analysis_type": "pseudobulk_edgeR",
        }
        self.columns = {
            "input_id": "gene", "effect_size": "logFC", "padj": "FDR",
            "cell_type": "celltype", "contrast": "contrast",
            "n_samples_group1": "n_samples_group1",
            "n_samples_group2": "n_samples_group2",
        }

    def write_rows(self, rows, delimiter=","):
        with self.path.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=delimiter)
            writer.writeheader()
            writer.writerows(rows)

    def row(self, **changes):
        result = {
            "gene": "TEST_GENE_A", "logFC": "1.5", "FDR": "0.01",
            "celltype": "test_cell_type", "contrast": "case vs control",
            "n_samples_group1": "4", "n_samples_group2": "4",
        }
        result.update(changes)
        return result

    def load(self, **options):
        fn = require_api(self, "load_candidates")
        return fn(self.path, context=self.context, columns=self.columns,
                  fdr_max=options.get("fdr_max", 0.05),
                  min_abs_log2fc=options.get("min_abs_log2fc", 1.0))

    def test_edger_preserves_analysis_context_and_original_row(self):
        self.write_rows([self.row()])
        batch = self.load()
        self.assertEqual(len(batch["candidates"]), 1)
        item = batch["candidates"][0]
        self.assertEqual(item["input_id"], "TEST_GENE_A")
        self.assertEqual((item["effect_size"], item["padj"]), (1.5, 0.01))
        self.assertEqual(item["direction"], "up")
        self.assertEqual(item["effect_measure"], "log2_fold_change")
        self.assertEqual(item["cell_type"], "test_cell_type")
        self.assertEqual((item["n_samples_group1"], item["n_samples_group2"]), (4, 4))
        for field, expected in self.context.items():
            self.assertEqual(item[field], expected, field)
        self.assertEqual(item["result_ref"], {"path": str(self.path), "row": 2})
        self.assertEqual(batch["excluded"], [])

    def test_significant_downregulation_is_also_a_candidate(self):
        self.write_rows([self.row(logFC="-2")])
        item = self.load()["candidates"][0]
        self.assertEqual((item["effect_size"], item["direction"]), (-2.0, "down"))

    def test_selection_uses_adjusted_p_and_effect_not_raw_p(self):
        self.write_rows([
            self.row(gene="TEST_RAW_ONLY", FDR="0.2", PValue="0.000001"),
            self.row(gene="TEST_TINY_EFFECT", logFC="0.1", PValue="0.000001"),
            self.row(gene="TEST_SELECTED", PValue="0.000001"),
        ])
        batch = self.load()
        self.assertEqual([r["input_id"] for r in batch["candidates"]], ["TEST_SELECTED"])
        excluded = {r["input_id"]: r["reason"] for r in batch["excluded"]}
        self.assertEqual(excluded, {"TEST_RAW_ONLY": "fdr", "TEST_TINY_EFFECT": "effect_size"})

    def test_threshold_boundaries_are_inclusive_and_configurable(self):
        self.write_rows([self.row(logFC="-0.5", FDR="0.1")])
        self.assertEqual(self.load()["candidates"], [])
        self.assertEqual(len(self.load(fdr_max=0.1, min_abs_log2fc=0.5)["candidates"]), 1)

    def test_seurat_exploratory_risk_label_survives_normalization(self):
        label = "exploratory_cell_level_pseudoreplication_risk"
        self.context["analysis_type"] = label
        self.columns = {
            "input_id": "gene", "effect_size": "avg_log2FC", "padj": "p_val_adj",
            "contrast": "contrast", "analysis_type": "analysis_type",
        }
        self.write_rows([{
            "gene": "TEST_GENE_A", "avg_log2FC": "2.0", "p_val_adj": "0.001",
            "contrast": "case vs control", "analysis_type": label,
        }])
        item = self.load()["candidates"][0]
        self.assertEqual(item["analysis_type"], label)
        self.assertIsNone(item.get("cell_type"))  # Existing exploratory output is pooled.
        self.assertIsNone(item.get("n_samples_group1"))

    def test_missing_species_fails_instead_of_guessing_from_gene_symbol(self):
        self.write_rows([self.row()])
        del self.context["species_taxid"]
        fn = require_api(self, "load_candidates")
        with self.assertRaisesRegex(ValueError, "species_taxid"):
            fn(self.path, context=self.context, columns=self.columns,
               fdr_max=0.05, min_abs_log2fc=1.0)

    def test_missing_contrast_cannot_be_inferred_from_effect_sign(self):
        self.write_rows([self.row()])
        del self.context["contrast"]
        fn = require_api(self, "load_candidates")
        with self.assertRaisesRegex(ValueError, "contrast"):
            fn(self.path, context=self.context, columns=self.columns,
               fdr_max=0.05, min_abs_log2fc=1.0)

    def test_invalid_selection_threshold_is_rejected(self):
        self.write_rows([self.row()])
        fn = require_api(self, "load_candidates")
        for fdr, effect in ((-0.1, 1.0), (1.1, 1.0), (0.05, -1.0), (float("nan"), 1.0)):
            with self.subTest(fdr=fdr, effect=effect):
                with self.assertRaises(ValueError):
                    fn(self.path, context=self.context, columns=self.columns,
                       fdr_max=fdr, min_abs_log2fc=effect)

    def test_missing_adjusted_p_column_does_not_fall_back_to_raw_p(self):
        row = self.row(PValue="0.001")
        del row["FDR"]
        self.write_rows([row])
        fn = require_api(self, "load_candidates")
        with self.assertRaisesRegex(ValueError, "FDR"):
            fn(self.path, context=self.context, columns=self.columns,
               fdr_max=0.05, min_abs_log2fc=1.0)

    def test_invalid_statistics_are_reported_and_not_interpreted(self):
        self.write_rows([
            self.row(gene="TEST_NAN", FDR="NaN"),
            self.row(gene="TEST_NEGATIVE_P", FDR="-0.1"),
            self.row(gene="TEST_P_OVER_ONE", FDR="1.1"),
            self.row(gene="TEST_INF", logFC="Inf"),
            self.row(gene="TEST_MISSING", FDR=""),
        ])
        batch = self.load()
        self.assertEqual(batch["candidates"], [])
        self.assertEqual(len(batch["excluded"]), 5)
        self.assertTrue(all(r["reason"] == "invalid_statistics" for r in batch["excluded"]))

    def test_same_gene_in_different_cell_types_is_not_collapsed(self):
        self.write_rows([self.row(celltype="cell_a"), self.row(celltype="cell_b", logFC="-2")])
        items = self.load()["candidates"]
        self.assertEqual([(r["cell_type"], r["direction"]) for r in items],
                         [("cell_a", "up"), ("cell_b", "down")])

    def test_conflicting_contrast_cannot_silently_reverse_effect_direction(self):
        self.write_rows([self.row(contrast="control vs case")])
        fn = require_api(self, "load_candidates")
        with self.assertRaisesRegex(ValueError, "contrast"):
            fn(self.path, context=self.context, columns=self.columns,
               fdr_max=0.05, min_abs_log2fc=1.0)

    def test_protein_isoform_identifier_survives_tsv_input(self):
        self.path = self.path.with_suffix(".tsv")
        self.context.update(entity_type="protein", id_namespace="uniprot",
                            omics="proteomics", analysis_type="protein_differential")
        self.write_rows([self.row(gene="TEST_P00001-2")], delimiter="\t")
        item = self.load()["candidates"][0]
        self.assertEqual(item["input_id"], "TEST_P00001-2")
        self.assertEqual((item["entity_type"], item["omics"]), ("protein", "proteomics"))

    def test_valid_table_with_no_selected_rows_is_an_empty_result(self):
        self.write_rows([self.row(FDR="0.8")])
        batch = self.load()
        self.assertEqual(batch["candidates"], [])
        self.assertEqual(len(batch["excluded"]), 1)
