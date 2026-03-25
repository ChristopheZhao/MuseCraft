"""Story planning data structures for project-based video generation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Tuple


class EpisodeEditorialStatus(str, Enum):
    """Editorial/script lifecycle states for an episode within a project."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"


@dataclass
class EpisodePlan:
    """High-level blueprint for a single episode (≈1 minute clip)."""

    episode_id: str
    sequence_index: int
    title: str
    target_duration_seconds: int
    summary: str = ""
    narrative_purpose: str = ""
    continuity_notes: Dict[str, Any] = field(default_factory=dict)
    required_assets: Dict[str, Any] = field(default_factory=dict)
    script_draft: str = ""
    status: EpisodeEditorialStatus = EpisodeEditorialStatus.DRAFT

    @classmethod
    def create(
        cls,
        sequence_index: int,
        title: str,
        target_duration_seconds: int,
        summary: str = "",
        narrative_purpose: str = "",
    ) -> "EpisodePlan":
        return cls(
            episode_id=str(uuid.uuid4()),
            sequence_index=sequence_index,
            title=title,
            target_duration_seconds=target_duration_seconds,
            summary=summary,
            narrative_purpose=narrative_purpose,
        )


@dataclass
class CharacterProfile:
    """Canonical representation of a character across the project."""

    canonical_id: str
    display_name: str
    description: str = ""
    narrative_role: str = ""
    aliases: List[str] = field(default_factory=list)
    personality_traits: List[str] = field(default_factory=list)
    visual_traits: Dict[str, Any] = field(default_factory=dict)
    style_preferences: Dict[str, Any] = field(default_factory=dict)
    voice_profile: Dict[str, Any] = field(default_factory=dict)
    reference_assets: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_id": self.canonical_id,
            "display_name": self.display_name,
            "description": self.description,
            "narrative_role": self.narrative_role,
            "aliases": list(dict.fromkeys(self.aliases)),
            "personality_traits": list(dict.fromkeys(self.personality_traits)),
            "visual_traits": self.visual_traits,
            "style_preferences": self.style_preferences,
            "voice_profile": self.voice_profile,
            "reference_assets": self.reference_assets,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterProfile":
        canonical_id = data.get("canonical_id") or data.get("id") or data.get("slug")
        display_name = data.get("display_name") or data.get("name") or canonical_id or "Unnamed"

        canonical_id = _canonicalize_character_id(canonical_id or display_name)

        return cls(
            canonical_id=canonical_id,
            display_name=str(display_name).strip() or canonical_id,
            description=str(data.get("description") or ""),
            narrative_role=str(data.get("narrative_role") or data.get("role") or ""),
            aliases=_dedupe_list(data.get("aliases")),
            personality_traits=_dedupe_list(data.get("personality_traits")),
            visual_traits=data.get("visual_traits") or data.get("appearance") or {},
            style_preferences=data.get("style_preferences") or data.get("style") or {},
            voice_profile=data.get("voice_profile") or {},
            reference_assets=data.get("reference_assets") or data.get("assets") or {},
            metadata=data.get("metadata") or {},
        )

    def merge(self, other: "CharacterProfile") -> "CharacterProfile":
        if other.canonical_id != self.canonical_id:
            raise ValueError("Cannot merge profiles with different canonical_ids")

        return CharacterProfile(
            canonical_id=self.canonical_id,
            display_name=self.display_name or other.display_name,
            description=self.description or other.description,
            narrative_role=self.narrative_role or other.narrative_role,
            aliases=_merge_lists(self.aliases, other.aliases),
            personality_traits=_merge_lists(self.personality_traits, other.personality_traits),
            visual_traits=_merge_dicts(other.visual_traits, self.visual_traits),
            style_preferences=_merge_dicts(other.style_preferences, self.style_preferences),
            voice_profile=_merge_dicts(other.voice_profile, self.voice_profile),
            reference_assets=_merge_dicts(other.reference_assets, self.reference_assets),
            metadata=_merge_dicts(other.metadata, self.metadata),
        )


def _dedupe_list(source: Any) -> List[str]:
    if not source:
        return []
    if isinstance(source, str):
        items = re.split(r"[,;\n]+", source)
    elif isinstance(source, Iterable):
        items = list(source)
    else:
        items = [str(source)]

    result: List[str] = []
    seen = set()
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _merge_lists(primary: List[str], secondary: List[str]) -> List[str]:
    merged = list(primary or [])
    for item in secondary or []:
        if item not in merged:
            merged.append(item)
    return merged


