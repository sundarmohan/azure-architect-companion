MonitorAI V2.2 — Updated product requirements
1. Product vision
Build a centralized, multi-client Azure Infrastructure Management and Cybersecurity Platform.

The application should function as an intelligent:
- Infrastructure Manager
- Cloud Architect
- Network Manager
- Cybersecurity Specialist
- Ethical Security Assessment Platform
- Compliance Officer
- DevOps / DevSecOps Manager
The platform must collect, monitor, analyze, detect, assess, alert, recommend, report and track.

Intelligence approach: Deterministic rules, thresholds, statistical baselines, event correlation, evidence-based risk scoring and recommendations. No external generative AI API dependency.

Initial operating boundary: Read-only infrastructure management and advisory workflows. No automatic remediation or infrastructure deployment.
2. Product modules
#	Module	Functional requirements
1	Overview Dashboard	Consolidated client health, security, compliance, incidents and risks
2	Architecture Designer	Design, edit, duplicate, version, validate, approve and manage architecture
3	Azure Cloud Management	Connections, subscriptions, resource discovery and inventory
4	Infrastructure Monitoring	Availability, performance, metrics, capacity and health
5	Network Intelligence	Network topology, traffic, DNS, routing, NSG, firewall and exposure
6	Cybersecurity Engine	Security posture, misconfigurations, threats, IAM and exposure
7	Ethical Hacking Engine	Authorized security assessments and penetration-testing workflows
8	Vulnerability Management	Scanner findings, prioritization, remediation and retesting
9	Threat Detection	Suspicious activity, event correlation and investigation
10	DevSecOps	Repository, dependency, container and CI/CD security
11	Compliance Engine	HIPAA, SOC 2, ISO 27001 and PCI DSS
12	Alerts & Incidents	Alert management, investigations, RCA and notifications
13	Cost Management	Azure cost analysis, budgets and optimization
14	Backup & DR	Backup monitoring, recovery readiness and restore evidence
15	Reports	Technical, security, compliance and executive reports
16	Administration	Clients, users, RBAC, integrations, policies and settings

3. Architecture Designer — detailed requirements
This is a complete architecture management module, not just a visual drawing tool.
- Create, edit, duplicate, archive and delete designs.
- Organize designs by client, project and environment.
- Azure resource catalog with categories and resource-specific properties.
- Drag and drop resources onto the canvas.
- Configure resource properties through structured panels.
- Create relationships and dependencies between resources.
- Save and reopen designs.
- Maintain version history and revision descriptions.
- Compare revisions and restore earlier versions.
- Validate configurations and relationships.
- Display actionable design findings.
- Estimate Azure costs with assumptions.
- Generate Terraform for supported Azure resources.
- Export Ansible playbooks for reusable OS and application baseline configuration
  on IT-managed hosts. The initial export supports declared packages and service
  state, with an inventory group to map to approved hosts outside MonitorAI.
- Terraform describes Azure infrastructure. Ansible describes host configuration.
  Exports include assumptions and coverage limits. MonitorAI does not execute
  these artifacts or store host login credentials for them.
- Export architecture diagrams and definitions.
- Maintain approval and revision history.
Design lifecycle:
Draft


In Review


Approved


Archived



Approval records must never trigger infrastructure deployment.

4. Cybersecurity Engine
Dedicated core module
This module continuously evaluates the security posture of connected Azure environments.
Capability	Requirements
CSPM	Azure security posture and configuration assessment
Attack surface	Public IPs, exposed resources and services
Network security	NSG, firewall, WAF and routing analysis
Identity security	Privileged access, excessive permissions and stale assignments
Data security	Storage, database, encryption and data protection checks
Secrets security	Key Vault configuration and secret exposure indicators
Vulnerabilities	Azure and integrated scanner findings
Patch security	Supported OS and infrastructure patch posture
Threat monitoring	Azure security alerts and suspicious activity
Security score	Explainable security posture and risk scoring
Remediation tracking	Findings, owners, due dates and status
Reporting	Security dashboards and assessment reports

