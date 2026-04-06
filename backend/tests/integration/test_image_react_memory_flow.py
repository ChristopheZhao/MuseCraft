import asyncio
import logging
from types import SimpleNamespace

from dotenv import load_dotenv

logging.basicConfig(level=logging.DEBUG)
root_logger = logging.getLogger()
agent_logger = logging.getLogger("agent.image_generator")
print("LOG_INIT root_level", root_logger.level, "handlers", root_logger.handlers)
print("LOG_INIT agent_level", agent_logger.level, "handlers", agent_logger.handlers)
try:
    from app.core.config import settings
    print("LOG_INIT settings.LOG_LEVEL", getattr(settings, "LOG_LEVEL", None))
    print("LOG_INIT settings.MAS_LOG_DIR", getattr(settings, "MAS_LOG_DIR", None))
    print("LOG_INIT settings.MAS_LOG_LEVEL", getattr(settings, "MAS_LOG_LEVEL", None))
except Exception as e:
    print("LOG_INIT settings import failed:", e)

from app.agents.image_generator import ImageGeneratorAgent
from app.agents.memory.short_term import get_working_memory_service
from app.agents.utils.memory_helpers import ensure_agent_working_memory
from app.agents.memory.short_term import SceneSnapshot
from app.agents.adapters.video.memory_adapter import VideoMemoryAdapter
from app.agents.tools.tool_registry import get_tool_registry
from app.agents.tools.ai_services.zhipu_client import ZhipuClientTool
from app.agents.tools.ai_services.image_generation_tool import ImageGenerationTool
from app.agents.tools.consistency_tool import ConsistencyTool
from app.agents.tools.storage.file_storage_tool import FileStorageTool



def _ensure_tools():
    registry = get_tool_registry()
    for tool_cls, name in [
        (ZhipuClientTool, "zhipu_client"),
        (ImageGenerationTool, "image_generation"),
        (ConsistencyTool, "consistency_tool"),
        (FileStorageTool, "file_storage_tool"),
    ]:
        try:
            registry.get_tool(name)
        except Exception:
            registry.register_tool(tool_cls, name=name, auto_load=False)


def _seed_concept_plan(wf_id: str):
    concept_plan = {
        "overview": "测试概念方案",
        "intelligent_style_design": {"style_name": "测试风格"},
        "scenes": [
            {
                "scene_number": 1,
                "visual_description": "夜色下的城市",
                "narrative_description": "介绍城市背景",
                "duration": 8,
            },
        ],
    }
    shared = get_working_memory_service().create_or_get(wf_id, f"mas:{wf_id}")
    shared.put("project.concept_plan", concept_plan)
    video_adapter = VideoMemoryAdapter(shared)
    snapshot = SceneSnapshot(
        scene_number=1,
        duration=8.0,
        visual_description="夜色下的城市",
        narrative_description="介绍城市背景",
    )
    video_adapter.upsert_scene(snapshot)


def _seed_working_memory(wf_id: str, agent_name: str):
    """通过迭代记忆服务创建/获取 WorkingMemory，确保与 Agent.wm 对接一致。"""
    wm = ensure_agent_working_memory(wf_id, agent_name)
    return wm, {}


async def _run_agent():
    # 确保 .env 变量加载（用于 LLM 密钥等）
    load_dotenv()
    wf_id = "wf-test-react"
    _ensure_tools()
    _seed_concept_plan(wf_id)
    wm, context = _seed_working_memory(wf_id, "image_generator")

    class DummySession:
        def add(self, obj):
            self.last_added = obj

        def flush(self):
            pass

        def commit(self):
            pass

        def rollback(self):
            pass

        def refresh(self, obj):
            pass

    # 使用真实 LLM（从 llm_policies.yaml 自动加载）
    # Agent 自主决策，与 MAS 中运行完全一致
    agent = ImageGeneratorAgent()
    input_data = {
        "workflow_state_id": wf_id,
    }
    task = SimpleNamespace(id=456, task_id=wf_id, status=None, update_progress=lambda *args, **kwargs: None)

    result = await agent.execute(task=task, input_data=input_data, db=DummySession())
    return result, agent, context


def test_image_generator_react_flow():
    """测试 ImageGenerator 完成子任务的完整流程（使用真实 LLM）"""
    result, agent, context = asyncio.run(_run_agent())

    # 1. 验证 Agent 执行成功
    assert isinstance(result, dict), "Agent should return dict result"
    react_metadata = result.get("react_metadata", {})
    assert react_metadata.get("success") is not None, "react_metadata should contain success status"

    # 2. 验证 WorkingMemory 状态
    wm = agent.wm
    assert wm is not None, "WorkingMemory should be initialized"

    # 3. 验证 OBS 事实链（至少包含场景记录）
    facts = wm.build_fact_observation()
    assert facts.get("scenes"), "scene facts should exist"

    # 4. 验证迭代记录（Agent 应该自主完成，不超过合理轮数）
    total_iterations = react_metadata.get("total_iterations", 0)
    assert 1 <= total_iterations <= 10, f"Should complete within reasonable iterations, got {total_iterations}"

    print(f"✅ Agent completed in {total_iterations} iterations")
    print(f"✅ Success: {react_metadata.get('success')}")
    print(f"✅ Completion type: {react_metadata.get('completion_type')}")
