# MonitorAI V2.2 Codex team

Use `PROJECT_REQUIREMENTS.md` for product scope. Make product changes in the
consolidated MonitorAI V2.2 project. Treat older MonitorAI and Azure Architect
Companion as read-only references.

## Ownership

- Main Codex coordinates the work, assigns owners, and integrates findings and changes.
- Full-Stack Developer owns application implementation.
- DevOps Engineer owns CI/CD and deployment.
- Network Manager owns network design and connectivity.
- Compliance Officer evaluates HIPAA, SOC 2, and ISO control requirements.
- IT Infrastructure Manager owns infrastructure operations and governance.
  See `.codex/agents/it-infrastructure-manager.toml`.
- Cybersecurity Specialist owns defensive security reviews.
  See `.codex/agents/cybersecurity-specialist.toml`.
- Ethical Hacker supports authorized, human-led offensive security validation
  through defensive review, evidence assessment, and remediation verification.
  See `.codex/agents/ethical-hacker.toml`.

## Coordination

Use only the specialists relevant to the task. Assign one primary implementation
agent and use specialists for targeted reviews. Limit concurrency to three
subagents. Share the relevant paths and existing findings with reviewers so
they can avoid duplicate repository scans and repeated reports. Return concise
findings with exact file paths.

Obtain explicit approval before starting product development. Obtain explicit
approval and scope before any human-led active security testing. Limit that
testing to authorized development or staging environments.
