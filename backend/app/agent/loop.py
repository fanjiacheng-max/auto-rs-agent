"""
Agent loop: select Skill → load SKILL.md → LLM tool_use loop → complete.
"""
import asyncio
import json
import os
from pathlib import Path

import aiosqlite

from app.config import DB_PATH, SKILLS_DIR
from app.agent.executor import Executor
from app.agent.project_state import ProjectState
from app.agent.resolver import DependencyResolver
from app.agent.providers.anthropic import AnthropicProvider
from app.agent.providers.base import ContentBlock
from app.agent.skill import Skill, load_skills
from app.agent.tools import TOOL_SCHEMAS, ToolContext
import app.db as db

_resolver = DependencyResolver()

# ── Executor selection ────────────────────────────────────────────────────
# Set AGENT_EXECUTOR=ssh to use remote SSH+rjob executor.
# Default is local subprocess executor.
def _make_executor():
    if os.environ.get("AGENT_EXECUTOR", "local").lower() == "ssh":
        from app.agent.ssh_executor import SSHRjobExecutor
        return SSHRjobExecutor()
    return Executor()

_executor = _make_executor()
_provider = AnthropicProvider()

# Cancel events keyed by run_id
_cancel_events: dict[str, asyncio.Event] = {}


def cancel_run(run_id: str) -> None:
    if run_id in _cancel_events:
        _cancel_events[run_id].set()


# ── System prompt ─────────────────────────────────────────

def _build_system(project: dict, skill: Skill, skill_md: str,
                   plan_summary: str = "") -> str:
    plan_section = f"\n## Execution Plan\n{plan_summary}\n" if plan_summary else ""
    return f"""You are a biomedical research analysis agent. You help researchers run scientific analyses by following established Skill workflows.

## Current Project
Name: {project['name']}
Workspace: {project['workspace_path']}

## Active Skill: {skill.name}
You are using the **{skill.name}** skill. The full SKILL.md is provided below.
Follow its instructions step by step. Execute commands exactly as specified, adapting file paths to the project workspace.
{plan_section}
## Rules
- Always use run_command to execute scripts (Python, Rscript, bash).
- Save all outputs inside the project workspace.
- If a command fails, show the error. Do not pretend it succeeded.
- Use ask_user only when the SKILL requires human confirmation or when the analysis cannot safely proceed without user input.
- Keep the user informed with brief status messages between steps.
- Modules listed as "Cached (skip)" already have results — do not re-run them.
- Only run modules listed in "Will run".

## SKILL.md
{skill_md}
"""


def _build_skill_list(skills: list[Skill]) -> str:
    return "\n".join(f"- **{s.name}**: {s.description}" for s in skills)


def _select_skill(user_message: str, skills: list[Skill]) -> tuple[Skill | None, str]:
    """
    Returns (skill, status) where status is 'clear' or 'ambiguous'.
    Explicit name match wins. With one skill, always clear.
    """
    msg_lower = user_message.lower()
    # Explicit name match
    for s in skills:
        if s.name.lower() in msg_lower:
            return s, "clear"
    # Single skill available
    if len(skills) == 1:
        return skills[0], "clear"
    # Multiple skills — delegate to LLM later; for now return ambiguous
    return None, "ambiguous"


# ── Conversation context ──────────────────────────────────

async def _build_messages(conn, project_id: str, user_message: str) -> list[dict]:
    history = await db.list_messages(conn, project_id, limit=10)
    messages = []
    for m in history:
        messages.append({"role": m["role"], "content": m["content"]})
    # Ensure last message is the current user turn
    if not messages or messages[-1]["content"] != user_message:
        messages.append({"role": "user", "content": user_message})
    return messages


# ── Main loop ─────────────────────────────────────────────

