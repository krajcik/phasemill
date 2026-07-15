# Python profile

- Respect the declared Python version and platform constraints; do not introduce unsupported syntax, standard-library APIs, metadata, or dependency versions.
- Preserve exception causes with `raise ... from ...`; catch narrow exceptions at intentional boundaries and avoid bare catches, silent fallbacks, or duplicate log-and-reraise handling. Use context managers or explicit cleanup for files, sockets, cursors, temporary resources, and locks.
- Check coroutine and task lifecycle, cancellation and timeout propagation, awaited results, background-task ownership, blocking work in async code, and async context-manager cleanup.
- Check mutable argument and dataclass defaults, late-bound closures, shared class state, iterator reuse, truthiness versus `None`, path handling, and mutation or aliasing of caller-owned collections. Keep runtime behavior, annotations, nullable returns, decorators, and public signatures consistent without imposing a type checker.
- Validate request, CLI, file, and deserialized input at trust boundaries. Use parameterized database access and safe subprocess arguments; preserve authorization and output escaping; treat `pickle`, unsafe YAML loading, dynamic imports, `eval`, and shell execution as security-sensitive.
- Keep `pyproject.toml`, supported-version metadata, lock or requirements files, extras, entry points, and the repository's environment and dependency-manager workflow consistent. Do not switch packaging, formatting, linting, or test tools merely to satisfy this profile.
- Preserve public APIs, serialized payloads, schemas, CLI behavior, configuration, observability, errors, and status codes unless the requirement changes them.
- Use the repository's existing test runner. Prefer behavior-focused regression tests covering success, malformed input, exceptions, cancellation, cleanup, and boundaries; do not require pytest, unittest, or a mocking library without project evidence.
