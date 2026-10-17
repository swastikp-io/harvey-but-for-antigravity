"""Tests for Google Antigravity (agy) provider, quota client, streaming session,
and Brain integration."""

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import yaml

from harvey.antigravity import (
    AntigravityError,
    AntigravityProvider,
    AntigravityQuotaClient,
    AntigravityResult,
    AntigravityStreamSession,
    DEFAULT_TOOL_FLAGS,
    _MAX_ARGV_PROMPT_CHARS,
)
from harvey.brain import Brain, BrainUnavailable
import harvey.brain as brain_mod
from harvey.config import BrainConfig, ConfigError, HarveyConfig, UsageConfig, load_brain_config
from harvey.state import StateManager

BASE_CONFIG = {
    "persona": {"name": "H", "company": "A", "role": "B", "email": "e", "linkedin": "", "tone": "t"},
    "product": {"name": "P", "description": "D", "pricing": "$1", "key_benefits": [], "objection_responses": {}},
    "icp": {"industries": [], "company_size": "", "titles": [], "geography": []},
}


@pytest_asyncio.fixture
async def state():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = StateManager(os.path.join(tmpdir, "test_antigravity.db"))
        await sm.init_db()
        yield sm


# ── Configuration & Aliases ──────────────────────────────────────────


def test_antigravity_provider_in_brain_config():
    cfg = BrainConfig(provider="antigravity", model="gemini-3.8-flash")
    assert cfg.provider == "antigravity"
    assert cfg.model == "gemini-3.8-flash"


def test_usage_config_provider_percent_alias():
    # Setting max_daily_provider_percent syncs to max_daily_claude_percent
    u1 = UsageConfig(max_daily_provider_percent=70.0)
    assert u1.max_daily_claude_percent == 70.0
    assert u1.max_daily_provider_percent == 70.0

    # Setting max_daily_claude_percent syncs to max_daily_provider_percent
    u2 = UsageConfig(max_daily_claude_percent=65.0)
    assert u2.max_daily_provider_percent == 65.0


def test_load_brain_config_antigravity(tmp_path):
    path = tmp_path / "harvey.yaml"
    path.write_text(yaml.dump({"brain": {"provider": "antigravity", "model": "gemini-pro"}}))
    cfg = load_brain_config(str(path))
    assert cfg.provider == "antigravity"
    assert cfg.model == "gemini-pro"


# ── AntigravityProvider Subprocess Calls & Safety ────────────────────


class _FakeProcess:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self.stdin_data = None

    async def communicate(self, data=None):
        self.stdin_data = data
        return self._stdout, self._stderr

    def kill(self):
        pass

    async def wait(self):
        return self.returncode