async def run_agent(run_id: str, project: dict, user_message: str) -> None:
    cancel_event = asyncio.Event()
    _cancel_events[run_id] = cancel_event

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        async def emit(event_type: str, payload: dict) -> None:
            await db.append_event(conn, run_id, event_type, payload)
            if event_type == "artifact_created":
                await db.upsert_artifact(
                    conn,
                    project_id=project["id"],
                    run_id=run_id,
                    rel_path=payload["path"],
                    artifact_type=payload["artifact_type"],
                    size=payload.get("size", 0),
                )

        try:
            await db.update_run_status(conn, run_id, "running")
            await emit("run_started", {"run_id": run_id})

            workspace = Path(project["workspace_path"])
            ps = ProjectState.open(workspace)

            # 1. Load skills
            skills = load_skills()
            if not skills:
                await emit("run_failed", {"error": "No skills found in skills/ directory."})
                await db.update_run_status(conn, run_id, "failed")
                return

            # 2. Select skill
            skill, status = _select_skill(user_message, skills)
            if status == "ambiguous" or skill is None:
                # Ask user to choose
                names = [s.name for s in skills]
                await db.set_run_pending_question(
                    conn, run_id,
                    question="Multiple skills are available. Which one should I use?",
                    choices=names,
                )
                # Store pending context so resume can continue
                # (Full resume is post-MVP; for now we end the loop here)
                return

            await emit("skill_selected", {"skill": skill.name, "description": skill.description})
            await db.update_run_status(conn, run_id, "running", skill_name=skill.name)

            # 3. Load SKILL.md
            skill_md = skill.read_skill_md()

            # 4. Resolve dependencies
            # Map skill name to target module (skill name = module name by convention)
            target_module = (
                skill.name
                .replace("geo-scrna-", "")
                .replace("scrna-", "")
                .replace("-", "_")   # pathway-scores → pathway_scores
            )
            # Fallback: if module not in registry, skip resolver
            plan = None
            plan_summary = ""
            try:
                plan = await _resolver.resolve(target_module, ps)
                plan_summary = plan.summary()
                await emit("plan_resolved", {
                    "target": plan.target_module,
                    "to_run": plan.modules_to_run,
                    "cached": plan.already_done,
                    "blocking_gates": plan.blocking_gates,
                    "missing_inputs": plan.missing_inputs,
                })

                # Handle blocking gates one at a time (first unconfirmed gate)
                if plan.blocking_gates:
                    gate_name = plan.blocking_gates[0]
                    question, choices = _resolver.gate_question(gate_name)
                    # Substitute placeholders with actual values from status.json
                    state = await ps.read()
                    for k, v in state.items():
                        if isinstance(v, str):
                            question = question.replace(f"{{{k}}}", v)
                    await db.save_pending_state(conn, run_id, [], f"gate:{gate_name}")
                    await db.set_run_pending_question(conn, run_id, question, choices)
                    return

                # Handle missing required inputs
                if plan.missing_inputs:
                    inp = plan.missing_inputs[0]
                    await db.save_pending_state(conn, run_id, [], f"input:{inp}")
                    await db.set_run_pending_question(
                        conn, run_id,
                        question=f"请提供 {inp}（分析必需，不能使用默认值）：",
                        choices=None,
                    )
                    return

            except ValueError:
                # Module not in registry — proceed without plan (LLM drives execution)
                pass

            # 5. Build initial LLM context
            messages = await _build_messages(conn, project["id"], user_message)
            system = _build_system(project, skill, skill_md, plan_summary)

            # 5. Tool context
            for d in ["inputs", "results", "figures", "tables", "objects", "reports", "logs"]:
                (workspace / d).mkdir(exist_ok=True)

            tool_ctx = ToolContext(
                workspace=workspace,
                emit=emit,
                executor=_executor,
                cancel_event=cancel_event,
            )

            # 6. LLM tool-use loop
            await _llm_loop(conn, run_id, project, skill, system, messages, tool_ctx, emit, ps)

        except asyncio.CancelledError:
            await db.update_run_status(conn, run_id, "interrupted")
            await emit("run_interrupted", {})
        except Exception as exc:
            await db.update_run_status(conn, run_id, "failed")
            await emit("run_failed", {"error": str(exc)})
            raise
        finally:
            _cancel_events.pop(run_id, None)


