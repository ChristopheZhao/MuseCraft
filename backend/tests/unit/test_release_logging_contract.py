from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("relative_path", "forbidden_marker"),
    [
        ("app/agents/tools/storage/oss_storage_tool.py", "OSS_CLIENT_CONFIG key_id="),
        ("app/agents/tools/storage/oss_storage_tool.py", "secret_sha1="),
        ("app/agents/tools/ai_services/image_generation_tool.py", "source_url=%s"),
        ("scripts/start_dev_uv.py", "Environment proxy variables after cleanup:"),
        ("scripts/start_dev_uv.py", "print(str(e))"),
        ("scripts/start_dev_uv.py", "Redis check failed: {e}"),
    ],
)
def test_release_runtime_does_not_log_credential_material(relative_path, forbidden_marker):
    source = (BACKEND_ROOT / relative_path).read_text(encoding="utf-8")

    assert forbidden_marker not in source
