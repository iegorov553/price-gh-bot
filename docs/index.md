# Documentation Overview

This site helps operators, contributors, and security reviewers run and evolve Price GH Bot. The content is organised by role so you can jump straight to the guidance you need.

## Quick Navigation
- **Architecture**:  
  - `architecture/overview.md` summarises the high-level design and guiding principles.  
  - `architecture/components.md` details each module and how dependencies are wired.  
  - `architecture/data_flow.md` walks through the end-to-end request pipeline.
- **Setup**:  
  - `setup/environment.md` covers local requirements, Docker images, and Playwright provisioning.  
  - `setup/configuration.md` documents environment variables, config files, and secrets handling.
- **Development**:  
  - `development/workflow.md` describes branching, quality gates, and pre-commit usage.  
  - `development/coding_guidelines.md` lists style rules, modularity expectations, and refactoring triggers.  
  - `development/dependency_management.md` explains how Poetry locks, updates, and audits dependencies.
- **Testing**:  
  - `testing/strategy.md` explains the multi-tier testing approach.  
  - `testing/how_to.md` provides command-by-command instructions for running the suite locally or in Docker.
- **Operations**:  
  - `operations/monitoring.md` outlines analytics, logging, and health checks.  
  - `operations/troubleshooting.md` captures the most common production incidents and their fixes.
- **Security**:  
  - `security/practices.md` lists hardening guidelines for tokens, infrastructure, and data.  
  - `security/auditing.md` explains how to run automated security scans and interpret the results.
- **Roadmap & Contributions**:  
  - `roadmap.md` tracks planned improvements and known risks.  
  - `CONTRIBUTING.md` sets expectations for new pull requests and code reviews.

## Getting Started
If you are deploying the bot for the first time, read:
1. `README.md` (project root) for a deployment-focused overview.  
2. `setup/environment.md` to prepare your machine or container image.  
3. `setup/configuration.md` to provide secrets and feature flags.

Contributors should also review:
1. `development/workflow.md` for day-to-day routines.  
2. `development/coding_guidelines.md` before proposing significant changes.  
3. `testing/how_to.md` to ensure every change ships with automated tests.

Security auditors can begin with:
1. `security/practices.md` for current safeguards.  
2. `security/auditing.md` to run Bandit, pip-audit, and complementary tooling.  
3. `roadmap.md` for upcoming mitigations.

The documentation is versioned alongside the codebase. Update the relevant section whenever you introduce new capabilities, change the architecture, or modify operational procedures.
