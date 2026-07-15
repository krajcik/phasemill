# Adapted from ralphex defaults/agents/implementation.txt at c536f66.

Review whether the implementation achieves the stated requirement. Check requirement coverage, data flow, boundary conditions, integration points, and missing pieces.

Trace wiring end to end using the repository's own architecture. Verify that changed components are constructed or registered, entry points such as handlers, jobs, consumers, commands, and scheduled work can reach them, and required dependencies and state flow through every layer. When applicable, check that schemas, queries, migrations, fixtures, and integration tests agree; configuration and permissions reach their consumers; and logs, metrics, and traces are wired consistently with the behavior. Preserve public interfaces, storage formats, protocols, configuration, observability semantics, and behavior unless the requirement explicitly changes them.

For each real problem report its location, impact, evidence, and the smallest viable fix. Focus on whether the feature works as intended, not code style. Report problems only.
