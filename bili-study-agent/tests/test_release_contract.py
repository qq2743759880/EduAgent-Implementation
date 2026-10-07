from pathlib import Path
from app.chat.tool_calling import _heuristic_arg_defaults
from app.ai.skills.registry import PROJECT_SKILLS

def test_import_requires_authorized_source_selection():
    assert _heuristic_arg_defaults("knowledge_import") == {}

def test_skill_path_is_project_relative():
    assert Path(PROJECT_SKILLS) == Path(__file__).resolve().parents[2] / ".claude" / "skills"