def _merge_dicts(base: Any, override: Any) -> Dict[str, Any]:
    combined: Dict[str, Any] = {}

    if isinstance(base, dict):
        combined.update(base)
    elif base not in (None, ""):
        combined["value"] = base

    if isinstance(override, dict):
        combined.update({k: v for k, v in override.items() if v is not None})
    elif override not in (None, ""):
        combined["value"] = override

    return combined


def _canonicalize_character_id(raw_id: Optional[str]) -> str:
    value = (raw_id or "").strip()
    if not value:
        return f"char-{uuid.uuid4().hex[:8]}"

    # If user provided a sane slug, keep it as-is to avoid surprising renames
    if re.fullmatch(r"[A-Za-z0-9_-]+", value):
        return value

    ascii_candidate = unicodedata.normalize("NFKD", value)
    ascii_candidate = ascii_candidate.encode("ascii", "ignore").decode("ascii")
    ascii_candidate = ascii_candidate.lower()
    # Keep underscores and dashes; collapse other runs to '-'
    ascii_candidate = re.sub(r"[^a-z0-9_-]+", "-", ascii_candidate).strip("-")

    if not ascii_candidate:
        digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
        return f"char-{digest}"

    return ascii_candidate[:64]


def _to_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _ensure_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.replace("、", ",")
        parts = re.split(r"[,;\n]+", cleaned)
        return [part.strip() for part in parts if part.strip()]
    if isinstance(value, Iterable) and not isinstance(value, (dict, bytes)):
        result: List[str] = []
        for item in value:
            text = _to_str(item)
            if text:
                result.append(text)
        return list(dict.fromkeys(result))
    text = _to_str(value)
    return [text] if text else []


def _ensure_structured_dict(value: Any, fallback_key: str) -> Dict[str, Any]:
    if isinstance(value, dict):
        return {str(k): v for k, v in value.items()}
    if isinstance(value, list):
        items = _ensure_str_list(value)
        return {fallback_key: items} if items else {}
    text = _to_str(value)
    return {fallback_key: text} if text else {}


def _merge_sanitized_character(
    primary: Dict[str, Any],
    incoming: Dict[str, Any],
) -> Dict[str, Any]:
    merged = dict(primary)

    for key in [
        "display_name",
        "type",
        "species_or_breed",
        "archetype_or_identity",
        "role",
        "description",
        "backstory",
        "motivation",
    ]:
        if not merged.get(key):
            merged[key] = incoming.get(key, merged.get(key))

    for key in [
        "aliases",
        "abstract_traits",
        "personality_traits",
        "visual_identity",
        "signature_outfit_or_props",
    ]:
        merged[key] = _merge_lists(merged.get(key, []), incoming.get(key, []))

    merged["visual_traits"] = _merge_dicts(
        incoming.get("visual_traits", {}),
        merged.get("visual_traits", {}),
    )
    merged["style_preferences"] = _merge_dicts(
        incoming.get("style_preferences", {}),
        merged.get("style_preferences", {}),
    )
    merged["voice_profile"] = _merge_dicts(
        incoming.get("voice_profile", {}),
        merged.get("voice_profile", {}),
    )
    merged["reference_assets"] = _merge_dicts(
        incoming.get("reference_assets", {}),
        merged.get("reference_assets", {}),
    )
    merged["metadata"] = _merge_dicts(
        incoming.get("metadata", {}),
        merged.get("metadata", {}),
    )

    return merged


