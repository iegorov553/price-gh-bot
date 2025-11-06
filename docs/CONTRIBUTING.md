# Contributing Guide

Thank you for considering a contribution to Price GH Bot. This document outlines expectations for issues, pull requests, and reviews.

## Getting Started
- Fork the repository or create a branch from `staging`.  
- Read `README.md` to understand deployment workflows.  
- Review `docs/development/workflow.md` and `docs/development/coding_guidelines.md` for style and process requirements.  
- Ensure you can run the full QA suite locally before proposing changes.

## Filing Issues
- Provide a clear summary, reproduction steps, expected vs actual behaviour, and environment details.  
- For scraping issues, include anonymised URLs and logs showing failures.  
- Tag issues with appropriate labels (bug, enhancement, security, documentation).  
- Reference related roadmap items if the issue aligns with long-term goals.

## Pull Requests
- Describe the problem and the chosen solution.  
- List tests executed (`pytest`, `ruff`, `mypy`, `bandit`, `pip-audit`, `pre-commit`).  
- Update documentation (`README.md`, `docs/`) to reflect changes.  
- Mention any follow-up tasks (e.g., additional tests needed, future refactors).  
- Keep commits focused and rebased on top of the latest `staging`.

## Code Review
- Respond to feedback promptly and respectfully.  
- Address requested changes or discuss alternatives when necessary.  
- Ensure reviewers have enough context (design decisions, trade-offs) to evaluate the change.  
- Do not merge until CI passes and at least one maintainer approves.

## Testing Requirements
- New or modified functionality must be covered by automated tests in `tests_new/`.  
- If a component lacks tests, propose coverage additions or create an issue to track the gap.  
- For complex logic, include integration or E2E tests alongside unit tests.

## Documentation
- Keep project documentation in English.  
- Update runbooks, configuration references, and architecture docs whenever you touch those areas.  
- Summarise notable changes in the pull request description for quick reference.

## Code of Conduct
- Be respectful, professional, and collaborative.  
- Report unacceptable behaviour to project maintainers.

We appreciate every contribution and strive to make collaboration transparent and predictable.
