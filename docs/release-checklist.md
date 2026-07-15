# Release checklist

1. Confirm the working tree is clean and the manifest, MCP server, changelog,
   and release tag use the same semantic version.
2. Run the manifest validator, all `tests/test-codex-*.py` files, Python
   compilation, and the installed-package smoke.
3. Push the source branch and require green GitHub CI at the release commit.
4. Create an annotated `vX.Y.Z` tag and GitHub Release from that exact commit.
5. Clone the tag into a clean temporary directory and run the installed-package
   smoke from the clone.
6. Add the GitHub marketplace by `owner/repo --ref vX.Y.Z`, install the plugin
   in a clean Codex home, and verify discovery in a new task.
7. Confirm the release notes, Privacy Policy, Terms, Support, Security Policy,
   and submission test cases match actual behavior.
