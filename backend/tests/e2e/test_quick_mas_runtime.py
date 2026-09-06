import asyncio
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.agents.concept_planner import ConceptPlannerAgent
from app.agents.script_writer import ScriptWriterAgent
from app.agents.tools.base_tool import ToolOutput
from app.agents.utils.memory_helpers import get_mas_working_memory
from app.agents.video_composer import VideoComposerAgent
from app.agents.video_generator import VideoGeneratorAgent
from app.api.v1.endpoints import tasks as tasks_endpoint
from app.core.config import settings
from app.core.database import Base, get_db
from app.domain import (
    AgentType,
    QueuedExecutionCommand,
    QueuedExecutionKind,
)
from app.infrastructure.orchestrator_composition import build_orchestrator_agent
from app.main import app
from app.services.memory_provider import build_memory_services
from app.services.queued_execution_use_case import QueuedExecutionUseCase
from app.services.runtime_attempt_keepalive_adapter import (
    create_runtime_attempt_keepalive_controller,
)
from app.services.task_queue import TaskQueueService


class _DeterministicPlanLLM:
    def __init__(self) -> None:
        agents = [
            AgentType.CONCEPT_PLANNER,
            AgentType.SCRIPT_WRITER,
            AgentType.VIDEO_GENERATOR,
            AgentType.VIDEO_COMPOSER,
        ]
        self._responses = [
            {
                "content": json.dumps(
                    {
                        "candidate_agents": [agent.value for agent in agents],
                        "selection_rationale": "minimal quick-video production path",
                    }
                )
            },
            {
                "content": json.dumps(
                    {
                        "agents": [
                            {
                                "agent": agent.value,
                                "run": True,
                                "mission": f"Produce the {agent.value} deliverable",
                                "deliverable": f"Accepted {agent.value} output",
                                "constraints": [],
                                "order": order,
                                "runtime_hints": (
                                    {"generate_audio": False}
                                    if agent is AgentType.VIDEO_GENERATOR
                                    else (
                                        {"compose_mode": "compose"}
                                        if agent is AgentType.VIDEO_COMPOSER
                                        else {}
                                    )
                                ),
                            }
                            for order, agent in enumerate(agents)
                        ],
                        "conditional_tasks": [],
                    }
                )
            },
        ]
        self.calls = []
        self.planning_calls = []
        self.runtime_decision_calls = []

    async def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        messages = kwargs.get("messages") or []
        if any(
            "运行时处置" in str(message.get("content") or "")
            for message in messages
            if isinstance(message, dict)
        ):
            self.runtime_decision_calls.append(kwargs)
            return {
                "content": json.dumps(
                    {
                        "action": "continue",
                        "reason": "The accepted artifact permits the workflow to continue",
                    }
                )
            }
        self.planning_calls.append(kwargs)
        if not self._responses:
            raise AssertionError("resume must use the persisted continuation plan")
        return self._responses.pop(0)


