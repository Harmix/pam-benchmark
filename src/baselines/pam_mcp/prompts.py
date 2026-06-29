"""System + answer prompts for the `pam_mcp` baseline.

The agent (Claude Code) answers questions by retrieving from Pam's server-side
memory through the PAM Memory MCP tool (`retrieve_memory`). Unlike the markdown
backend there is NO ingest prompt — memory is built server-side via the Pam API
before answering.

`SYSTEM_PROMPT` is copied verbatim from pam-agent-api's
`MEMORY_MCP_SYSTEM_PROMPT_SNIPPET` (the snippet the Memory MCP quickstart docs
require callers to add). Keep it in sync if the upstream snippet changes.
"""

from __future__ import annotations

# Verbatim from app/services/mcp/memory_tools.py::MEMORY_MCP_SYSTEM_PROMPT_SNIPPET
SYSTEM_PROMPT = (
    "You have access to PAM Memory through the retrieve_memory MCP tool. Use it "
    "when a request may depend on company-specific context: people, projects, "
    "decisions, processes, priorities, history, customers, documents, meetings, "
    "or internal terminology. Prefer retrieving memory before making assumptions. "
    "If retrieved context is partial or uncertain, say so and ask a focused "
    "follow-up."
)


def answer_prompt(batch_prompt: str) -> str:
    """Answer a numbered Q1..QN batch using ONLY the PAM Memory MCP tool."""
    return (
        "Answer the questions below about a long conversation. The facts live in "
        "PAM Memory — call the `retrieve_memory` tool (one or more times) to fetch "
        "the relevant context before answering. Use ONLY what the retrieved memory "
        "supports; do not guess beyond it, but always give your single best answer "
        "for every question.\n\n"
        f"{batch_prompt}"
    )