Integrations should include Azure Defender for Cloud where authorized, Azure Activity Logs, Azure Monitor and approved vulnerability scanners.

The engine must show the evidence and source behind each finding.
5. Ethical Hacking Engine
Dedicated core module
This is an application feature, separate from the Codex Ethical Hacker agent.

Required capabilities:
1. Create an authorized security assessment.
2. Select client, environment, applications, endpoints and approved IP ranges.
3. Record authorization, scope, exclusions and testing window.
4. Discover the approved attack surface.
5. Perform passive reconnaissance and configuration reviews.
6. Assess exposed ports and services.
7. Perform approved vulnerability scanning.
8. Support web application and API security assessment integrations.
9. Assess network security and access-control weaknesses.
10. Import findings from approved security tools.
11. Capture evidence, timestamps, tool versions and methodology.
12. Classify findings by severity and risk.
13. Track remediation and retesting.
14. Generate technical and executive security assessment reports.
Assessment finding lifecycle:
1
Open


2
Confirmed


3
In Remediation


4
Ready for Retest


5
Closed


Safety requirements:
- Default to passive, non-destructive testing.
- Require explicit authorization before active testing.
- Enforce approved targets and assessment windows.
- No denial-of-service, destructive testing, data exfiltration or unauthorized exploitation.
- No automatic exploitation or remediation.
- Production testing requires separate explicit authorization.
6. Vulnerability and Threat Intelligence
- Consolidate vulnerability findings from Azure and integrated scanners.
- Deduplicate repeated findings.
- Prioritize based on severity, exploitability, exposure and business impact.
- Track vulnerability age and remediation SLA.
- Maintain risk acceptance records.
- Correlate suspicious events and security alerts.
- Create incidents from significant findings.
- Maintain investigation timelines and evidence.
- Generate incident reports and RCA.
- Track corrective and preventive actions.
7. DevSecOps Engine
- GitHub repository monitoring.
- Dependency vulnerability scanning.
- Container image security scanning.
- Dockerfile security checks.
- Infrastructure-as-code security validation.
- Secret detection.
- CI/CD pipeline monitoring.
- Release risk assessment.
- Security findings associated with repositories, commits, images and deployments.
The application must monitor these workflows, not execute customer deployments.
8. Compliance Engine
Initial frameworks:
- HIPAA
- SOC 2
- ISO 27001
- PCI DSS
Capabilities:
- Technical control assessment.
- Automated Azure evidence collection.
- Control-level Pass, Fail, Review Required, Not Applicable and Unable to Validate statuses.
- Evidence storage and traceability.
- Manual review requirements.
- Compliance gap identification.
- Corrective action tracking.
- Assessment history and audit trail.
- Framework-level and consolidated reports.
The platform must not claim certification based solely on automated checks.
9. Other operational modules
Infrastructure Monitoring

- Resource health, metrics, availability, capacity and service status.

Network Intelligence

- Azure network inventory, topology, routing, NSGs, firewalls, traffic analysis and exposure.

Cost Management

- Resource costs, budgets, cost anomalies and optimization recommendations.

Backup & DR

- Backup configuration, job status, retention, RPO/RTO, restore testing and recovery readiness.

Alerts & Incidents

- Configurable alerts, acknowledgement, assignment, escalation, resolution, timeline and RCA.

Reports

- Client reports, infrastructure reports, security reports, penetration-testing reports, compliance reports and executive summaries.
10. Authentication and client management
- Local username/password authentication only.
- No Microsoft Entra ID application login integration.
- Secure password hashing and password reset.
- Platform administrator and client administrators.
- Multiple client organizations.
- User membership and configurable RBAC.
- Client-level data isolation.
- Secure cloud credential storage.
- Audit logs for sensitive operations.
- Backend authorization on every protected API.
11. Cloud scope
Initial release: Azure only
Provider	Initial release
Microsoft Azure	Full implementation
AWS	Deferred
GCP	Deferred