class _DeterministicConceptLLM:
    def __init__(self) -> None:
        self.calls = []

    async def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        prompt = kwargs["messages"][-1]["content"]
        if "概念规划的第一阶段" in prompt:
            payload = {
                "overview": "A concise current-architecture acceptance story",
                "genre_and_theme": {
                    "primary_genre": "documentary",
                    "theme": "calm beginnings",
                    "tone": "hopeful",
                },
                "target_audience": "general",
                "key_messages": ["A new day begins"],
                "scene_blueprint": [
                    {
                        "scene_number": scene_number,
                        "title": f"Arrival {scene_number}",
                        "narrative_goal": "Show the city moving into a new day",
                        "duration_hint": 10,
                        "key_elements": ["city", "sunrise"],
                        "atmosphere": "calm",
                    }
                    for scene_number in range(1, 4)
                ],
            }
        elif "概念规划第二阶段" in prompt or "概念规划的第二阶段" in prompt:
            payload = {
                "intelligent_style_design": {
                    "style_name": "Natural Dawn",
                    "style_description": "Clean documentary imagery",
                },
                "content_elements": {"characters": []},
                "consistency_hints": {
                    "visual": "Keep the sunrise palette consistent",
                    "narrative": "Maintain a calm progression",
                    "color_palette": ["amber", "blue"],
                },
            }
        elif "概念规划第三阶段" in prompt or "概念规划的第三阶段" in prompt:
            payload = {
                "voice_plan": {
                    "enabled": False,
                    "mode": "none",
                    "persona": "",
                    "tone_keywords": [],
                    "style_notes": "silent",
                    "scene_guidance": [],
                    "audio_strategy": {
                        "bgm_direction": "ambient",
                        "sfx_direction": "city ambience",
                        "mix_notes": "keep natural sound subtle",
                    },
                }
            }
        elif "概念规划第四阶段" in prompt or "概念规划的第四阶段" in prompt:
            batch_text = prompt.split("## 待细化场景批次", 1)[1].split(
                "## 输出要求", 1
            )[0]
            batch = json.loads(batch_text.strip())
            payload = {
                "scenes": [
                    {
                        "scene_number": scene["scene_number"],
                        "title": scene.get("title", f"Arrival {scene['scene_number']}"),
                        "scene_thesis": "Morning light reveals a waking city",
                        "description": "The city emerges into a calm new day",
                        "visual_description": "A calm city sunrise",
                        "narrative_description": "The opening establishes renewal",
                        "duration": 10,
                        "final_duration": 10,
                        "content_elements": {
                            "characters_present": [],
                            "environment": "city skyline",
                            "key_objects": ["buildings"],
                            "concepts_visualized": ["renewal"],
                        },
                        "mood_and_atmosphere": "calm",
                        "camera_language": "slow reveal",
                        "key_actions": ["sun rises"],
                        "audio_cues": ["distant city ambience"],
                        "transition_hint": "fade",
                    }
                    for scene in batch
                ],
                "notes": {
                    "consistency": "Preserve the dawn palette",
                    "duration_adjustment": "Use the provider-supported five seconds",
                },
            }
        else:
            raise AssertionError("unexpected concept-planner prompt")
        return {
            "content": json.dumps(payload),
            "finish_reason": "stop",
            "usage": {"total_tokens": 1},
        }


class _DeterministicReActLLM:
    def __init__(self, *, tool_calls, require_progress_read_model: bool = False) -> None:
        self._tool_calls = list(tool_calls)
        self._require_progress_read_model = require_progress_read_model
        self.function_calls = []
        self.contract_calls = []

    async def function_call(self, **kwargs):
        self.function_calls.append(kwargs)
        if len(self.function_calls) == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": f"call-{index}",
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": arguments,
                        },
                    }
                    for index, (tool_name, arguments) in enumerate(self._tool_calls, 1)
                ],
            }
        plan_input = str(kwargs["messages"][-1]["content"])
        if self._require_progress_read_model:
            assert '"planned_scene_numbers"' in plan_input, plan_input
        return {
            "content": "The required artifact has an accepted delivery receipt.",
            "finish_reason": "stop",
            "tool_calls": [],
        }

    async def chat_completion(self, **kwargs):
        self.contract_calls.append(kwargs)
        return {
            "content": json.dumps(
                {
                    "task_complete": True,
                    "completed_reason": "accepted delivery receipt observed",
                    "plan_summary": "No further action is required",
                }
            ),
            "finish_reason": "stop",
        }


class _DeterministicTool:
    def __init__(self, *, actions, handler) -> None:
        self._actions = list(actions)
        self._handler = handler
        self.calls = []

    def get_available_actions(self):
        return list(self._actions)

    def get_action_schema(self, action):
        assert action in self._actions
        return {"type": "object", "properties": {}}

    async def execute(self, tool_input):
        assert tool_input.action in self._actions
        self.calls.append(tool_input)
        result = self._handler(tool_input)
        if asyncio.iscoroutine(result):
            result = await result
        return ToolOutput(success=True, result=result, execution_time=0.0)


