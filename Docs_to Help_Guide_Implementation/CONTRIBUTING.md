# Contributing

Thank you for contributing to the DFFRNT Air-Gapped AI Assistant project. This document gives new contributors and teammates a clear onboarding path: what has been done, how we work, and how to propose or make changes.

- **Communication**: Use the project channel (Slack/email) for design discussions and scheduling. For code-level changes, open a PR with a clear descriptive title, summary, and linked issue.
- **Branching**: Use feature branches: `feature/<short-desc>`. Keep `main` stable.
- **Code style**: Follow existing repository style. Use `black` and `ruff` if installed. Run linters locally before opening a PR.
- **Commit messages**: Use short imperative subject lines and an optional body. Example: `feat: add PDF ingestion CLI`.
- **Reviews & approvals**: Request at least one code review. Address review comments and squash/fixup commits as requested.
- **Testing**: Add or update tests for new behavior. Run `pytest` locally and ensure tests pass.
- **Issues**: Create issues that include reproduction steps, expected behavior, and environment notes.

Meeting cadence and responsibilities
- Bi-weekly progress demos (as requested by sponsors). 
- Assign an owner for each feature in `ROADMAP.md`.

Onboarding checklist for new teammates
1. Clone the repo. 2. Create and activate the project venv. 3. Install dependencies. 4. Run the example extractor script. 5. Read `ARCHITECTURE.md` and `RUNNING.md`.

If you have questions, ask the project manager or the technical advisor listed in the presentation.