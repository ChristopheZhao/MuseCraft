import os
import sys
import json


def setup_path():
    # Ensure backend/app is on sys.path
    here = os.path.abspath(os.path.dirname(__file__))
    backend_root = os.path.abspath(os.path.join(here, os.pardir))
    app_path = os.path.join(backend_root, 'app')
    if app_path not in sys.path:
        sys.path.insert(0, app_path)


def main():
    setup_path()
    from app.core.prompt_manager import get_prompt_manager

    pm = get_prompt_manager()
    configs = pm.list_configs()
    print("Loaded configs:", configs)

    def render(cfg, tpl, vars):
        try:
            txt = pm.render_template(cfg, tpl, variables=vars, use_cache=False, auto_reload=True)
            print(f"[OK] {cfg}.{tpl} -> {len(txt)} chars")
        except Exception as e:
            try:
                tlist = pm.list_templates(cfg)
            except Exception:
                tlist = []
            print(f"[FAIL] {cfg}.{tpl}: {e}; templates_in_cfg={tlist}")

    # Image observation
    image_vars = {
        "facts_json": json.dumps({"summary": {"total": 3, "pending": 3}}, ensure_ascii=False, indent=2),
        "schema_json": json.dumps({"type": "object", "properties": {"summary": {"type": "object"}, "scenes": {"type": "array"}}}, ensure_ascii=False, indent=2)
    }
    render("image_generator", "observation", image_vars)

    # Video observation
    video_vars = {
        "facts_json": json.dumps({"summary": {"total": 2, "pending": 2}}, ensure_ascii=False, indent=2),
        "schema_json": json.dumps({"type": "object", "properties": {"summary": {"type": "object"}, "scenes": {"type": "array"}}}, ensure_ascii=False, indent=2)
    }
    render("video_generator", "observation", video_vars)

    # Orchestrator decision
    render("orchestrator", "decision_system", {"primary_role": "工作流编排器"})
    render("orchestrator", "decision_user", {
        "agent_name": "image_generator",
        "meta_json": json.dumps({"k": 1}, ensure_ascii=False),
        "summary_json": json.dumps({"done": 1}, ensure_ascii=False),
        "success_count": 1,
        "fail_count": 0,
    })

    # ReAct orchestrator FC decision
    render("react_orchestrator", "fc_decision_user", {
        "completed_json": json.dumps(["script_writer"], ensure_ascii=False),
        "failed_json": json.dumps([], ensure_ascii=False),
        "quality_json": json.dumps({"overall": 8.5}, ensure_ascii=False),
        "iteration": 1,
    })


if __name__ == "__main__":
    main()