def _replace_allocated_tool(agent, tool_name: str, tool) -> None:
    assert tool_name in agent.allocated_tools
    assert tool_name in agent._available_tools
    agent._available_tools[tool_name] = tool


def test_quick_api_runs_current_mas_path_through_gate_resume_and_runtime_read_model(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "quick-mas-e2e.sqlite3"
    sync_engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    sync_session_factory = sessionmaker(
        bind=sync_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    async_engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async_session_factory = sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=sync_engine)

    storage_root = tmp_path / "storage"
    scene_video_path = storage_root / "scene-1.mp4"
    final_video_path = storage_root / "final.mp4"
    scene_video_path.parent.mkdir(parents=True)
    scene_video_path.write_bytes(b"scene-video")

    monkeypatch.setattr(settings, "TEMP_PATH", str(storage_root / "temp"))
    monkeypatch.setattr(settings, "UPLOAD_PATH", str(storage_root / "uploads"))
    monkeypatch.setattr(settings, "GENERATED_PATH", str(storage_root / "generated"))
    monkeypatch.setattr(settings, "FINAL_OUTPUT_ROOT", str(storage_root / "outputs"))
    monkeypatch.setattr(settings, "EPISODIC_EVENT_ENABLED", False)
    monkeypatch.setattr(settings, "TASKS_API_ENABLE_IN_PROCESS_RUNNER", False)
    monkeypatch.setenv("MEMORY_BACKEND", "dict")

    async def override_get_db():
        async with async_session_factory() as db:
            yield db

    memory_services = build_memory_services()
    plan_llm = _DeterministicPlanLLM()
    concept_llm = _DeterministicConceptLLM()
    video_llm = _DeterministicReActLLM(
        require_progress_read_model=True,
        tool_calls=[
            (
                "video_generation.generate_with_continuity",
                {
                    "scene_number": scene_number,
                    "duration": 10,
                    "prompt": f"A calm city sunrise, scene {scene_number}",
                },
            )
            for scene_number in range(1, 4)
        ],
    )
    composer_llm = _DeterministicReActLLM(
        tool_calls=[
            (
                "composition_tool.compose_story_video",
                {
                    "scenes": [
                        {"video_file": str(scene_video_path), "scene_number": scene_number}
                        for scene_number in range(1, 4)
                    ],
                    "output_filename": "final.mp4",
                },
            )
        ],
    )

    def generate_scripts(tool_input):
        scene_inputs = tool_input.parameters["scenes"]
        return {
            "scripts": {
                str(scene_input["scene_number"]): {
                    "scene_thesis": "Morning light reveals a waking city",
                    "script_text": (
                        f"Morning light opens scene {scene_input['scene_number']}."
                    ),
                    "narrative_description": "The opening establishes renewal.",
                    "voice_over_text": "",
                    "motion_beats": [],
                    "opening_state": "The skyline is dim",
                    "event_trigger": "The sun reaches the horizon",
                    "action_phases": [],
                    "end_state": "The city is illuminated",
                    "camera_language": "slow reveal",
                }
                for scene_input in scene_inputs
            },
            "failures": [],
        }

    script_tool = _DeterministicTool(
        actions=["generate_scene_scripts_batch"],
        handler=generate_scripts,
    )
    continuity_tool = _DeterministicTool(
        actions=["analyze_all_scenes_continuity"],
        handler=lambda _tool_input: {
            "continuity_decisions": {
                str(scene_number): {
                    "strategy": "new",
                    "reason": "single scene",
                    "motion_beats": [],
                }
                for scene_number in range(1, 4)
            }
        },
    )
    role_tool = _DeterministicTool(
        actions=["analyze_roles_and_scenes"],
        handler=lambda _tool_input: {
            "roles": [],
            "per_scene_roles": {
                str(scene_number): [] for scene_number in range(1, 4)
            },
        },
    )
    video_tool = _DeterministicTool(
        actions=["generate_with_continuity"],
        handler=lambda tool_input: {
            "scene_number": tool_input.parameters["scene_number"],
            "video_path": str(scene_video_path),
            "video_url": "",
            "duration_sec": 10.0,
            "prompt_text": tool_input.parameters.get("prompt", ""),
        },
    )

    def compose_video(_tool_input):
        final_video_path.write_bytes(scene_video_path.read_bytes())
        return {
            "output_path": str(final_video_path),
            "video_path": str(final_video_path),
        }

    composition_tool = _DeterministicTool(
        actions=["compose_story_video"],
        handler=compose_video,
    )
    specialist_type_snapshots = []

    def build_agent(_agent_type: AgentType):
        assert _agent_type is AgentType.ORCHESTRATOR
        orchestrator = build_orchestrator_agent(
            session_factory=sync_session_factory,
            memory_services=memory_services,
        )
        orchestrator._llms = {"plan": plan_llm}
        specialist_type_snapshots.append(
            {agent_type: type(agent) for agent_type, agent in orchestrator.agents.items()}
        )

        concept_agent = orchestrator.agents[AgentType.CONCEPT_PLANNER]
        script_agent = orchestrator.agents[AgentType.SCRIPT_WRITER]
        video_agent = orchestrator.agents[AgentType.VIDEO_GENERATOR]
        composer_agent = orchestrator.agents[AgentType.VIDEO_COMPOSER]

        concept_agent._llms = {"plan": concept_llm}
        _replace_allocated_tool(script_agent, "script_generation", script_tool)
        _replace_allocated_tool(
            script_agent,
            "scene_continuity_analysis_tool",
            continuity_tool,
        )
        _replace_allocated_tool(script_agent, "role_analysis_tool", role_tool)
        video_agent._llms = {"plan": video_llm}
        _replace_allocated_tool(video_agent, "video_generation", video_tool)
        composer_agent._llms = {"plan": composer_llm}
        _replace_allocated_tool(composer_agent, "composition_tool", composition_tool)
        return orchestrator

    use_case = QueuedExecutionUseCase(
        session_factory=sync_session_factory,
        agent_factory=build_agent,
        keepalive_factory=lambda logger: create_runtime_attempt_keepalive_controller(
            session_factory=sync_session_factory,
            logger=logger,
        ),
    )
    queue_service = TaskQueueService(execution_use_case=use_case)
    deliveries = []

    class _InlineCeleryTask:
        def delay(self, task_id: str):
            result = use_case.execute(
                QueuedExecutionCommand(
                    task_id=task_id,
                    execution_kind=QueuedExecutionKind.VIDEO_GENERATION,
                )
            )
            deliveries.append(result)
            return SimpleNamespace(id=f"inline-{len(deliveries)}")

    from app.services import celery_app as celery_app_module

    monkeypatch.setattr(celery_app_module, "process_video_task", _InlineCeleryTask())
    monkeypatch.setattr(tasks_endpoint, "TaskQueueService", lambda: queue_service)
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            created_response = client.post(
                "/api/v1/tasks/",
                json={
                    "user_prompt": "Create one calm sunrise scene",
                    "duration": 5,
                    "resolution": "720p",
                    "aspect_ratio": "16:9",
                    "session_id": "quick-mas-e2e",
                },
            )
            assert created_response.status_code == 200, created_response.text
            task_id = created_response.json()["task_id"]

            assert deliveries[0]["status"] == "waiting_gate"
            waiting_response = client.get(f"/api/v1/tasks/{task_id}/runtime")
            assert waiting_response.status_code == 200, waiting_response.text
            waiting_runtime = waiting_response.json()
            runtime_session_id = waiting_runtime["session_id"]
            waiting_nodes = {
                node["node_key"]: node for node in waiting_runtime["nodes"]
            }
            assert waiting_runtime["status"] == "waiting_gate"
            assert waiting_runtime["current_node_key"] == "script"
            assert waiting_runtime["active_gate"]["gate_name"] == "script_review"
            assert waiting_runtime["active_gate"]["status"] == "awaiting_human"
            assert waiting_nodes["concept"]["status"] == "completed"
            assert waiting_nodes["script"]["status"] == "pending_gate"
            assert len(concept_llm.calls) >= 4
            assert len(script_tool.calls) == 1
            assert len(continuity_tool.calls) == 1
            assert len(role_tool.calls) == 1
            assert video_tool.calls == []
            assert composition_tool.calls == []

            decision_response = client.post(
                f"/api/v1/tasks/{task_id}/runtime/script/decision",
                json={"action": "approve", "actor_id": "e2e-reviewer"},
            )
            assert decision_response.status_code == 200, decision_response.text
            assert deliveries[1]["status"] == "completed"

            completed_response = client.get(f"/api/v1/tasks/{task_id}/runtime")
            assert completed_response.status_code == 200, completed_response.text
            completed_runtime = completed_response.json()
            completed_nodes = {
                node["node_key"]: node for node in completed_runtime["nodes"]
            }
            assert completed_runtime["session_id"] == runtime_session_id
            assert completed_runtime["status"] == "completed"
            assert completed_runtime["resume_control"] is None
            assert completed_runtime["active_gate"]["latest_decision"]["action"] == "approve"
            assert completed_nodes["concept"]["status"] == "completed"
            assert completed_nodes["script"]["status"] == "completed"
            assert completed_nodes["video"]["status"] == "completed"
            assert completed_nodes["compose"]["status"] == "completed"
            assert completed_runtime["summary_output"]["status"] == "completed"
            assert completed_runtime["summary_output"]["final_video_path"] == str(
                final_video_path
            )
            expected_agent_types = {
                AgentType.CONCEPT_PLANNER: ConceptPlannerAgent,
                AgentType.SCRIPT_WRITER: ScriptWriterAgent,
                AgentType.VIDEO_GENERATOR: VideoGeneratorAgent,
                AgentType.VIDEO_COMPOSER: VideoComposerAgent,
            }
            assert len(specialist_type_snapshots) == 2
            for snapshot in specialist_type_snapshots:
                for agent_type, expected_type in expected_agent_types.items():
                    assert snapshot[agent_type] is expected_type

            assert len(video_tool.calls) == 3
            assert len(composition_tool.calls) == 1
            assert len(video_llm.function_calls) == 2
            assert len(video_llm.contract_calls) == 1
            assert len(composer_llm.function_calls) == 2
            assert len(composer_llm.contract_calls) == 1
            all_tool_calls = [
                *script_tool.calls,
                *continuity_tool.calls,
                *role_tool.calls,
                *video_tool.calls,
                *composition_tool.calls,
            ]
            workflow_ids = {
                tool_call.context["workflow_state_id"] for tool_call in all_tool_calls
            }
            assert len(workflow_ids) == 1
            assert video_tool.calls[0].context["execution_contract"][
                "workflow_state_id"
            ] in workflow_ids
            shared_memory = get_mas_working_memory(
                next(iter(workflow_ids)),
                service=memory_services.short_term,
            )
            scene_outputs = shared_memory.get("scene_outputs.video", {})
            for scene_number in range(1, 4):
                scene_output = scene_outputs.get(scene_number) or scene_outputs.get(
                    str(scene_number)
                )
                assert scene_output["acceptance_receipt"]["status"] == "accepted"
            assert final_video_path.read_bytes() == scene_video_path.read_bytes()
            assert len(plan_llm.planning_calls) == 2
            assert plan_llm.runtime_decision_calls
            assert all(
                call["response_format"] == {"type": "json_object"}
                for call in plan_llm.calls
            )
            assert all(
                call["response_format"] == {"type": "json_object"}
                for call in concept_llm.calls
            )
            assert all(
                call["response_format"] == {"type": "json_object"}
                for call in [
                    *video_llm.contract_calls,
                    *composer_llm.contract_calls,
                ]
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(async_engine.dispose())
        sync_engine.dispose()
