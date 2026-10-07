# Contributing

Use the [README](README.md#quick-start) to set up the backend and frontend. Install `backend/requirements-langchain.txt` for the full backend test suite. Tests use fixtures and do not require an API key.

Before opening a pull request, run:

```sh
(cd backend && ../.venv/bin/python -m pytest -q)
(cd frontend && npm test && npm run build)
```

Preserve recorded-run compatibility and keep replay independent of execution. Add focused tests when changing event validation, context isolation, or state transitions. Describe the behavior change and how you verified it in the pull request.

Do not commit `.env` files, credentials, generated recordings, or private prompt/tool data. Use `backend/.env.example` for configuration names with empty values. Review screenshots and sample traces before sharing them.
