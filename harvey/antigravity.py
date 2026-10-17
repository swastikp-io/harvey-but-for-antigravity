"""Antigravity provider — Harvey's native thinking engine on Google Antigravity (agy).

Invokes the Antigravity CLI (`agy`) in headless mode (`-p`). Disables model tools
and sandbox execution so `agy` acts strictly as the text/reasoning engine while
Harvey's Python pipeline handles network requests, SQLite state, and email operations.
Includes persistent streaming session support via `--input-format stream-json
--output-format stream-json` for batching multiple turns in a single cycle.
"""

import asyncio
import json
import logging
import os
import shutil
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("harvey.antigravity")

DEFAULT_TIMEOUT_SECONDS = 300.0
RETRY_BASE_DELAY = 5.0
_MAX_ARGV_PROMPT_CHARS = 8000

# Subprocess safety: zero tools and isolated execution for prompts containing
# untrusted external text (prospect emails, scraped website content).
DEFAULT_TOOL_FLAGS = ["--tools", "", "--strict-mcp-config"]

_NON_RETRYABLE_PATTERNS = (
    "not logged in",
    "please run `agy login`",
    "please login",
    "invalid api key",
    "unauthorized",
    "authentication failed",
)

_USAGE_LIMIT_PATTERNS = (
    "quota exceeded",
    "credit limit reached",
    "out of credits",
    "insufficient credits",
    "rate limit exceeded",
    "resource exhausted",
)


class AntigravityError(Exception):
    """Failure reported by or communicating with the Antigravity CLI."""

    def __init__(self, message: str, kind: str = "general", retryable: bool = False):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable


@dataclass
class AntigravityResult:
    """Outcome of one Antigravity model call."""

    text: str
    model: str = ""
    session_id: str = ""
    duration_ms: int = 0
    usage: dict = field(default_factory=dict)


class AntigravityStreamSession:
    """Persistent streaming session communicating with `agy` over stream-json stdio.

    Used when Harvey batches multiple turns in a single cycle without
    re-spawning the CLI process for each prompt.
    """

    def __init__(self, provider: "AntigravityProvider"):
        self.provider = provider
        self.process: Optional[asyncio.subprocess.Process] = None
        self._lock = asyncio.Lock()

    async def start(self):
        """Start the persistent agy streaming subprocess."""
        if self.process is not None and self.process.returncode is None:
            return

        cmd = [
            self.provider.resolve_agy(),
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            *self.provider.tool_flags,
        ]
        if self.provider.model:
            cmd.extend(["--model", self.provider.model])

        try:
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            raise AntigravityError(
                "Antigravity CLI ('agy') not found. Install Antigravity to use this provider.",
                kind="setup",
                retryable=False,
            )

    async def send(
        self, prompt: str, turn_id: str | None = None, timeout: float = 120.0
    ) -> AntigravityResult:
        """Send a prompt turn and await the stream-json completion line."""
        if self.process is None or self.process.returncode is not None:
            await self.start()

        async with self._lock:
            msg_id = turn_id or uuid.uuid4().hex[:8]
            payload = json.dumps({
                "id": msg_id,
                "type": "prompt",
                "prompt": prompt,
            }) + "\n"

            t0 = time.monotonic()
            try:
                self.process.stdin.write(payload.encode("utf-8"))
                drain_ret = self.process.stdin.drain()
                if asyncio.iscoroutine(drain_ret) or hasattr(drain_ret, "__await__"):
                    await drain_ret

                line_bytes = await asyncio.wait_for(
                    self.process.stdout.readline(), timeout=timeout
                )
            except asyncio.TimeoutError:
                await self.close()
                raise AntigravityError(
                    f"Antigravity stream turn timed out after {timeout:.0f}s",
                    kind="timeout",
                    retryable=True,
                )
            except Exception as e:
                await self.close()
                raise AntigravityError(
                    f"Antigravity stream turn error: {e}",
                    kind="stream",
                    retryable=True,
                )

            duration_ms = int((time.monotonic() - t0) * 1000)
            if not line_bytes:
                await self.close()
                raise AntigravityError(
                    "Antigravity stream closed unexpectedly.",
                    kind="stream",
                    retryable=True,
                )

            raw = line_bytes.decode("utf-8", errors="replace").strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return AntigravityResult(
                    text=raw,
                    model=self.provider.model,
                    session_id=msg_id,
                    duration_ms=duration_ms,
                )

            if data.get("error"):
                raise AntigravityError(str(data["error"]), kind="stream", retryable=False)

            text = str(data.get("result") or data.get("text") or data.get("content") or "")
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            return AntigravityResult(
                text=text,
                model=str(data.get("model") or self.provider.model),
                session_id=msg_id,
                duration_ms=duration_ms,
                usage={
                    "input_tokens": int(usage.get("input_tokens") or usage.get("inputTokens") or 0),
                    "output_tokens": int(usage.get("output_tokens") or usage.get("outputTokens") or 0),
                    "cache_read_tokens": int(usage.get("cache_read_tokens") or 0),
                    "cache_creation_tokens": int(usage.get("cache_creation_tokens") or 0),
                    "cost_usd": float(usage.get("cost_usd") or usage.get("costUSD") or 0.0),
                },
            )

    async def close(self):
        """Close the persistent streaming subprocess."""
        if self.process is not None:
            try:
                if self.process.stdin:
                    self.process.stdin.close()
                self.process.kill()
                await self.process.wait()
            except Exception:
                pass
            self.process = None


