# Commit conventions

- **Status:** Accepted
- **Decision:** Use Conventional Commits with small, focused commits.

## Format

```text
<type>(<optional scope>): <short description>
```

Use a lowercase type and an imperative description without a trailing period. Keep the subject concise and describe the user-visible or technical change. The scope is optional and names the affected area.

## Types

| Type | Use it for |
| --- | --- |
| `feat` | A new capability |
| `fix` | A bug fix |
| `docs` | Documentation changes |
| `style` | Formatting-only changes |
| `refactor` | Code changes that do not add features or fix bugs |
| `test` | Adding or changing tests |
| `build` | Packaging, dependencies, or build configuration |
| `ci` | Continuous integration configuration |
| `chore` | Maintenance that does not fit another type |

## Examples

```text
feat(api): add the natural-language question endpoint
fix(cleaning): discard rows with malformed dates
docs: document the pre-commit checks
test(validation): reject write queries
build: add FastAPI dependency
```

Make commits as work progresses. Each commit should capture one coherent change so the project history shows how the implementation developed.
