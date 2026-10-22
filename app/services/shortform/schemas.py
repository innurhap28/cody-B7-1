"""Shared A/B/C DTOs. Unknown fields and implicit type coercion are rejected."""
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=6000)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @model_validator(mode="after")
    def valid_unicode(self) -> Self:
        def check(value):
            if isinstance(value, str):
                try:
                    value.encode("utf-8")
                except UnicodeEncodeError:
                    raise ValueError("사용할 수 없는 문자가 포함되어 있습니다.") from None
            elif isinstance(value, list):
                for item in value:
                    check(item)
            elif isinstance(value, dict):
                for item in value.values():
                    check(item)
        check(self.model_dump())
        return self


class Audience(DTO):
    segment: Short | None = None
    age_range: Short | None = None
    prior_knowledge: Short | None = None


class Brief(DTO):
    schema_version: Literal["brief.v1"] = "brief.v1"
    topic: Short | None = None
    goal: Short | None = None
    audience: Audience = Field(default_factory=Audience)
    duration_sec: int | None = Field(default=None, ge=10, le=180)
    presentation_mode: Literal["on_camera", "hands_only", "voiceover", "mixed", "no_people"] | None = None
    characters: list[Short] = Field(default_factory=list, max_length=8)
    direction_style: Short | None = None
    tone: Short | None = None
    core_message: Short | None = None
    constraints: list[Short] = Field(default_factory=list, max_length=12)
    proposed_defaults: list[Short] = Field(default_factory=list, max_length=8)
    confirmed: bool = False

    def missing_fields(self) -> list[str]:
        required = ["topic", "goal", "audience.segment", "audience.age_range", "duration_sec",
                    "presentation_mode", "direction_style", "core_message"]
        data = self.model_dump()
        missing = []
        for path in required:
            value = data
            for part in path.split("."):
                value = value[part]
            if value is None:
                missing.append(path)
        if self.presentation_mode in {"on_camera", "mixed"} and not self.characters:
            missing.append("characters")
        return missing

    def patched(self, patch: dict) -> Self:
        # Model/clients cannot confirm a brief or silently change the schema.
        if set(patch) - set(type(self).model_fields) or {"confirmed", "schema_version"} & set(patch):
            raise ValueError("Unsupported brief fields")
        data = self.model_dump()
        incoming = dict(patch)
        if "audience" in incoming:
            if not isinstance(incoming["audience"], dict):
                raise ValueError("audience must be an object")
            incoming["audience"] = {**data["audience"], **incoming["audience"]}
        data.update(incoming)
        data["confirmed"] = False
        return type(self).model_validate(data)


class ChatRequest(DTO):
    conversation_id: int = Field(gt=0)
    expected_version: int = Field(ge=0)
    action: Literal["message", "generate", "revise"] = "message"
    message: Text
    base_script_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def revision_needs_script(self) -> Self:
        if self.action == "revise" and self.base_script_id is None:
            raise ValueError("수정할 대본을 선택해 주세요.")
        return self


class ConversationCreate(DTO):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] = "새 릴스 기획"


class FollowUp(DTO):
    field: str
    question: Short
    suggestions: list[Short] = Field(default_factory=list, max_length=3)


class Extraction(DTO):
    intent: Literal["brief", "explanation"] = "brief"
    brief_patch: dict = Field(default_factory=dict)
    follow_up_questions: list[FollowUp] = Field(default_factory=list, max_length=2)
    answer: Text | None = None
    card_ids: list[str] = Field(default_factory=list, max_length=3)


class Structure(DTO):
    name: Short
    reason: Text


class Scene(DTO):
    scene_no: int = Field(gt=0)
    start_sec: int = Field(ge=0)
    end_sec: int = Field(gt=0)
    purpose: Short
    visual: Text
    dialogue: Annotated[str, StringConstraints(max_length=3000)] = ""
    caption: Annotated[str, StringConstraints(max_length=1000)] = ""
    direction: Text


class Rationale(DTO):
    scene_nos: list[int] = Field(min_length=1, max_length=20)
    card_ids: list[str] = Field(min_length=1, max_length=3)
    explanation: Text


class ScriptDraft(DTO):
    title: Short
    duration_sec: int = Field(ge=10, le=180)
    structure: Structure
    scenes: list[Scene] = Field(min_length=1, max_length=20)
    rationale: list[Rationale] = Field(min_length=1, max_length=10)
    change_summary: Short | None = None

    def check_grounding(self, brief: Brief, allowed_ids: set[str]) -> None:
        if self.duration_sec != brief.duration_sec:
            raise ValueError("Duration does not match the brief")
        previous_end = 0
        for index, scene in enumerate(self.scenes, start=1):
            if scene.scene_no != index or scene.start_sec != previous_end or scene.end_sec <= scene.start_sec:
                raise ValueError("Scenes must be consecutive and non-overlapping")
            previous_end = scene.end_sec
        if previous_end != self.duration_sec:
            raise ValueError("Scene durations must cover the requested duration")
        scene_ids = {s.scene_no for s in self.scenes}
        for reason in self.rationale:
            if not set(reason.scene_nos) <= scene_ids or not set(reason.card_ids) <= allowed_ids:
                raise ValueError("Unknown scene or source reference")