We should complete and manually validate all applicable Azure capabilities before starting AWS or GCP.
12. Delivery phases
Phase	Development scope
0	Repository and architecture preparation
1	Local authentication, clients, RBAC and application foundation
2	Azure architecture designer, connections, resource inventory, and Terraform/Ansible exports
3	Client-scoped Azure infrastructure monitoring and network intelligence
4	Cybersecurity and threat detection
5	Ethical hacking and vulnerability management
6	Compliance and evidence management
7	DevSecOps, incidents and RCA
8	Cost, backup/DR and operational intelligence
9	Reports and complete functional validation
10	Repository cleanup, Docker finalization and first EC2 deployment

Phase 3 delivery and verification:
- Use the client's existing Azure connection and latest complete inventory.
- Collect Azure Resource Health and supported Azure Monitor performance,
  capacity and traffic metrics. Report missing data, permission failures,
  resource coverage limits and last successful collection.
- Correlate inventoried network resources, topology links, DNS, routes, NSGs,
  firewalls and explicit exposure indicators using read-only Azure APIs.
- Allow client administrators to opt in to per-subscription polling. Keep
  all observations and schedules scoped to that client and subscription.
- Azure Monitor counters provide aggregate traffic evidence. Flow-level traffic
  attribution and effective reachability need separate Azure data sources.
- Add on-demand Advanced Diagnostics from resource-scoped Azure Monitor
  Logs using fixed KQL summaries for Azure Activity, resource diagnostics,
  App Service HTTP, Application Insights exceptions, and guest OS events.
  Use inventoried resources, bounded time ranges, Azure read permissions,
  and aggregates. Keep CLI, PowerShell, SSH, and Kudu execution outside
  the application. Report unavailable or partial sources separately.
- Verify isolation, permission checks, snapshot retention, scheduling, and
  the frontend build through GitHub Actions.

Phase 4 delivery and verification:
- Read Defender for Cloud findings and active alerts where authorized and
  summarize selected Azure Activity changes as review signals.
- Evaluate explicit configuration evidence for network exposure, storage
  access and TLS, Key Vault settings, Azure SQL encryption and direct
  privileged subscription roles. Distinguish configuration from reachability.
- Show an explainable risk score, findings, evidence, source limitations,
  recommendations, and client-scoped remediation tracking.
- Administrators can opt in to security collection on existing subscription
  schedules. Advisory findings do not change Azure resources or execute tests.
- Vulnerability and patch coverage depends on exposed Defender evidence.
  Scanner imports, richer identity analytics, and cross-source incident
  correlation are later-phase work.

13. First deployment and manual testing
The first complete deployment should follow this sequence:
1. Complete the Azure-focused application.
2. Verify backend APIs, frontend workflows, database migrations and automated tests through GitHub Actions.
3. Review duplicate and obsolete files. Present a deletion list before removing anything.
4. Finalize Dockerfile, Docker Compose and application configuration.
5. Push finalized code to the existing GitHub repository.
6. Build frontend and backend Docker containers.
7. Deploy to the existing AWS EC2 host using the existing deployment arrangement.
8. Verify application health, database connectivity, migrations and frontend availability.
9. You manually test the deployed application and provide feedback.
Future deployments will be manually triggered by you through GitHub.

14. Important engineering rules
1. Main Codex Agent coordinates development.
2. Full-Stack Developer is the primary implementation agent.
3. Cybersecurity Specialist, Network Manager and Compliance Officer review relevant phases.
4. DevOps Engineer is used for deployment-related work.
5. Maximum three concurrent subagents.
6. Avoid multiple agents editing the same files.
7. Reuse working V2.2 code.
8. Do not create UI-only placeholders and mark them complete.
9. Do not delete old reference folders until dependency verification and approval.
10. Do not deploy or change live infrastructure without explicit approval.
11. Follow the no-local-testing policy and use GitHub Actions for verification.
12. Preserve the existing repository and EC2 deployment arrangement.

Final product objective: MonitorAI should become one platform through which you can manage a portfolio of clients' Azure infrastructure, monitor operational health, identify security weaknesses, conduct authorized security assessments, measure compliance, investigate incidents and produce management reports—all with evidence, accountability and human control.