def _normalize_character_entry(
    raw_entry: Any,
    index: int,
) -> Tuple[Dict[str, Any], CharacterProfile]:
    if isinstance(raw_entry, CharacterProfile):
        profile = raw_entry
        sanitized = profile.to_dict()
        sanitized.update(
            {
                "canonical_name": profile.canonical_id,
                "canonical_id": profile.canonical_id,
                "display_name": profile.display_name,
                "role": profile.narrative_role,
            }
        )
        return sanitized, profile

    if isinstance(raw_entry, dict):
        entry = dict(raw_entry)
    else:
        entry = {"display_name": _to_str(raw_entry)}

    canonical_candidate = _to_str(
        entry.get("canonical_name")
        or entry.get("canonical_id")
        or entry.get("canonical")
        or entry.get("id")
        or entry.get("slug")
        or entry.get("name")
    )
    display_name = _to_str(entry.get("display_name") or entry.get("name") or canonical_candidate)

    canonical_id = _canonicalize_character_id(canonical_candidate or display_name)
    if not display_name:
        display_name = canonical_id

    aliases = _ensure_str_list(entry.get("aliases") or entry.get("aka"))
    if canonical_candidate and canonical_candidate.casefold() != canonical_id.casefold():
        aliases.append(canonical_candidate)
    if display_name and display_name.casefold() != canonical_id.casefold():
        aliases.append(display_name)
    aliases = list(dict.fromkeys([alias for alias in aliases if alias]))

    type_hint = _to_str(entry.get("type") or entry.get("entity_type") or entry.get("category"))
    species = _to_str(entry.get("species_or_breed") or entry.get("species") or entry.get("breed"))
    archetype = _to_str(
        entry.get("archetype_or_identity")
        or entry.get("archetype")
        or entry.get("identity")
        or entry.get("persona")
    )
    role = _to_str(entry.get("role") or entry.get("narrative_role"))

    abstract_traits = _ensure_str_list(entry.get("abstract_traits"))
    personality_traits = _merge_lists(
        abstract_traits,
        _ensure_str_list(entry.get("personality_traits")),
    )
    visual_identity = _ensure_str_list(entry.get("visual_identity"))
    signature_props = _ensure_str_list(entry.get("signature_outfit_or_props") or entry.get("signature_props"))

    backstory = _to_str(entry.get("backstory"))
    motivation = _to_str(entry.get("motivation"))

    description = _to_str(entry.get("description"))
    if not description and personality_traits:
        description = "；".join(personality_traits[:5])

    visual_traits = _ensure_structured_dict(entry.get("visual_traits"), "notes")
    if visual_identity:
        visual_traits = _merge_dicts({"identity_tags": visual_identity}, visual_traits)
    if signature_props:
        visual_traits = _merge_dicts({"signature_props": signature_props}, visual_traits)
    if type_hint:
        visual_traits.setdefault("entity_type", type_hint)
    if species:
        visual_traits.setdefault("species_or_breed", species)

    style_preferences = _ensure_structured_dict(entry.get("style_preferences"), "keywords")
    voice_profile = _ensure_structured_dict(entry.get("voice_profile"), "notes")
    reference_assets = _ensure_structured_dict(entry.get("reference_assets"), "items")

    metadata = _ensure_structured_dict(entry.get("metadata"), "details")
    if archetype:
        metadata.setdefault("archetype_or_identity", archetype)
    if type_hint:
        metadata.setdefault("type", type_hint)
    if species:
        metadata.setdefault("species_or_breed", species)
    if backstory:
        metadata.setdefault("backstory", backstory)
    if motivation:
        metadata.setdefault("motivation", motivation)
    metadata.setdefault("source", entry.get("source") or "concept_plan")
    metadata.setdefault("source_index", index)

    sanitized: Dict[str, Any] = {
        "canonical_id": canonical_id,
        "canonical_name": canonical_id,
        "display_name": display_name,
        "aliases": aliases,
        "type": type_hint,
        "species_or_breed": species,
        "archetype_or_identity": archetype,
        "abstract_traits": abstract_traits,
        "personality_traits": personality_traits,
        "visual_identity": visual_identity,
        "signature_outfit_or_props": signature_props,
        "role": role,
        "description": description,
        "backstory": backstory,
        "motivation": motivation,
        "visual_traits": visual_traits,
        "style_preferences": style_preferences,
        "voice_profile": voice_profile,
        "reference_assets": reference_assets,
        "metadata": metadata,
    }

    profile_payload = {
        "canonical_id": canonical_id,
        "display_name": display_name,
        "description": description,
        "narrative_role": role,
        "aliases": aliases,
        "personality_traits": personality_traits,
        "visual_traits": visual_traits,
        "style_preferences": style_preferences,
        "voice_profile": voice_profile,
        "reference_assets": reference_assets,
        "metadata": metadata,
    }
    profile = CharacterProfile.from_dict(profile_payload)

    return sanitized, profile


