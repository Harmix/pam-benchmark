"""Pydantic schemas for the LoCoMo dataset.

Mirrors the JSON shape in `data/locomo10.json` exactly. Loader code stays in
`loader.py`; this module is pure data definition.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

LoCoMoCategory = int  # 1=single-hop, 2=temporal, 3=open-domain, 4=multi-hop, 5=adversarial

CATEGORY_NAMES: dict[int, str] = {
    1: "single_hop",
    2: "temporal",
    3: "open_domain",
    4: "multi_hop",
    5: "adversarial",
}


class LoCoMoQA(BaseModel):
    """One question-answer record.

    Category 5 (adversarial) records may omit `answer` and instead carry
    `adversarial_answer`; the task assembles the question as a two-option
    multiple choice at prompt time.
    """

    question: str
    answer: str | None = None
    adversarial_answer: str | None = None
    evidence: list[str] = Field(default_factory=list)
    category: LoCoMoCategory

    @field_validator("answer", "adversarial_answer", mode="before")
    @classmethod
    def _coerce_to_str(cls, v: Any) -> Any:
        # Some LoCoMo records carry integer answers (years, counts). Normalize
        # to string so downstream metrics get a uniform type.
        if v is None or isinstance(v, str):
            return v
        return str(v)

    @property
    def category_name(self) -> str:
        return CATEGORY_NAMES.get(self.category, f"category_{self.category}")


class LoCoMoTurn(BaseModel):
    """One conversational turn within a session."""

    model_config = ConfigDict(extra="allow")

    speaker: str
    dia_id: str
    text: str
    blip_caption: str | None = None
    img_file: list[str] | None = None


class LoCoMoSample(BaseModel):
    """One LoCoMo conversation with its QA pairs.

    `conversation` stays as a raw dict because session keys are dynamic
    (`session_1`, `session_1_date_time`, `session_2`, ...). Helpers below
    surface the typed view used by prompt building.
    """

    model_config = ConfigDict(extra="ignore")

    sample_id: str
    qa: list[LoCoMoQA]
    conversation: dict[str, Any]

    def session_indices(self) -> list[int]:
        idxs: list[int] = []
        for key in self.conversation:
            if key.startswith("session_") and "date_time" not in key:
                try:
                    idxs.append(int(key.split("_")[-1]))
                except ValueError:
                    continue
        return sorted(idxs)

    def session(self, idx: int) -> list[LoCoMoTurn]:
        raw = self.conversation.get(f"session_{idx}", [])
        return [LoCoMoTurn(**t) for t in raw]

    def session_date_time(self, idx: int) -> str:
        return self.conversation.get(f"session_{idx}_date_time", "") or ""

    def speakers(self) -> tuple[str, str]:
        first = self.conversation.get("speaker_a")
        second = self.conversation.get("speaker_b")
        if first and second:
            return str(first), str(second)
        # Fallback: derive from session_1
        names = list({t.speaker for t in self.session(1)})
        if len(names) >= 2:
            return names[0], names[1]
        if len(names) == 1:
            return names[0], names[0]
        return "Speaker A", "Speaker B"
