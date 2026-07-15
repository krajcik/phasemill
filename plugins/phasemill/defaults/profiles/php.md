# PHP profile

- Respect the PHP version and Composer platform constraints. Preserve the project's `strict_types` policy and check nullable and union types, loose comparisons, numeric-string coercion, and `isset()` versus `array_key_exists()` at type boundaries.
- Preserve exception chains and domain exception contracts; catch `Throwable` only at intentional boundaries. Do not hide failures with `@`, empty catches, or silent fallback values.
- Complete transactions and clean up streams, temporary files, generators, and iterators on every path. Check closure captures, references left by `foreach`, and mutable static or global state that can leak across requests, workers, or tests.
- Validate request, CLI, file, and deserialized input at trust boundaries. Use parameterized database access, preserve authorization and context-appropriate output escaping, and treat unsafe deserialization or dynamic execution as security-sensitive.
- Keep `composer.json`, `composer.lock`, platform requirements, autoload mappings, and the repository's vendor workflow consistent. Change dependencies or Composer scripts only when required and validated.
- Preserve public APIs and named-argument compatibility, serialized payloads, schemas, routes, configuration, observability, errors, status codes, and framework-visible behavior unless the requirement changes them.
- Use the repository's existing test runner and conventions. Prefer behavior-focused regression tests covering success, exceptions, authorization, transactions, cleanup, and boundary values; do not require PHPUnit, Pest, or a mocking library without project evidence.
