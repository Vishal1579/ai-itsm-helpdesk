"""ITSM taxonomy: categories, assignment groups, KB links, self-heal playbooks and intent exemplars."""

# Each sub-category maps to an assignment group, its primary KB article and (optionally) an
# automation playbook that the self-heal agent may run without a human.
CATEGORIES: list[dict] = [
    {
        "category": "Network", "subcategory": "VPN", "assignment_group": "Network Support",
        "kb": "KB0001", "resolution": "VPN troubleshooting", "playbook": None, "diagnostic": "vpn_status_check",
        "keywords": ["vpn", "globalprotect", "remote access", "tunnel", "gateway"],
        "description": "VPN remote access connection or authentication failure, GlobalProtect client",
    },
    {
        "category": "Network", "subcategory": "Wi-Fi", "assignment_group": "Network Support",
        "kb": "KB0005", "resolution": "Wi-Fi connectivity troubleshooting", "playbook": None, "diagnostic": None,
        "keywords": ["wifi", "wi-fi", "wireless", "corp-secure", "hotspot", "internet connection", "access point"],
        "description": "Wireless Wi-Fi network connectivity, no internet, dropping connection",
    },
    {
        "category": "Access", "subcategory": "Password", "assignment_group": "Identity & Access Management",
        "kb": "KB0002", "resolution": "Self-service password reset", "playbook": "password_reset", "diagnostic": None,
        "keywords": ["password", "passcode", "expired", "forgot my password", "reset my password", "change password"],
        "description": "Password expired, forgotten password, password reset",
    },
    {
        "category": "Access", "subcategory": "Account Lockout", "assignment_group": "Identity & Access Management",
        "kb": "KB0003", "resolution": "Account unlock", "playbook": "account_unlock", "diagnostic": None,
        "keywords": ["locked out", "account locked", "account is locked", "lockout", "unlock"],
        "description": "User account locked out after failed sign-in attempts, unlock account",
    },
    {
        "category": "Access", "subcategory": "Application Access", "assignment_group": "Identity & Access Management",
        "kb": "KB0008", "resolution": "Application access request", "playbook": None, "diagnostic": None,
        "keywords": ["access denied", "permission", "access to", "sap", "salesforce", "workday", "jira", "shared drive", "role"],
        "description": "Access to business application, permissions, access denied, shared drive",
    },
    {
        "category": "Email", "subcategory": "Outlook", "assignment_group": "Messaging Support",
        "kb": "KB0004", "resolution": "Outlook synchronization troubleshooting", "playbook": "outlook_cache_clear", "diagnostic": None,
        "keywords": ["outlook", "email", "e-mail", "mailbox", "inbox", "sync", "synchroni", "calendar", "outbox"],
        "description": "Outlook email not syncing, mailbox, calendar, send receive problems",
    },
    {
        "category": "Hardware", "subcategory": "Laptop Performance", "assignment_group": "Desktop Support",
        "kb": "KB0006", "resolution": "Laptop performance clean-up", "playbook": "laptop_cleanup", "diagnostic": None,
        "keywords": ["slow", "slowness", "laptop", "freez", "hang", "performance", "fan", "disk space", "lag"],
        "description": "Laptop or computer very slow, freezing, performance, disk full",
    },
    {
        "category": "Hardware", "subcategory": "Printer", "assignment_group": "Desktop Support",
        "kb": "KB0009", "resolution": "Print queue reset", "playbook": "service_restart", "diagnostic": None,
        "keywords": ["printer", "print", "printing", "spooler", "print queue", "followme"],
        "description": "Printer not printing, print jobs stuck in queue, print spooler",
    },
    {
        "category": "Collaboration", "subcategory": "Teams", "assignment_group": "Collaboration Support",
        "kb": "KB0010", "resolution": "Teams application restart", "playbook": "app_restart", "diagnostic": None,
        "keywords": ["teams", "meeting", "call", "microphone", "camera", "webcam"],
        "description": "Microsoft Teams frozen, not responding, meeting audio video issues",
    },
    {
        "category": "Software", "subcategory": "Installation", "assignment_group": "Software Distribution",
        "kb": "KB0007", "resolution": "Software catalogue provisioning", "playbook": None, "diagnostic": None,
        "keywords": ["install", "installed", "installation", "software", "license", "licence", "application", "download"],
        "description": "Install software application, software request, licence",
    },
]

GENERAL = {
    "category": "General", "subcategory": "Other", "assignment_group": "Service Desk",
    "kb": None, "resolution": "Manual triage by Service Desk", "playbook": None, "diagnostic": None,
    "keywords": [], "description": "General enquiry",
}

INTENTS = ["incident", "service_request", "knowledge_question", "automatable"]

# Exemplar utterances used for embedding-based (few-shot, nearest neighbour) intent detection
INTENT_EXEMPLARS: dict[str, list[str]] = {
    "incident": [
        "I cannot connect to VPN since this morning",
        "My laptop screen is flickering and goes black",
        "Wi-Fi keeps dropping in the meeting room",
        "I get an access denied error when opening SAP",
        "The shared drive is not loading for our team",
        "My docking station is not detecting the monitor",
        "Authentication keeps failing when I sign in",
        "The application crashes with an error every time I open it",
        "Internet is not working on my laptop",
    ],
    "service_request": [
        "I need Visual Studio Code installed on my laptop",
        "Please install Adobe Acrobat for me",
        "Can I get access to the Finance shared drive",
        "I would like a new monitor for my desk",
        "Request a licence for Microsoft Visio",
        "I need Zoom on my machine",
        "Please provision Docker Desktop",
    ],
    "knowledge_question": [
        "How do I troubleshoot Outlook synchronization?",
        "How can I connect to the office Wi-Fi?",
        "What is the password policy?",
        "Where can I find the software catalogue?",
        "How do I set up the VPN client?",
        "What should I do if my print job is stuck?",
        "Explain how to request application access",
    ],
    "automatable": [
        "My password has expired",
        "I forgot my password, please reset it",
        "My account is locked out",
        "Please unlock my account",
        "Outlook is not syncing my emails",
        "Teams is frozen and not responding",
        "My print jobs are stuck in the queue",
        "My laptop is running very slow",
    ],
}

# ITIL-style impact x urgency -> priority matrix
PRIORITY_MATRIX = {
    ("Enterprise", "High"): "P1", ("Department", "High"): "P1", ("Individual", "High"): "P2",
    ("Enterprise", "Medium"): "P2", ("Department", "Medium"): "P2", ("Individual", "Medium"): "P3",
    ("Enterprise", "Low"): "P3", ("Department", "Low"): "P3", ("Individual", "Low"): "P4",
}
PRIORITY_LABELS = {"P1": "1 - Critical", "P2": "2 - High", "P3": "3 - Moderate", "P4": "4 - Low"}
IMPACT_TO_SN = {"Enterprise": "1", "Department": "2", "Individual": "3"}
URGENCY_TO_SN = {"High": "1", "Medium": "2", "Low": "3"}


def find_category(subcategory: str) -> dict:
    return next((c for c in CATEGORIES if c["subcategory"] == subcategory), GENERAL)