@pytest.mark.asyncio
async def test_provider_invokes_agy_with_safety_flags(monkeypatch):
    captured = {}

    async def fake_exec(*cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["kwargs"] = kwargs
        payload = json.dumps({
            "type": "result",
            "result": "Generated cold email content",
            "model": "gemini-3.8-flash",
            "usage": {"input_tokens": 150, "output_tokens": 50, "total_cost_usd": 0.0},
        }).encode("utf-8")
        return _FakeProcess(stdout=payload)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    provider = AntigravityProvider(model="gemini-3.8-flash", agy_path="agy")
    result = await provider.run("Draft an email for Acme Corp", output_format="json")

    assert result.text == "Generated cold email content"
    assert result.model == "gemini-3.8-flash"
    assert result.usage["input_tokens"] == 150
    assert result.usage["output_tokens"] == 50

    # Verify command line arguments
    cmd = captured["cmd"]
    assert cmd[0] == "agy"
    assert "-p" in cmd
    assert "--output-format" in cmd and cmd[cmd.index("--output-format") + 1] == "json"
    # Invariant: tool isolation enabled
    assert "--tools" in cmd and cmd[cmd.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in cmd
    assert "--model" in cmd and cmd[cmd.index("--model") + 1] == "gemini-3.8-flash"


@pytest.mark.asyncio
async def test_provider_long_prompt_via_stdin(monkeypatch):
    captured = {}

    async def fake_exec(*cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["kwargs"] = kwargs
        proc = _FakeProcess(stdout=b'{"type": "result", "result": "done"}')
        captured["proc"] = proc
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    provider = AntigravityProvider(agy_path="agy")
    long_prompt = "x" * (_MAX_ARGV_PROMPT_CHARS + 50)
    await provider.run(long_prompt)

    # Long prompt must NOT be in argv (Windows cap protection)
    assert long_prompt not in captured["cmd"]
    assert captured["kwargs"]["stdin"] == asyncio.subprocess.PIPE
    assert captured["proc"].stdin_data == long_prompt.encode("utf-8")

    # Short prompt goes in argv
    short_prompt = "Short prompt"
    await provider.run(short_prompt)
    assert short_prompt in captured["cmd"]
    assert captured["kwargs"]["stdin"] == asyncio.subprocess.DEVNULL


@pytest.mark.asyncio
async def test_provider_text_output_format(monkeypatch):
    async def fake_exec(*cmd, **kwargs):
        return _FakeProcess(stdout=b"Raw plain text response")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    provider = AntigravityProvider(agy_path="agy")
    result = await provider.run("Hello", output_format="text")
    assert result.text == "Raw plain text response"


@pytest.mark.asyncio
async def test_provider_error_classification(monkeypatch):
    provider = AntigravityProvider(agy_path="agy")

    # Auth error
    async def fake_auth_error(*cmd, **kwargs):
        return _FakeProcess(returncode=1, stderr=b"Unauthorized: please run `agy login`")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_auth_error)
    with pytest.raises(AntigravityError) as exc_auth:
        await provider.run("test")
    assert exc_auth.value.kind == "auth"
    assert exc_auth.value.retryable is False

    # Usage limit error
    async def fake_quota_error(*cmd, **kwargs):
        return _FakeProcess(returncode=1, stderr=b"Quota exceeded: out of credits")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_quota_error)
    with pytest.raises(AntigravityError) as exc_quota:
        await provider.run("test")
    assert exc_quota.value.kind == "usage_limit"
    assert exc_quota.value.retryable is False

    # Transient error
    async def fake_transient_error(*cmd, **kwargs):
        return _FakeProcess(returncode=1, stderr=b"Transient socket reset")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_transient_error)
    with pytest.raises(AntigravityError) as exc_trans:
        await provider.run("test")
    assert exc_trans.value.kind == "cli_error"
    assert exc_trans.value.retryable is True


# ── Persistent Streaming Session ─────────────────────────────────────


class _FakeStreamProcess:
    def __init__(self):
        self.returncode = None
        self.stdin = MagicMock()
        self.stdin.drain = AsyncMock()
        self.stdout = AsyncMock()
        self._lines = []

    def queue_line(self, line: bytes):
        self._lines.append(line)

    async def readline(self):
        if self._lines:
            return self._lines.pop(0)
        return b""

    def kill(self):
        self.returncode = 0

    async def wait(self):
        self.returncode = 0
        return 0


@pytest.mark.asyncio
async def test_stream_session_batching(monkeypatch):
    fake_proc = _FakeStreamProcess()
    fake_proc.stdout.readline = fake_proc.readline

    async def fake_exec(*cmd, **kwargs):
        assert "--input-format" in cmd and "stream-json" in cmd
        assert "--output-format" in cmd and "stream-json" in cmd
        assert "--tools" in cmd and "" in cmd
        return fake_proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    provider = AntigravityProvider(agy_path="agy")
    session = provider.create_stream_session()
    await session.start()

    # Queue mock responses for 2 turns
    fake_proc.queue_line(json.dumps({"id": "1", "type": "result", "result": "Turn 1 answer"}).encode() + b"\n")
    fake_proc.queue_line(json.dumps({"id": "2", "type": "result", "result": "Turn 2 answer"}).encode() + b"\n")

    res1 = await session.send("Prompt 1", turn_id="1")
    assert res1.text == "Turn 1 answer"
    assert res1.session_id == "1"

    res2 = await session.send("Prompt 2", turn_id="2")
    assert res2.text == "Turn 2 answer"
    assert res2.session_id == "2"

    await session.close()


# ── Quota & Credit Checking ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_quota_client_parsing_formats():
    client = AntigravityQuotaClient()

    # Format 1: Direct utilization
    res1 = client._parse_quota_payload({"utilization": 42.5, "resets_at": "2026-10-18T00:00:00Z"})
    assert res1 == {"credits": {"utilization": 42.5, "resets_at": "2026-10-18T00:00:00Z"}}

    # Format 2: Credit accounting (credits_used / total_credits)
    res2 = client._parse_quota_payload({"credits_used": 250, "total_credits": 1000})
    assert res2 == {"credits": {"utilization": 25.0, "resets_at": ""}}

    # Format 3: Remaining balance (balance 200 out of 1000 -> 80% used)
    res3 = client._parse_quota_payload({"credit_balance": 200, "total": 1000})
    assert res3 == {"credits": {"utilization": 80.0, "resets_at": ""}}

    # Format 4: Window dictionary
    res4 = client._parse_quota_payload({"five_hour": {"utilization": 15.0, "resets_at": "soon"}})
    assert res4 == {"five_hour": {"utilization": 15.0, "resets_at": "soon"}}

    # Invalid payload returns None
    assert client._parse_quota_payload({}) is None
    assert client._parse_quota_payload("not a dict") is None