def normalize_character_elements(
    raw: Any,
) -> Tuple[List[Dict[str, Any]], Dict[str, CharacterProfile]]:
    if not raw:
        return [], {}

    entries: List[Any]
    if isinstance(raw, dict):
        entries = []
        for key, value in raw.items():
            if isinstance(value, dict):
                candidate = dict(value)
            else:
                candidate = {"display_name": value}
            if "canonical_name" not in candidate and key:
                candidate["canonical_name"] = key
            entries.append(candidate)
    elif isinstance(raw, list):
        entries = list(raw)
    else:
        entries = [raw]

    sanitized_order: Dict[str, Dict[str, Any]] = {}
    profiles: Dict[str, CharacterProfile] = {}

    for index, entry in enumerate(entries):
        sanitized, profile = _normalize_character_entry(entry, index)
        key = profile.canonical_id

        existing = sanitized_order.get(key)
        if existing and existing.get("display_name", "").strip().casefold() != sanitized.get(
            "display_name", ""
        ).strip().casefold():
            suffix = 1
            candidate = f"{key}-{suffix}"
            while candidate in sanitized_order:
                suffix += 1
                candidate = f"{key}-{suffix}"

            metadata = _merge_dicts({"original_canonical_id": key}, sanitized.get("metadata", {}))
            sanitized = dict(sanitized)
            sanitized["canonical_id"] = candidate
            sanitized["canonical_name"] = candidate
            sanitized["aliases"] = _merge_lists(sanitized.get("aliases", []), [key])
            sanitized["metadata"] = metadata

            profile_payload = profile.to_dict()
            profile_payload["canonical_id"] = candidate
            profile_payload.setdefault("metadata", {}).update(metadata)
            profile = CharacterProfile.from_dict(profile_payload)
            key = candidate
            existing = None

        if existing:
            sanitized_order[key] = _merge_sanitized_character(existing, sanitized)
            profiles[key] = profiles[key].merge(profile)
        else:
            sanitized_order[key] = sanitized
            profiles[key] = profile

    sanitized_list = list(sanitized_order.values())
    sanitized_list.sort(key=lambda item: item.get("metadata", {}).get("source_index", 0))

    return sanitized_list, profiles


def normalize_character_bible(raw: Any) -> Dict[str, CharacterProfile]:
    _, profiles = normalize_character_elements(raw)
    return profiles


def merge_character_bibles(
    base: Dict[str, CharacterProfile],
    updates: Dict[str, CharacterProfile],
) -> Dict[str, CharacterProfile]:
    if not base and not updates:
        return {}

    merged = dict(base or {})

    for update in (updates or {}).values():
        existing = merged.get(update.canonical_id)
        if existing:
            merged[update.canonical_id] = existing.merge(update)
            continue

        existing = next(
            (
                profile
                for profile in merged.values()
                if profile.display_name.strip().casefold()
                == update.display_name.strip().casefold()
            ),
            None,
        )
        if existing:
            adjusted = CharacterProfile.from_dict(update.to_dict())
            adjusted.canonical_id = existing.canonical_id
            if adjusted.display_name not in adjusted.aliases:
                adjusted.aliases.append(adjusted.display_name)
            if existing.display_name not in adjusted.aliases:
                adjusted.aliases.append(existing.display_name)
            merged[existing.canonical_id] = existing.merge(adjusted)
            continue

        merged[update.canonical_id] = update

    return merged


@dataclass
class StoryPlan:
    """Global plan for a project-mode video composed by multiple episodes."""

    project_id: str
    user_prompt: str
    target_duration_seconds: int
    aspect_ratio: str
    episodes: List[EpisodePlan] = field(default_factory=list)
    global_theme: str = ""
    character_bible: Dict[str, CharacterProfile] = field(default_factory=dict)
    visual_style: Dict[str, Any] = field(default_factory=dict)
    tone_and_mood: str = ""
    additional_notes: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.character_bible = normalize_character_bible(self.character_bible)

    def add_episode(self, episode: EpisodePlan) -> None:
        self.episodes.append(episode)
        self.episodes.sort(key=lambda ep: ep.sequence_index)

    @property
    def total_planned_duration(self) -> int:
        return sum(ep.target_duration_seconds for ep in self.episodes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "user_prompt": self.user_prompt,
            "target_duration_seconds": self.target_duration_seconds,
            "aspect_ratio": self.aspect_ratio,
            "episodes": [
                {
                    "episode_id": ep.episode_id,
                    "sequence_index": ep.sequence_index,
                    "title": ep.title,
                    "target_duration_seconds": ep.target_duration_seconds,
                    "summary": ep.summary,
                    "narrative_purpose": ep.narrative_purpose,
                    "continuity_notes": ep.continuity_notes,
                    "required_assets": ep.required_assets,
                    "script_draft": ep.script_draft,
                    "status": ep.status.value,
                }
                for ep in self.episodes
            ],
            "global_theme": self.global_theme,
            "character_bible": {
                cid: profile.to_dict() for cid, profile in self.character_bible.items()
            },
            "visual_style": self.visual_style,
            "tone_and_mood": self.tone_and_mood,
            "additional_notes": self.additional_notes,
        }

    def merge_character_profiles(self, profiles: Dict[str, CharacterProfile]) -> None:
        if not profiles:
            return
        self.character_bible = merge_character_bibles(self.character_bible, profiles)

    def character_profiles(self) -> List[CharacterProfile]:
        return list(self.character_bible.values())


class EpisodeExecutionStatus(str, Enum):
    """Execution/runtime lifecycle states for an episode run."""

    IDLE = "idle"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"
    STALE = "stale"


