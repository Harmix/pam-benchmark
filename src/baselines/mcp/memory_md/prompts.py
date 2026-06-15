"""Ingest + answer prompts for the markdown filesystem-memory baseline.

Design follows the well-known "filesystem / markdown-notes memory" baseline
(Letta, "Is a Filesystem All You Need?"; Basic Memory's Obsidian-markdown
format). Memory is a directory of Obsidian-style notes the agent writes during
ingestion and reads (search) during answering.

Fairness guardrails:
  - INGEST sees the conversation only — never the questions (query-agnostic).
  - ANSWER sees the questions + memory only — never the raw transcript.
"""

from __future__ import annotations

MEMORY_DIR = "memory"
INDEX_FILE = "memory/index.md"
NOTES_DIR = "memory/notes"


def ingest_prompt(transcript: str) -> str:
    """Build durable Obsidian-markdown memory from a conversation transcript."""
    return (
        "You are building a long-term MEMORY from a conversation, to be reused "
        "later to answer questions you cannot see now. Read the conversation "
        "below and write durable notes as Obsidian-style Markdown files.\n\n"
        "Rules:\n"
        f"- Write notes under `{NOTES_DIR}/` — one file per salient entity, "
        "person, place, event, or recurring topic (kebab-case filenames, e.g. "
        f"`{NOTES_DIR}/caroline.md`).\n"
        "- Each note starts with YAML front-matter (`---` title/type/tags `---`) "
        "followed by atomic, dated facts as `- ` bullets. Always include the "
        "DATE/SESSION a fact came from when known. Use `[[wikilinks]]` to connect "
        "related notes.\n"
        f"- Maintain `{INDEX_FILE}` as a table of contents linking every note "
        "with a one-line summary.\n"
        "- Capture specifics (names, dates, numbers, preferences, relationships, "
        "events and their order). Do not invent facts not in the conversation.\n"
        "- Write the files now using your file tools. Do NOT ask questions. When "
        'done, reply with exactly "MEMORY_WRITTEN".\n\n'
        "=== CONVERSATION ===\n"
        f"{transcript}\n"
        "=== END CONVERSATION ==="
    )


def answer_prompt(batch_prompt: str) -> str:
    """Answer a numbered Q1..QN batch using only the markdown memory (read-only)."""
    return (
        "You have a long-term MEMORY stored as Obsidian-style Markdown files "
        f"under `{MEMORY_DIR}/` (start at `{INDEX_FILE}`, then read/search the "
        f"notes in `{NOTES_DIR}/`). Use ONLY your memory files to answer — do not "
        "guess beyond what they support, but always give your single best answer "
        "for every question.\n\n"
        "Search and read the relevant notes, then answer the questions below.\n\n"
        f"{batch_prompt}"
    )
