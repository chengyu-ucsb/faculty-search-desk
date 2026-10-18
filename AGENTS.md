# Repository maintenance rules for coding assistants

Before creating, copying, or editing GitHub Actions workflows:

1. **Verify current action releases**, runtime requirements, and runner compatibility against each action's official repository. Do not reuse remembered or template action versions blindly.
2. **Do not use actions that still target the deprecated Node.js 20 runtime.** As of October 2026, the verified Node.js 24-capable versions in use are `actions/checkout@v7`, `actions/setup-python@v7`, `actions/setup-node@v7`, `actions/configure-pages@v6`, `actions/upload-pages-artifact@v5`, and `actions/deploy-pages@v5`. Check for newer supported versions before writing workflows.
3. Treat GitHub Actions warnings as maintenance issues, even if a run is green. After changing a workflow, inspect the next actual run for errors, warnings, deployment status, and any unintended triggered jobs.
4. Keep `.github/dependabot.yml` enabled for weekly `github-actions` version-update proposals. Review and verify these updates rather than merging automatically.
5. Don't claim deployment or scheduled collection success based only on code changes; verify completed run status and relevant output artifacts.

This policy is stored in the repository so future assistants working on it can see and follow it. It does not override GitHub's documentation or substitute for checking current versions.
