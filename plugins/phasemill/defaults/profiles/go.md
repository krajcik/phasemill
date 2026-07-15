# Go profile

- Check context propagation and cancellation, goroutine lifecycle, channel ownership, cleanup, races, and error wrapping. Preserve sentinel error chains with `%w` when callers use `errors.Is` or `errors.As`, and avoid duplicate log-and-return handling.
- Ensure database rows and HTTP response bodies are closed, check `rows.Err()`, and avoid `defer` inside potentially unbounded loops when cleanup would be delayed.
- Give external HTTP calls a bounded lifetime through an `http.Client` timeout or an explicit request-context deadline, and propagate the caller's context into requests.
- Check nil maps and pointers, typed nil interfaces, nil channels, unsafe numeric conversions, and unintended slice or map aliasing and mutation.
- Prefer behavior-focused table tests where they stay readable, and run the narrowest relevant `go test` before broader packages.
- Keep `go.mod`, `go.sum`, `go.work`, and vendored module metadata consistent with the repository workflow.
- Preserve package boundaries, public HTTP and API contracts, accepted status codes, storage formats, metrics, logs, errors, protocols, and the repository's established tracing, retry, and dependency conventions.