async def _llm_loop(conn, run_id, project, skill, system, messages, tool_ctx, emit, ps: ProjectState):
    max_iterations = 50

    for _ in range(max_iterations):
        response = await _provider.chat(system=system, messages=messages, tools=TOOL_SCHEMAS)

        text_blocks = [b for b in response.content if b.type == "text"]
        tool_blocks = [b for b in response.content if b.type == "tool_use"]

        if text_blocks:
            text = "\n".join(b.text or "" for b in text_blocks)
            await emit("agent_message", {"text": text})

        if response.stop_reason == "end_turn" or not tool_blocks:
            final_text = "\n".join(b.text or "" for b in text_blocks)
            if final_text:
                await db.create_message(conn, project["id"], "assistant", final_text, run_id)
            await db.update_run_status(conn, run_id, "completed")
            await emit("run_completed", {"skill": skill.name})
            return

        messages.append({
            "role": "assistant",
            "content": AnthropicProvider.serialize_message_content(response.content),
        })

        tool_results = []
        for tb in tool_blocks:
            if tb.tool_name == "ask_user":
                question = (tb.tool_input or {}).get("question", "")
                choices = (tb.tool_input or {}).get("choices")
                await db.save_pending_state(conn, run_id, messages, tb.tool_use_id or "")
                await db.set_run_pending_question(conn, run_id, question, choices)
                return

            await emit("tool_call", {
                "tool": tb.tool_name,
                "args": tb.tool_input,
                "tool_use_id": tb.tool_use_id,
            })
            result = await tool_ctx.execute(tb.tool_name or "", tb.tool_input or {})

            await emit("tool_result", {
                "tool": tb.tool_name,
                "tool_use_id": tb.tool_use_id,
                "result": result if isinstance(result, str) else json.dumps(result)[:2000],
            })

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tb.tool_use_id,
                "content": result if isinstance(result, str) else json.dumps(result),
            })

        messages.append({"role": "user", "content": tool_results})

    await db.update_run_status(conn, run_id, "failed")
    await emit("run_failed", {"error": "Reached maximum iteration limit."})


async def resume_agent(run_id: str, project: dict, user_reply: str) -> None:
    """
    Resume a paused run after the user replies.

    pending_id encoding:
      "gate:<name>"   → confirm gate in status.json, re-resolve from top
      "input:<name>"  → record input in status.json, re-resolve from top
      "<tool_use_id>" → plain ask_user reply, inject as tool_result, continue loop
    """
    cancel_event = asyncio.Event()
    _cancel_events[run_id] = cancel_event

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        async def emit(event_type: str, payload: dict) -> None:
            await db.append_event(conn, run_id, event_type, payload)
            if event_type == "artifact_created":
                await db.upsert_artifact(
                    conn,
                    project_id=project["id"],
                    run_id=run_id,
                    rel_path=payload["path"],
                    artifact_type=payload["artifact_type"],
                    size=payload.get("size", 0),
                )

        try:
            saved = await db.load_pending_state(conn, run_id)
            if not saved:
                await emit("run_failed", {"error": "No pending state found for resume."})
                await db.update_run_status(conn, run_id, "failed")
                return

            messages, pending_id = saved
            await db.delete_pending_state(conn, run_id)

            workspace = Path(project["workspace_path"])
            ps = ProjectState.open(workspace)

            # Gate or input confirmation → persist and re-resolve from scratch
            if pending_id.startswith("gate:"):
                gate_name = pending_id[5:]
                await ps.confirm_gate(gate_name, user_reply)
                await emit("agent_message", {
                    "text": f"Gate '{gate_name}' 已确认：{user_reply}。重新检查依赖..."
                })
                _cancel_events.pop(run_id, None)
                await run_agent(run_id, project, user_reply)
                return

            if pending_id.startswith("input:"):
                input_name = pending_id[6:]
                await ps.set_input(input_name, user_reply)
                await emit("agent_message", {
                    "text": f"Input '{input_name}' 已记录：{user_reply}。重新检查依赖..."
                })
                _cancel_events.pop(run_id, None)
                await run_agent(run_id, project, user_reply)
                return

            # Plain ask_user → inject reply as tool_result, continue loop
            messages.append({
                "role": "user",
                "content": [{"type": "tool_result",
                              "tool_use_id": pending_id,
                              "content": user_reply}],
            })

            await db.update_run_status(conn, run_id, "running")
            await emit("agent_message", {"text": f"继续分析（用户回复：{user_reply}）"})

            run = await db.get_run(conn, run_id)
            skill_name = run["skill_name"] if run else None
            skills = load_skills()
            skill = next((s for s in skills if s.name == skill_name), None)
            if not skill:
                await emit("run_failed", {"error": f"Skill '{skill_name}' not found."})
                await db.update_run_status(conn, run_id, "failed")
                return

            skill_md = skill.read_skill_md()
            system = _build_system(project, skill, skill_md)
            tool_ctx = ToolContext(
                workspace=workspace, emit=emit,
                executor=_executor, cancel_event=cancel_event,
            )
            await _llm_loop(conn, run_id, project, skill, system, messages, tool_ctx, emit, ps)

        except asyncio.CancelledError:
            await db.update_run_status(conn, run_id, "interrupted")
            await emit("run_interrupted", {})
        except Exception as exc:
            await db.update_run_status(conn, run_id, "failed")
            await emit("run_failed", {"error": str(exc)})
            raise
        finally:
            _cancel_events.pop(run_id, None)