@pytest.mark.asyncio
async def test_quota_client_graceful_fallback_when_cli_unavailable(monkeypatch):
    client = AntigravityQuotaClient()
    monkeypatch.setattr(client, "_fetch", AsyncMock(return_value=None))

    windows = await client.get_utilization()
    assert windows is None  # Triggers fallback to call budget


# ── Brain Integration ────────────────────────────────────────────────


class _StubAntigravity:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.preflights = 0

    def fingerprint(self):
        return ("agy-v1",)

    async def preflight(self):
        self.preflights += 1
        if self.outcomes and isinstance(self.outcomes[0], AntigravityError):
            err = self.outcomes.pop(0)
            raise err

    async def run(self, prompt, timeout, session_id=None, skip_if=None):
        self.calls += 1
        if not self.outcomes:
            return AntigravityResult(text="default")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_antigravity_brain_never_touches_claude(state, monkeypatch):
    async def no_claude(*a, **k):
        raise AssertionError("Antigravity brain must not run the Claude CLI")

    monkeypatch.setattr(brain_mod.asyncio, "create_subprocess_exec", no_claude)

    brain = Brain(state, BrainConfig(provider="antigravity", model="gemini-3.8-flash"))
    brain.antigravity = _StubAntigravity([
        AntigravityResult(
            text="Personalized pitch",
            model="gemini-3.8-flash",
            session_id="ses-1",
            duration_ms=450,
            usage={"input_tokens": 120, "output_tokens": 60, "cache_read_tokens": 0, "cache_creation_tokens": 0},
        )
    ])

    assert brain.provider_label == "Antigravity"
    assert await brain.think("Write email", agent="writer", task="outreach") == "Personalized pitch"

    # Verifies provider-specific call tracking in database
    assert await state.get_usage_today("antigravity") == 1
    assert await state.get_usage_today("claude") == 0
    assert await state.get_usage_today("codex") == 0

    rows = await state.usage_by_provider(days=1)
    assert rows[0]["provider"] == "antigravity"
    assert rows[0]["output_tokens"] == 60


@pytest.mark.asyncio
async def test_antigravity_think_json(state):
    brain = Brain(state, BrainConfig(provider="antigravity"))
    brain.antigravity = _StubAntigravity([
        AntigravityResult(text='```json\n{"fit": "high", "reason": "SaaS founder"}\n```')
    ])
    result = await brain.think_json("Analyze lead")
    assert result == {"fit": "high", "reason": "SaaS founder"}


@pytest.mark.asyncio
async def test_antigravity_budget_gate_with_quota_and_fallback(state):
    brain = Brain(state, BrainConfig(provider="antigravity"))

    # When quota is readable and over threshold -> gate blocks
    class MockQuotaOver:
        async def get_utilization(self):
            return {"credits": {"utilization": 88.0, "resets_at": ""}}

    brain.quota = MockQuotaOver()
    assert await brain.is_within_budget(max_daily_calls=50, max_percent=80.0) is False

    # When quota is readable and within threshold -> gate permits
    class MockQuotaUnder:
        async def get_utilization(self):
            return {"credits": {"utilization": 45.0, "resets_at": ""}}

    brain.quota = MockQuotaUnder()
    assert await brain.is_within_budget(max_daily_calls=50, max_percent=80.0) is True

    # When quota is unavailable -> cleanly falls back to Harvey's call count
    class MockQuotaUnavailable:
        async def get_utilization(self):
            return None

    brain.quota = MockQuotaUnavailable()
    # 0 calls made today, max 2 calls allowed
    assert await brain.is_within_budget(max_daily_calls=2, max_percent=80.0) is True
    # Increment usage to 2 calls
    await state.increment_usage(provider="antigravity")
    await state.increment_usage(provider="antigravity")
    # Now at limit
    assert await brain.is_within_budget(max_daily_calls=2, max_percent=80.0) is False
