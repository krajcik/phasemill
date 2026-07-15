#!/usr/bin/env python3
"""Run an independent Pi code review with a strict read-only CLI contract."""

from __future__ import annotations

import argparse
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence, TextIO


PI_MODEL = "zai/glm-5.2"
PI_THINKING = "xhigh"
READ_ONLY_TOOLS = "read,grep,find,ls"
PROXY_ENV_KEYS = (
    "ALL_PROXY",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "all_proxy",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)
PI_ARGS = (
    "--mode",
    "json",
    "--model",
    PI_MODEL,
    "--thinking",
    PI_THINKING,
    "--no-session",
    "--no-approve",
    "--no-extensions",
    "--no-skills",
    "--no-prompt-templates",
    "--no-context-files",
    "--tools",
    READ_ONLY_TOOLS,
)


@dataclass(frozen=True)
class PiReviewResult:
    status: str
    reason: str
    review: str = ""
    provider: str = ""
    model: str = ""
    elapsed_seconds: float = 0
    turn_count: int = 0
    tool_call_count: int = 0
    current_tool: str = ""
    last_event: str = ""
    partial_review: str = ""


class PiEventStream:
    """Incrementally validate Pi JSONL and retain review diagnostics."""

    def __init__(self) -> None:
        self.line_number = 0
        self.final_message: dict[str, Any] | None = None
        self.last_event = ""
        self.turn_count = 0
        self.tool_call_count = 0
        self.active_tools: dict[str, str] = {}
        self.partial_text: list[str] = []

    @property
    def current_tool(self) -> str:
        return ", ".join(dict.fromkeys(self.active_tools.values()))

    @property
    def partial_review(self) -> str:
        return "".join(self.partial_text).strip()

    def feed(self, raw_line: str) -> str | None:
        self.line_number += 1
        if not raw_line.strip():
            return None
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            return f"Pi emitted malformed JSON on line {self.line_number}"
        if not isinstance(event, dict):
            return f"Pi emitted a non-object event on line {self.line_number}"

        event_type = event.get("type")
        self.last_event = event_type if isinstance(event_type, str) else "unknown"
        if event_type == "turn_start":
            self.turn_count += 1
        elif event_type == "tool_execution_start":
            self.tool_call_count += 1
            call_id = event.get("toolCallId")
            tool_name = event.get("toolName")
            if isinstance(call_id, str) and isinstance(tool_name, str):
                self.active_tools[call_id] = tool_name
        elif event_type == "tool_execution_end":
            call_id = event.get("toolCallId")
            if isinstance(call_id, str):
                self.active_tools.pop(call_id, None)
        elif event_type == "message_update":
            update = event.get("assistantMessageEvent")
            if isinstance(update, dict) and update.get("type") == "text_delta":
                delta = update.get("delta")
                if isinstance(delta, str):
                    self.partial_text.append(delta)

        message = event.get("message")
        if event_type == "message_end" and isinstance(message, dict) and message.get("role") == "assistant":
            self.final_message = message
        return None

    def result(self, required: bool, *, elapsed_seconds: float = 0) -> PiReviewResult:
        diagnostics = _diagnostics(self, elapsed_seconds)
        if self.final_message is None:
            return failure(required, "Pi returned no final assistant message", **diagnostics)
        stop_reason = self.final_message.get("stopReason")
        if stop_reason != "stop":
            return failure(
                required,
                f"Pi review did not complete cleanly (stopReason={stop_reason!r})",
                **diagnostics,
            )

        content = self.final_message.get("content")
        if not isinstance(content, list):
            return failure(required, "Pi final assistant message has invalid content", **diagnostics)
        review = "\n".join(
            item["text"]
            for item in content
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)
        ).strip()
        if not review:
            return failure(required, "Pi returned an empty review", **diagnostics)

        provider = self.final_message.get("provider")
        model = self.final_message.get("model")
        return PiReviewResult(
            status="ok",
            reason="completed",
            review=review,
            provider=provider if isinstance(provider, str) else "",
            model=model if isinstance(model, str) else "",
            elapsed_seconds=diagnostics["elapsed_seconds"],
            turn_count=self.turn_count,
            tool_call_count=self.tool_call_count,
            last_event=self.last_event,
        )


def build_command(command: Sequence[str]) -> list[str]:
    if not command or not all(isinstance(part, str) and part for part in command):
        raise ValueError("Pi command must be a non-empty argv list")
    return [*command, *PI_ARGS]


def failure(required: bool, reason: str, **diagnostics: Any) -> PiReviewResult:
    return PiReviewResult(status="error" if required else "skipped", reason=reason, **diagnostics)


def _diagnostics(stream: PiEventStream, elapsed_seconds: float) -> dict[str, Any]:
    return {
        "elapsed_seconds": round(elapsed_seconds, 3),
        "turn_count": stream.turn_count,
        "tool_call_count": stream.tool_call_count,
        "current_tool": stream.current_tool,
        "last_event": stream.last_event,
        "partial_review": stream.partial_review,
    }


def direct_environment() -> dict[str, str]:
    env = os.environ.copy()
    # Empty values force a direct connection and prevent Pi's global httpProxy
    # setting from filling HTTP_PROXY/HTTPS_PROXY via nullish assignment.
    for key in PROXY_ENV_KEYS:
        env[key] = ""
    env["PI_SKIP_VERSION_CHECK"] = "1"
    return env


