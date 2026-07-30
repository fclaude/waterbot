# CI/CD Pipeline Documentation

WaterBot CI runs on GitHub Actions and GitLab CI with the same quality gates.

## Stages

1. **Quality** - formatting, linting, mypy, Bandit, pip-audit
2. **Test** - unit tests on Python 3.11 and 3.12 with coverage
3. **Artifacts** - HTML coverage upload (GitHub)

## Quality gates

- All tests must pass
- Coverage ≥85%
- No lint/format errors
- mypy must pass
- Bandit and pip-audit must pass

## Local simulation

```bash
pip install -r requirements-dev.txt
make format-check
make lint
make type-check
make security-check
make test-cov-fail
```

Or:

```bash
make ci-check
```

## Notes

- `RPi.GPIO` is not installed in CI; hardware access is covered via emulation mocks.
- Codecov upload is best-effort and does not fail the build when the token is missing.
- There is no automatic PyPI publish job in the current pipeline.
