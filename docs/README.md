# Project documentation

This folder records the conventions and technical choices that guide development. Add a short decision document here when a project-wide choice needs context, rationale, or instructions for future contributors.

## Technical decisions

- [Project architecture](architecture.md): package responsibilities, data flow, and dependency boundaries.
- [Initial data model](data-model.md): the minimal `orders` table and design questions still open.
- [Synthetic CSV generation](data-generation.md): generator choice, row contract, defect profile, and command usage.
- [CSV ingestion](data-ingestion.md): chunked reading, row validation, duplicate handling, and SQLite writes.
- [Commit conventions](technical-decisions/commit-conventions.md): commit message structure and examples.
- [Pre-commit hooks](technical-decisions/pre-commit-hooks.md): the configured checks, their responsibilities, and how to run them.
