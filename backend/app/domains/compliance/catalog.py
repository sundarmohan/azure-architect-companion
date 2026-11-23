"""A versioned starter catalog of review prompts and official references."""

FRAMEWORK_CATALOG = (
    {
        "topic": "hipaa_transport_v1",
        "framework": "HIPAA",
        "edition": "Security Rule",
        "reference": "45 CFR 164.312(e)(1)",
        "title": "Electronic health information in transit",
        "prompt": "Identify in-scope ePHI flows and review their transmission safeguards. Check whether the observed storage account handles those flows.",
        "source_url": "https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/index.html",
        "evidence_topic": "transport",
    },
    {
        "topic": "soc2_transport_v1",
        "framework": "SOC 2",
        "edition": "2017 Trust Services Criteria, 2022 revised points of focus",
        "reference": "CC6.7",
        "title": "Protection of information in transit",
        "prompt": "Confirm which information flows are in engagement scope. Review transfer restrictions and safeguards using operating evidence.",
        "source_url": "https://www.aicpa-cima.com/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022",
        "evidence_topic": "transport",
    },
    {
        "topic": "iso27001_scope_v1",
        "framework": "ISO/IEC 27001",
        "edition": "2022",
        "reference": "Information security management system",
        "title": "Management system scope and control selection",
        "prompt": "Review the approved ISMS scope, documented risk treatment and selected controls. Determine which Azure resources and evidence belong in that scope.",
        "source_url": "https://www.iso.org/standard/27001",
        "evidence_topic": None,
    },
    {
        "topic": "pcidss_transport_v1",
        "framework": "PCI DSS",
        "edition": "v4.0.1",
        "reference": "Requirement 4.2",
        "title": "Protection of account data during public-network transmission",
        "prompt": "Confirm whether the resource transmits cardholder data over an open or public network. Review encryption and protocol evidence for those flows.",
        "source_url": "https://www.pcisecuritystandards.org/faqs/1075/",
        "evidence_topic": "transport",
    },
)
FRAMEWORK_TOPICS = {entry["topic"] for entry in FRAMEWORK_CATALOG}
