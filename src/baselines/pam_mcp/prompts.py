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


def answer_prompt(batch_prompt: str, tool_name: str = "mcp__pam_memory__retrieve_memory") -> str:
    """Answer a numbered Q1..QN batch using ONLY the PAM Memory MCP tool.

    The tool is referenced by its EXACT Claude Code id (``mcp__<server>__<tool>``)
    and calling it is mandatory. Earlier runs showed the model inventing tool
    names (``$MCP_TOOL::...``) or reaching for ``Bash`` when the tool was named
    only as ``retrieve_memory``; both just error out, waste turns, and degrade
    answers. Pinning the exact name and forbidding other tools fixes that.
    """
    return (
        "Answer the numbered questions below about a long conversation you did "
        "not see. Every fact you need lives in PAM Memory.\n\n"
        f"The ONLY tool available to you is `{tool_name}`. You MUST call it — by "
        "that exact name, one or more times, with a natural-language query — to "
        "retrieve the relevant facts BEFORE writing any answer.\n\n"
        "Tool rules:\n"
        f"- Call the tool by its exact name `{tool_name}`. Never invent, "
        "abbreviate, rename, or re-namespace it, and never emit a placeholder "
        "like `$MCP_TOOL`.\n"
        f"- `{tool_name}` is the only tool you have. Do NOT use Bash, file tools, "
        "or any other tool — they are unavailable and will error.\n"
        "- Issue as many queries as needed to cover every question before you "
        "answer.\n\n"
        "Answering rules:\n"
        "- Base each answer ONLY on what the retrieved memory supports; do not "
        "guess beyond it.\n"
        "- Still give your single best answer for EVERY question — never leave a "
        "line blank, even when memory is thin.\n\n"
        f"{batch_prompt}"
    )