def parse_pi_events(output: str, required: bool) -> PiReviewResult:
    stream = PiEventStream()
    for raw_line in output.splitlines():
        if error := stream.feed(raw_line):
            return failure(required, error, **_diagnostics(stream, 0))
    return stream.result(required)


def _read_lines(pipe: TextIO, output: queue.Queue[tuple[str, str]]) -> None:
    try:
        for line in pipe:
            output.put(("line", line))
    finally:
        output.put(("eof", ""))


def _drain_stderr(pipe: TextIO) -> None:
    for _line in pipe:
        pass


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:  # pragma: no cover - Windows compatibility
            process.terminate()
        process.wait(timeout=1)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:  # pragma: no cover - Windows compatibility
                    process.kill()
            except ProcessLookupError:
                pass
            process.wait()


def _close_process_pipes(process: subprocess.Popen[str], threads: Sequence[threading.Thread]) -> None:
    for thread in threads:
        thread.join(timeout=1)
    for pipe in (process.stdin, process.stdout, process.stderr):
        if pipe is not None and not pipe.closed:
            pipe.close()


def _timeout_result(
    required: bool,
    kind: str,
    limit: float,
    elapsed: float,
    stream: PiEventStream,
) -> PiReviewResult:
    diagnostics = _diagnostics(stream, elapsed)
    current_tool = diagnostics["current_tool"] or "none"
    last_event = diagnostics["last_event"] or "none"
    reason = (
        f"Pi review {kind} timeout after {limit:g}s "
        f"(elapsed={elapsed:.1f}s, turns={stream.turn_count}, "
        f"tool_calls={stream.tool_call_count}, current_tool={current_tool}, "
        f"last_event={last_event})"
    )
    return failure(required, reason, **diagnostics)


def run_pi_review(
    prompt: str,
    *,
    cwd: Path,
    command: Sequence[str] = ("pi",),
    timeout_seconds: float = 900,
    idle_timeout_seconds: float = 120,
    required: bool = False,
) -> PiReviewResult:
    if not prompt.strip():
        return failure(required, "review prompt is empty")
    if timeout_seconds <= 0:
        return failure(required, "Pi wall timeout must be greater than zero")
    if idle_timeout_seconds <= 0:
        return failure(required, "Pi idle timeout must be greater than zero")
    if idle_timeout_seconds >= timeout_seconds:
        return failure(required, "Pi idle timeout must be less than wall timeout")
    if not cwd.is_dir():
        return failure(required, f"review working directory does not exist: {cwd}")

    try:
        argv = build_command(command)
    except ValueError as exc:
        return failure(required, str(exc))

    started = time.monotonic()
    try:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=direct_environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=os.name == "posix",
        )
    except FileNotFoundError:
        return failure(required, f"Pi executable not found: {command[0]}")
    except OSError as exc:
        return failure(required, f"failed to start Pi: {exc.strerror or exc.__class__.__name__}")

    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    events: queue.Queue[tuple[str, str]] = queue.Queue()
    stdout_thread = threading.Thread(target=_read_lines, args=(process.stdout, events), daemon=True)
    stderr_thread = threading.Thread(target=_drain_stderr, args=(process.stderr,), daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    try:
        process.stdin.write(prompt)
        process.stdin.close()
    except (BrokenPipeError, OSError):
        pass

    stream = PiEventStream()
    last_event_at = started
    stdout_eof = False
    while not (stdout_eof and process.poll() is not None):
        now = time.monotonic()
        elapsed = now - started
        if elapsed >= timeout_seconds:
            _stop_process(process)
            _close_process_pipes(process, (stdout_thread, stderr_thread))
            return _timeout_result(required, "wall", timeout_seconds, elapsed, stream)
        idle_elapsed = now - last_event_at
        if idle_elapsed >= idle_timeout_seconds:
            _stop_process(process)
            _close_process_pipes(process, (stdout_thread, stderr_thread))
            return _timeout_result(required, "idle", idle_timeout_seconds, elapsed, stream)

        wait_for = min(timeout_seconds - elapsed, idle_timeout_seconds - idle_elapsed, 0.1)
        try:
            item_type, payload = events.get(timeout=max(wait_for, 0.001))
        except queue.Empty:
            continue
        if item_type == "eof":
            stdout_eof = True
            continue
        if error := stream.feed(payload):
            _stop_process(process)
            _close_process_pipes(process, (stdout_thread, stderr_thread))
            return failure(required, error, **_diagnostics(stream, time.monotonic() - started))
        if payload.strip():
            last_event_at = time.monotonic()

    elapsed = time.monotonic() - started
    _close_process_pipes(process, (stdout_thread, stderr_thread))
    if process.returncode != 0:
        return failure(
            required,
            f"Pi exited with code {process.returncode}",
            **_diagnostics(stream, elapsed),
        )
    return stream.result(required, elapsed_seconds=elapsed)


def parse_command_json(raw: str) -> list[str]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid command JSON: {exc.msg}") from exc
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise argparse.ArgumentTypeError("command JSON must be a non-empty array of non-empty strings")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--command-json", type=parse_command_json, default=["pi"])
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument("--idle-timeout-seconds", type=float, default=120)
    parser.add_argument("--required", action="store_true")
    args = parser.parse_args()

    result = run_pi_review(
        sys.stdin.read(),
        cwd=args.cwd,
        command=args.command_json,
        timeout_seconds=args.timeout_seconds,
        idle_timeout_seconds=args.idle_timeout_seconds,
        required=args.required,
    )
    print(json.dumps(asdict(result), ensure_ascii=False))
    return 1 if result.status == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