class ProjectOperationState(str, Enum):
    """Status vocabulary for project-scoped async operations."""

    IDLE = "idle"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ProjectOperationStatus:
    """Typed progress state for a single project-scoped operation."""

    status: ProjectOperationState = ProjectOperationState.IDLE
    task_id: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "task_id": self.task_id,
            "error": self.error,
        }


@dataclass
class ProjectProgressState:
    """Typed project-level planning/reference progress projection."""

    planning: ProjectOperationStatus = field(default_factory=ProjectOperationStatus)
    character_references: ProjectOperationStatus = field(default_factory=ProjectOperationStatus)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "planning": self.planning.to_dict(),
            "character_references": self.character_references.to_dict(),
        }


@dataclass
class EpisodeRuntimeState:
    """Runtime execution status for an episode during orchestration."""

    episode_id: str
    status: EpisodeExecutionStatus = EpisodeExecutionStatus.IDLE
    approved_script: str = ""
    workflow_task_id: Optional[str] = None
    aggregated_cost: float = 0.0
    aggregated_tokens: int = 0
    output_assets: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "status": self.status.value,
            "approved_script": self.approved_script,
            "workflow_task_id": self.workflow_task_id,
            "aggregated_cost": self.aggregated_cost,
            "aggregated_tokens": self.aggregated_tokens,
            "output_assets": self.output_assets,
            "error": self.error,
        }


@dataclass
class ProjectState:
    """Aggregated state for the long-form project orchestration."""

    project_id: str
    mode: str
    story_plan: StoryPlan
    episodes_runtime: Dict[str, EpisodeRuntimeState] = field(default_factory=dict)
    progress: ProjectProgressState = field(default_factory=ProjectProgressState)
    global_settings: Dict[str, Any] = field(default_factory=dict)
    cost_budget: Optional[float] = None
    total_cost: float = 0.0
    total_tokens: int = 0
    completed_episodes: int = 0
    style_profile: Dict[str, Any] = field(default_factory=dict)
    character_bible: Dict[str, CharacterProfile] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalize project-level character bible to canonical profiles
        if self.character_bible:
            self.character_bible = normalize_character_bible(self.character_bible)

    def ensure_runtime_state(self, episode_id: str) -> EpisodeRuntimeState:
        if episode_id not in self.episodes_runtime:
            self.episodes_runtime[episode_id] = EpisodeRuntimeState(episode_id=episode_id)
        return self.episodes_runtime[episode_id]

    def update_cost(self, episode_id: str, cost: float, tokens: int) -> None:
        runtime = self.ensure_runtime_state(episode_id)
        runtime.aggregated_cost += cost
        runtime.aggregated_tokens += tokens
        self.total_cost += cost
        self.total_tokens += tokens

    def mark_episode_runtime_status(
        self,
        episode_id: str,
        status: EpisodeExecutionStatus,
        error: Optional[str] = None,
    ) -> None:
        runtime = self.ensure_runtime_state(episode_id)
        runtime.status = status
        runtime.error = error
        if status == EpisodeExecutionStatus.COMPLETED:
            self.completed_episodes = sum(
                1
                for state in self.episodes_runtime.values()
                if state.status == EpisodeExecutionStatus.COMPLETED
            )
        else:
            self.completed_episodes = sum(
                1
                for state in self.episodes_runtime.values()
                if state.status == EpisodeExecutionStatus.COMPLETED
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "mode": self.mode,
            "story_plan": self.story_plan.to_dict(),
            "episodes_runtime": {
                episode_id: runtime.to_dict()
                for episode_id, runtime in self.episodes_runtime.items()
            },
            "progress": self.progress.to_dict(),
            "global_settings": self.global_settings,
            "cost_budget": self.cost_budget,
            "total_cost": self.total_cost,
            "total_tokens": self.total_tokens,
            "completed_episodes": self.completed_episodes,
            "style_profile": self.style_profile,
            "character_bible": {
                cid: profile.to_dict() if isinstance(profile, CharacterProfile) else profile
                for cid, profile in self.character_bible.items()
            },
        }


class ProjectStateRepository:
    """In-memory repository for project states (MVP scope)."""

    def __init__(self) -> None:
        self._states: Dict[str, ProjectState] = {}

    def save(self, project_state: ProjectState) -> ProjectState:
        self._states[project_state.project_id] = project_state
        return project_state

    def get(self, project_id: str) -> Optional[ProjectState]:
        return self._states.get(project_id)

    def remove(self, project_id: str) -> None:
        if project_id in self._states:
            del self._states[project_id]

    def list_states(self) -> List[ProjectState]:
        return list(self._states.values())


project_state_repository = ProjectStateRepository()
