"""What kinds of initiatives we detect, and who usually owns each kind.

The taxonomy is tuned for IT services and consulting sellers. Each customer
workspace maps its own offerings onto these categories (see profiles.py).
"""

CATEGORIES: dict[str, dict] = {
    "qa_testing": {
        "function_words": ['qa', 'quality', 'test', 'testing', 'sdet'],
        "label": "QA / testing",
        "owner_titles": ["Head of QA", "Director Quality Engineering", "QA Manager", "Head of Testing"],
        "sponsor_titles": ["CTO", "VP Engineering", "CIO"],
        "practitioner_titles": ["QA Lead", "SDET Lead", "Test Automation Lead"],
    },
    "app_launch": {
        "function_words": ['digital', 'product', 'mobile', 'app', 'channels', 'device', 'devices', 'ios', 'android'],
        "label": "New app / product launch",
        "owner_titles": ["Head of Product", "Director Engineering", "Head of Digital"],
        "sponsor_titles": ["Chief Digital Officer", "CTO", "CPO"],
        "practitioner_titles": ["Engineering Manager", "Product Manager", "Mobile Lead"],
    },
    "cloud_migration": {
        "function_words": ['cloud', 'infrastructure', 'platform', 'devops', 'sre'],
        "label": "Cloud migration",
        "owner_titles": ["Head of Cloud", "Director Infrastructure", "Head of Platform Engineering"],
        "sponsor_titles": ["CIO", "CTO", "VP Infrastructure"],
        "practitioner_titles": ["Cloud Architect", "DevOps Lead", "SRE Manager"],
    },
    "app_modernization": {
        "function_words": ['technology', 'core', 'enterprise', 'architect', 'systems', 'transformation'],
        "label": "Application / core modernisation",
        "owner_titles": ["Head of Technology", "Director Engineering", "Head of Core Systems"],
        "sponsor_titles": ["CIO", "CTO", "COO"],
        "practitioner_titles": ["Enterprise Architect", "Engineering Manager", "Program Manager"],
    },
    "data_ai": {
        "function_words": ['ai', 'ml', 'data', 'analytics', 'machine', 'science'],
        "label": "Data & AI / GenAI",
        "owner_titles": ["Head of Data", "Head of AI", "Director Data Science", "Chief Data Officer"],
        "sponsor_titles": ["CTO", "CIO", "Chief Digital Officer"],
        "practitioner_titles": ["ML Engineering Manager", "Data Engineering Lead", "AI Architect"],
    },
    "cybersecurity": {
        "function_words": ['security', 'ciso', 'appsec', 'soc', 'cyber', 'risk'],
        "label": "Cybersecurity",
        "owner_titles": ["CISO", "Head of Information Security", "Director Security"],
        "sponsor_titles": ["CIO", "CTO", "Chief Risk Officer"],
        "practitioner_titles": ["Security Architect", "AppSec Lead", "SOC Manager"],
    },
    "erp_crm": {
        "function_words": ['erp', 'sap', 'applications', 'salesforce', 'crm'],
        "label": "ERP / CRM rollout",
        "owner_titles": ["Head of Enterprise Applications", "Director ERP", "Head of IT Applications"],
        "sponsor_titles": ["CIO", "CFO", "COO"],
        "practitioner_titles": ["SAP Lead", "Salesforce Lead", "Functional Architect"],
    },
    "devops_platform": {
        "function_words": ['platform', 'devops', 'sre', 'reliability'],
        "label": "DevOps / platform engineering",
        "owner_titles": ["Head of Platform Engineering", "Director DevOps", "Head of SRE"],
        "sponsor_titles": ["CTO", "VP Engineering"],
        "practitioner_titles": ["DevOps Lead", "Platform Engineering Manager"],
    },
    "compliance": {
        "function_words": ['compliance', 'risk', 'governance', 'regulatory'],
        "label": "Regulatory / compliance programme",
        "owner_titles": ["Head of Compliance Technology", "Chief Compliance Officer", "Head of IT Risk"],
        "sponsor_titles": ["CIO", "Chief Risk Officer", "COO"],
        "practitioner_titles": ["Compliance Program Manager", "IT Risk Manager"],
    },
    "gcc_expansion": {
        "function_words": ['site', 'gcc', 'centre', 'center', 'india'],
        "label": "GCC / new centre / expansion",
        "owner_titles": ["GCC Head", "Site Leader", "Managing Director India"],
        "sponsor_titles": ["CEO", "COO", "CTO"],
        "practitioner_titles": ["Engineering Director", "Talent Acquisition Head"],
    },
    "other": {
        "function_words": [],
        "label": "Other",
        "owner_titles": ["Director Engineering"],
        "sponsor_titles": ["CTO", "CIO"],
        "practitioner_titles": ["Engineering Manager"],
    },
}

STAGES = ["hinted", "announced", "hiring", "in_flight", "vendor_selection"]
ROLES = ["Owner", "Sponsor", "Influencer", "Practitioner"]


def category(key: str) -> dict:
    return CATEGORIES.get(key) or CATEGORIES["other"]
