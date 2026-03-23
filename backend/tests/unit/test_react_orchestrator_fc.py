import asyncio
import pytest

from app.agents.react_orchestrator import ReActOrchestratorAgent


@pytest.mark.asyncio
async def test_orchestrator_builds_without_ai_client(monkeypatch):
    monkeypatch.setattr(ReActOrchestratorAgent, "_load_tools", lambda self, tool_names: None)
    agent = ReActOrchestratorAgent.create_default()
    # 仅验证对象可创建，且不存在 ai_client 属性（已去除直连）
    assert not hasattr(agent, 'ai_client')
