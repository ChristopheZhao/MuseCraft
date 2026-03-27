from pathlib import Path

import yaml


def _repo_paths():
    backend_root = Path(__file__).resolve().parents[2]
    repo_root = backend_root.parent
    return repo_root, backend_root


def test_concept_planner_deepseek_route_is_exposed_in_env_examples():
    repo_root, backend_root = _repo_paths()
    policy_path = backend_root / "app" / "config" / "llm_policies.yaml"
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}

    concept_plan_route = ((policy.get("agents.concept_planner") or {}).get("plan") or {})
    assert concept_plan_route, "concept_planner.plan route must be configured explicitly"

    if concept_plan_route.get("provider") != "deepseek":
        return

    expected_keys = [
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_DEFAULT_MODEL",
    ]
    env_example_paths = [
        repo_root / ".env.example",
        backend_root / ".env.example",
    ]

    for env_path in env_example_paths:
        content = env_path.read_text(encoding="utf-8")
        for key in expected_keys:
            assert key in content, f"{env_path} must document {key} for concept_planner DeepSeek routing"


def test_ai_config_marks_concept_planner_mapping_as_compatibility_only():
    _, backend_root = _repo_paths()
    ai_config_yaml = (backend_root / "config" / "ai_config.yaml").read_text(encoding="utf-8")

    assert "concept_planner 的主 planning supplier/model authority 不在这里" in ai_config_yaml
    assert "概念规划兼容映射；主 route authority 见 llm_policies.yaml" in ai_config_yaml
