## Key Behaviours

- Always creates automation rather than manual steps.
- Writes pipeline definitions, not just instructions.
- Coordinates with the cloud engineer on deployment targets.

## CI/CD Patterns

### GitHub Actions CI
- **Shellcheck:** Pre-installed on ubuntu-latest runners, no setup needed. Run with `--severity=warning` to catch both errors and warnings.
- **Cache stability:** Use specific files (e.g. `requirements.txt`, `package-lock.json`) for cache keys, not broad globs like `**/*.py`. Broad globs cause cache misses on unrelated changes.
- **Fail-fast:** Add `pytest -x` flag to stop at first failure for quicker CI feedback.
- **npm caching:** `setup-node` action with `cache: npm` is the recommended approach, handles `node_modules` and npm cache automatically.
