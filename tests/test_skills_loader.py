"""Tests for skills loader in Brain and Antigravity .agents/skills/ architecture."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harvey.brain import Brain


@pytest.fixture
def mock_brain():
    state = MagicMock()
    return Brain(state)


def test_load_skill_from_agents_skills(mock_brain):
    """Verify loading from .agents/skills/ with frontmatter stripped."""
    content = mock_brain.load_skill("email_frameworks")
    assert content != ""
    # Frontmatter must be stripped
    assert not content.strip().startswith("---")
    # All 5 frameworks must be present
    assert "AIDA" in content
    assert "PAS" in content
    assert "BAB" in content
    assert "QVC" in content
    assert "3Ps" in content
    # Invariant human rules
    assert "Em dashes" in content
    assert "Under 75 words" in content


def test_load_skill_signal_playbook(mock_brain):
    """Verify signal playbook preserves prioritization and footer agency thresholds."""
    content = mock_brain.load_skill("signal_playbook")
    assert content != ""
    assert not content.strip().startswith("---")
    # Agency thresholds
    assert "0.90" in content or "0.9" in content
    assert "0.75" in content
    assert "0.35" in content
    # Prioritization rules
    assert "hiring > funding" in content


def test_load_skill_fallback_to_skills_dir(mock_brain, monkeypatch):
    """Verify fallback to skills/ directory if .agents/skills/ does not exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        test_file = skills_dir / "custom_test_skill.md"
        test_file.write_text("# Custom Skill Content\nHello world!", encoding="utf-8")

        monkeypatch.setattr("harvey.brain.SKILLS_DIR", skills_dir)
        # Load skill that only exists in skills_dir
        content = mock_brain.load_skill("custom_test_skill")
        assert content == "# Custom Skill Content\nHello world!"


def test_load_skill_nonexistent(mock_brain):
    """Verify missing skill returns empty string without error."""
    assert mock_brain.load_skill("non_existent_skill_xyz") == ""


def test_load_skills_for_agent(mock_brain):
    """Verify load_skills_for_agent returns concatenated FOUNDATIONAL KNOWLEDGE."""
    writer_skills = mock_brain.load_skills_for_agent("writer")
    assert "## FOUNDATIONAL KNOWLEDGE" in writer_skills
    assert "email-frameworks" not in writer_skills  # frontmatter should not be leaked
    assert "AIDA" in writer_skills

    scout_skills = mock_brain.load_skills_for_agent("scout")
    assert "## FOUNDATIONAL KNOWLEDGE" in scout_skills
    assert "Google Dorking" in scout_skills

    empty_skills = mock_brain.load_skills_for_agent("unknown_agent")
    assert empty_skills == ""
