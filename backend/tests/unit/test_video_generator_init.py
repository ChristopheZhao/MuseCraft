from app.agents.tools import register_default_tools
from app.agents.video_generator import VideoGeneratorAgent


def test_video_generator_has_video_config():
    # 确保工具已注册（避免 Agent 初始化阶段因未注册工具而失败）
    register_default_tools()
    agent = VideoGeneratorAgent()
    # __init__ 应初始化视频配置（用于提供商能力约束等）
    assert hasattr(agent, "video_config") and agent.video_config is not None


def test_planning_decision_schema_shape():
    register_default_tools()
    agent = VideoGeneratorAgent()
    schema = agent._planning_decision_schema()
    # 关键字段存在且类型正确
    assert schema["type"] == "object"
    props = schema["properties"]
    for key in ["intent", "selected_units", "plan_digest"]:
        assert key in props
    assert "required" in schema and "plan_digest" in schema["required"]