class AntigravityProvider:
    """Invokes Google Antigravity (`agy`) in headless mode with strict safety boundaries."""

    def __init__(
        self,
        model: str = "",
        agy_path: str = "",
        tool_flags: list[str] | None = None,
    ):
        self.model = model.strip() if model else ""
        self._custom_agy_path = agy_path.strip() if agy_path else ""
        self.tool_flags = list(tool_flags) if tool_flags is not None else list(DEFAULT_TOOL_FLAGS)

    def resolve_agy(self) -> str:
        """Find the agy executable path."""
        if self._custom_agy_path:
            return self._custom_agy_path
        env_path = os.environ.get("AGY_PATH", "").strip()
        if env_path:
            return env_path
        found = shutil.which("agy")
        if found:
            return found
        if sys.platform == "win32":
            for ext in (".cmd", ".exe", ".bat"):
                cand = shutil.which(f"agy{ext}")
                if cand:
                    return cand
        return "agy"

    def fingerprint(self) -> tuple:
        """Fingerprint identifying current CLI location for health caching."""
        return (self.resolve_agy(),)

    async def preflight(self, timeout: float = 30.0) -> None:
        """Verify the Antigravity CLI is available and functional without sending inference."""
        agy = self.resolve_agy()
        if not shutil.which(agy):
            raise AntigravityError(
                "Antigravity CLI ('agy') not found. Please ensure Antigravity is installed.",
                kind="setup",
                retryable=False,
            )

        try:
            proc = await asyncio.create_subprocess_exec(
                agy, "--version",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            raise AntigravityError(
                "Antigravity preflight check timed out.",
                kind="timeout",
                retryable=True,
            )
        except Exception as e:
            raise AntigravityError(
                f"Antigravity preflight error: {e}",
                kind="setup",
                retryable=False,
            )

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            if any(p in err.lower() for p in _NON_RETRYABLE_PATTERNS):
                raise AntigravityError(f"Antigravity authentication required: {err}", kind="auth", retryable=False)
            raise AntigravityError(f"Antigravity CLI check failed: {err}", kind="setup", retryable=False)

    async def run(
        self,
        prompt: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        session_id: str | None = None,
        output_format: str = "json",
        skip_if=None,
    ) -> AntigravityResult:
        """Send a single prompt to `agy -p` with zero tool permissions.

        Returns text and structured token usage accounting.
        """
        if skip_if and skip_if():
            raise AntigravityError(skip_if(), kind="paused")

        agy = self.resolve_agy()
        prompt_via_stdin = len(prompt) > _MAX_ARGV_PROMPT_CHARS

        cmd = [agy, "-p"]
        if not prompt_via_stdin:
            cmd.append(prompt)

        cmd.extend(["--output-format", output_format])
        cmd.extend(self.tool_flags)

        if self.model:
            cmd.extend(["--model", self.model])
        if session_id:
            try:
                uuid.UUID(session_id)
                cmd.extend(["--session-id", session_id])
            except ValueError:
                pass

        logger.debug(f"Antigravity call (session={session_id}, format={output_format}): {prompt[:100]}...")

        t0 = time.monotonic()
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if prompt_via_stdin else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(prompt.encode("utf-8") if prompt_via_stdin else None),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            if process is not None:
                try:
                    process.kill()
                    await process.wait()
                except ProcessLookupError:
                    pass
            raise AntigravityError(
                f"Antigravity call timed out after {timeout:.0f}s.",
                kind="timeout",
                retryable=True,
            )
        except FileNotFoundError:
            raise AntigravityError(
                "Antigravity CLI ('agy') not found.",
                kind="setup",
                retryable=False,
            )
        except asyncio.CancelledError:
            if process is not None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            raise

        duration_ms = int((time.monotonic() - t0) * 1000)

        if process.returncode != 0:
            error_text = stderr.decode("utf-8", errors="replace").strip()
            lowered = error_text.lower()
            if any(p in lowered for p in _NON_RETRYABLE_PATTERNS):
                raise AntigravityError(
                    f"Antigravity auth error: {error_text}",
                    kind="auth",
                    retryable=False,
                )
            if any(p in lowered for p in _USAGE_LIMIT_PATTERNS):
                raise AntigravityError(
                    f"Antigravity usage limit reached: {error_text}",
                    kind="usage_limit",
                    retryable=False,
                )
            raise AntigravityError(
                f"Antigravity exited with code {process.returncode}: {error_text[:300]}",
                kind="cli_error",
                retryable=True,
            )

        raw = stdout.decode("utf-8", errors="replace").strip()
        if output_format == "json":
            return self._parse_json_result(raw, duration_ms, session_id or "")

        return AntigravityResult(
            text=raw,
            model=self.model,
            session_id=session_id or "",
            duration_ms=duration_ms,
        )

    def _parse_json_result(self, raw: str, duration_ms: int, session_id: str) -> AntigravityResult:
        """Parse structured CLI output or degrade cleanly to text."""
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return AntigravityResult(
                text=raw,
                model=self.model,
                session_id=session_id,
                duration_ms=duration_ms,
            )

        if not isinstance(payload, dict):
            return AntigravityResult(
                text=raw,
                model=self.model,
                session_id=session_id,
                duration_ms=duration_ms,
            )

        text = str(payload.get("result") or payload.get("text") or payload.get("content") or "")
        model = str(payload.get("model") or self.model)
        sid = str(payload.get("session_id") or session_id)
        dur = int(payload.get("duration_ms") or duration_ms)

        usage = payload.get("usage")
        parsed_usage = {}
        if isinstance(usage, dict):
            parsed_usage = {
                "input_tokens": int(usage.get("input_tokens") or usage.get("inputTokens") or 0),
                "output_tokens": int(usage.get("output_tokens") or usage.get("outputTokens") or 0),
                "cache_read_tokens": int(usage.get("cache_read_input_tokens") or usage.get("cache_read_tokens") or 0),
                "cache_creation_tokens": int(usage.get("cache_creation_input_tokens") or usage.get("cache_creation_tokens") or 0),
                "cost_usd": float(payload.get("total_cost_usd") or usage.get("cost_usd") or 0.0),
            }

        return AntigravityResult(
            text=text,
            model=model,
            session_id=sid,
            duration_ms=dur,
            usage=parsed_usage,
        )

    def create_stream_session(self) -> AntigravityStreamSession:
        """Create a persistent streaming session."""
        return AntigravityStreamSession(self)

    async def run_batch_stream(
        self, prompts: list[str], timeout: float = 300.0
    ) -> list[AntigravityResult]:
        """Run a batch of prompts through a persistent stream session."""
        session = self.create_stream_session()
        results = []
        try:
            await session.start()
            for p in prompts:
                res = await session.send(p, timeout=timeout)
                results.append(res)
        finally:
            await session.close()
        return results


class AntigravityQuotaClient:
    """Cached reader of Google Antigravity credits / quota utilization."""

    def __init__(self, provider: Optional[AntigravityProvider] = None):
        self.provider = provider
        self._cache: Optional[dict] = None
        self._cache_at = 0.0
        self._cache_ttl = 300.0
        self._lock = asyncio.Lock()

    def invalidate(self):
        """Invalidate cached quota snapshot."""
        self._cache = None
        self._cache_at = 0.0

    async def get_utilization(self) -> Optional[dict]:
        """Return {'credits': {'utilization': float, 'resets_at': str}} or None.

        When CLI quota output is unavailable or cannot be fetched, returns None
        so Brain.is_within_budget falls back cleanly to Harvey's daily call budget.
        """
        async with self._lock:
            now = time.monotonic()
            if self._cache is not None and now - self._cache_at < self._cache_ttl:
                return self._cache

            result = await self._fetch()
            self._cache = result
            self._cache_at = now
            return result

    async def _fetch(self) -> Optional[dict]:
        """Query the CLI for quota or credit utilization."""
        agy = self.provider.resolve_agy() if self.provider else shutil.which("agy")
        if not agy or not shutil.which(agy):
            return None

        for args in (
            ["quota", "--output-format", "json"],
            ["usage", "--output-format", "json"],
            ["status", "--json"],
        ):
            try:
                proc = await asyncio.create_subprocess_exec(
                    agy, *args,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
                if proc.returncode == 0:
                    raw = stdout.decode("utf-8", errors="replace").strip()
                    data = json.loads(raw)
                    parsed = self._parse_quota_payload(data)
                    if parsed:
                        return parsed
            except Exception as e:
                logger.debug(f"Antigravity quota command {args} failed: {e}")
                continue

        return None

    def _parse_quota_payload(self, data: dict) -> Optional[dict]:
        """Parse Antigravity quota or credit payload into normalized windows."""
        if not isinstance(data, dict):
            return None

        # Format 1: Explicit utilization percentage
        if "utilization" in data and isinstance(data["utilization"], (int, float)):
            return {
                "credits": {
                    "utilization": float(data["utilization"]),
                    "resets_at": str(data.get("resets_at") or data.get("resetsAt") or ""),
                }
            }

        # Format 2: Credit accounting (credits_used / total_credits)
        used = data.get("credits_used") or data.get("used_credits") or data.get("used")
        total = data.get("total_credits") or data.get("credits_limit") or data.get("total")
        if isinstance(used, (int, float)) and isinstance(total, (int, float)) and total > 0:
            utilization = (float(used) / float(total)) * 100.0
            return {
                "credits": {
                    "utilization": float(utilization),
                    "resets_at": str(data.get("resets_at") or data.get("resetsAt") or ""),
                }
            }

        # Format 3: Remaining credit balance
        balance = data.get("credit_balance") or data.get("remaining")
        if isinstance(balance, (int, float)) and isinstance(total, (int, float)) and total > 0:
            utilization = max(0.0, min(100.0, ((float(total) - float(balance)) / float(total)) * 100.0))
            return {
                "credits": {
                    "utilization": float(utilization),
                    "resets_at": str(data.get("resets_at") or data.get("resetsAt") or ""),
                }
            }

        # Format 4: Window dictionary
        windows = {}
        for key in ("credits", "five_hour", "seven_day", "daily", "monthly"):
            sub = data.get(key)
            if isinstance(sub, dict) and "utilization" in sub:
                windows[key] = {
                    "utilization": float(sub["utilization"]),
                    "resets_at": str(sub.get("resets_at") or sub.get("resetsAt") or ""),
                }
        return windows or None
