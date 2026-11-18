# Pre-commit hooks

- **Status:** Accepted
- **Configuration:** [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml)
- **Decision:** Run inexpensive quality, formatting, and secret checks before commits.

## Hook responsibilities

| Hook | Purpose |
| --- | --- |
| `trailing-whitespace`, `end-of-file-fixer` | Keep text files consistently formatted. |
| `check-yaml`, `check-toml` | Catch malformed YAML and TOML configuration. |
| `check-merge-conflict`, `check-case-conflict` | Catch unresolved conflict markers and paths that differ only by case. |
| `debug-statements` | Prevent Python debugging statements from being committed. |
| `detect-private-key` | Catch private key material in added files. |
| `check-added-large-files` | Flag newly added files larger than 5,000 KB, reducing the chance of committing bulky data or artifacts. |
| `ruff` | Lint Python and apply safe autofixes. It uses Ruff's default lint rules; import sorting is delegated to isort. |
| `isort` | Sort imports using the Black profile and an 88-character line length. |
| `black` | Format Python with the same 88-character line length. |
| `gitleaks` | Detect likely credentials and other secrets in commit changes. |
| `ty` | Type-check the project. The hook checks the whole project because a change in one module can affect another. |

## Formatting and execution order

Ruff is configured for linting and autofixes, not formatting. isort owns import ordering; Black owns code formatting. Both use an 88-character line length, and isort's `black` profile keeps multiline imports compatible with Black. The hooks run in the order listed in the configuration: Ruff, isort, then Black.

If a hook changes a file, review the change and stage it before committing. Run the hooks again to confirm the staged files pass.

## Running the checks

Install the Git hook once:

```bash
uv run pre-commit install
```

Run checks on all tracked files:

```bash
uv run pre-commit run --all-files
```

Pre-commit creates its hook environments on first run. The ty hook uses `uv` and checks the project as a whole.

## Sensitive data

Gitleaks and the private-key check reduce the chance of committing credentials. The large-file check helps prevent accidental inclusion of data dumps. These checks are safeguards, not a guarantee that every sensitive value or dataset will be detected; review files before staging and keep secrets outside the repository.
