"""Agent dispatcher contracts, plus regressions for its existing tools."""

import asyncio
import copy
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.agent.tools import TOOL_SCHEMAS, ToolContext
from tests.rag.support import OfflineAsyncCase, resolved_candidate


class ToolIntegrationTests(OfflineAsyncCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(self.tmp.name)
        self.context = ToolContext(self.workspace, AsyncMock(), executor=None,
                                   cancel_event=asyncio.Event())

    def test_rag_tool_is_advertised_with_required_candidate_input(self):
        matches = [t for t in TOOL_SCHEMAS if t["name"] == "retrieve_biomedical_evidence"]
        self.assertEqual(len(matches), 1, "RAG tool is not registered in TOOL_SCHEMAS")
        schema = matches[0]["input_schema"]
        self.assertEqual(schema["type"], "object")
        self.assertIn("candidate", schema["required"])
        self.assertEqual(schema["properties"]["candidate"]["type"], "object")

    async def test_dispatch_returns_structured_evidence_without_losing_context(self):
        handler = getattr(ToolContext, "retrieve_biomedical_evidence", None)
        self.assertTrue(callable(handler), "RAG tool handler is not implemented")
        query = resolved_candidate()
        response = {
            "status": "partial", "candidate": query, "evidence": [],
            "source_status": {"fixture_primary": {"status": "error", "error": "timeout"}},
            "independent_publications": 0, "rejected": [],
        }
        # Only the handler boundary is replaced: ToolContext.execute is real.
        with patch.object(ToolContext, "retrieve_biomedical_evidence",
                          new=AsyncMock(return_value=copy.deepcopy(response))) as retrieval:
            actual = await self.context.execute("retrieve_biomedical_evidence", {"candidate": query})
        self.assertEqual(actual, response)
        retrieval.assert_awaited_once_with(candidate=query)

    async def test_existing_read_file_tool_still_reads_project_artifacts(self):
        path = self.workspace / "results" / "existing.txt"
        path.parent.mkdir()
        path.write_text("existing analysis", encoding="utf-8")
        result = await self.context.execute("read_file", {"path": str(path)})
        self.assertEqual(result, "existing analysis")

    async def test_unknown_tool_is_still_reported_as_an_error(self):
        result = await self.context.execute("does_not_exist", {})
        self.assertEqual(result, "Error: unknown tool 'does_not_exist'")
