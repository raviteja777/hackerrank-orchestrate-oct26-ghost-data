"""Resource catalog: resource prefix -> system_id and data category (DESIGN §7.1).

Rules: X-SYS-01 (closed vocabulary; unknown -> no step, logged), G-SYS-01 (replica copies map to the
base system), X-POL-01 (categories with no sample step use the rule default), OQ-1 (object_* flag).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import config

CATEGORIES = (
    "USER_PROFILE", "SECONDARY_IDENTIFIER", "SEARCH_INDEX_ENTRY", "ANALYTICS_PROFILE", "PRODUCT_TELEMETRY",
    "SUPPORT_MESSAGE", "SUPPORT_ATTACHMENT", "EMAIL_DELIVERY_LOG", "MARKETING_PROFILE", "USER_EXPORT",
    "CACHE_ENTRY", "BACKUP_ARCHIVE", "SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD", "ACCOUNT_TOMBSTONE",
)
DATA_FLOW = "DATA_FLOW"  # a process, not a data record (DESIGN §7.2)


@dataclass(frozen=True)
class CatalogEntry:
    prefix: str
    system_id: str
    category: str


# Longest prefix wins (data_flow_ before any shorter prefix, audit_record_ etc.).
_ENTRIES = (
    CatalogEntry("account_", "account_service", "USER_PROFILE"),
    CatalogEntry("search_", "search_service", "SEARCH_INDEX_ENTRY"),
    CatalogEntry("analytics_", "analytics_platform", "ANALYTICS_PROFILE"),
    CatalogEntry("support_", "support_platform", "SUPPORT_MESSAGE"),
    CatalogEntry("export_", "export_service", "USER_EXPORT"),
    CatalogEntry("data_flow_", "integration_service", DATA_FLOW),
    CatalogEntry("backup_", "backup_service", "BACKUP_ARCHIVE"),
    CatalogEntry("audit_record_", "security_service", "SECURITY_AUDIT_LOG"),
    CatalogEntry("tombstone_", "identity_service", "ACCOUNT_TOMBSTONE"),
    CatalogEntry("cache_", "cache_service", "CACHE_ENTRY"),
    CatalogEntry("email_delivery_", "email_delivery_service", "EMAIL_DELIVERY_LOG"),
    CatalogEntry("marketing_", "marketing_platform", "MARKETING_PROFILE"),
    CatalogEntry("legal_hold_", "legal_service", "LEGAL_HOLD_RECORD"),
    CatalogEntry("object_", "object_storage", "SUPPORT_ATTACHMENT"),  # OQ-1 default, flag object_as_attachment
)
_BY_LENGTH = sorted(_ENTRIES, key=lambda e: -len(e.prefix))
PREFIXES = tuple(e.prefix for e in _BY_LENGTH)
SYSTEMS = frozenset(e.system_id for e in _ENTRIES)

# Matches a catalog resource id inside free text (PDF, handover, OCR): <prefix><digits>.
RESOURCE_ID_RE = re.compile(r"\b(?:" + "|".join(re.escape(p) for p in PREFIXES) + r")\d+\b")

# Container / service names seen in evidence that are not base systems (G-SYS-01 and aliases).
_ALIASES = {
    "profile_service": "account_service",
    "account_replication_cluster": "account_service",
    "support_replica": "support_platform",
    "support_storage_service": "support_platform",
    "backup_restore_service": "backup_service",
    "search_index_service": "search_service",
}


def entry_for(resource_id: str | None) -> CatalogEntry | None:
    if not resource_id:
        return None
    rid = resource_id.strip().lower()
    for e in _BY_LENGTH:
        if rid.startswith(e.prefix):
            return e
    return None


def prefix_of(resource_id: str) -> str:
    return re.sub(r"\d+$", "", resource_id.strip().lower()) or resource_id


def normalize_system(name: str | None) -> str | None:
    """Map a container/service name to a catalog system_id; replica names map to the base system (G-SYS-01)."""
    if not name:
        return None
    n = name.strip().lower()
    if n in SYSTEMS:
        return n
    if n in _ALIASES:
        return _ALIASES[n]
    n2 = re.sub(r"_(?:primary|failover_replica|read_replica|reporting_replica|replica(?:_\w+)?)$", "", n)
    if n2 in SYSTEMS:
        return n2
    return _ALIASES.get(n2)


def system_for(resource_id: str | None, hint: str | None = None) -> str | None:
    """Catalog system by resource prefix; else the normalised hint (parent key / data_store); else None (X-SYS-01)."""
    e = entry_for(resource_id)
    if e:
        return e.system_id
    return normalize_system(hint)


def category_for(resource_id: str | None, label: str | None = None, collection: str | None = None,
                 event: str | None = None) -> str | None:
    """Default category from the prefix, refined by explicit labels (trusted) and attachment cues (DESIGN §7.1)."""
    e = entry_for(resource_id)
    base = e.category if e else None
    if label:
        lab = label.strip().upper()
        if lab in CATEGORIES or lab == DATA_FLOW:
            return lab
    if base == "SUPPORT_MESSAGE":
        cues = " ".join(x for x in (collection, event) if x).lower()
        if "attachment" in cues:
            return "SUPPORT_ATTACHMENT"
    if base == "SUPPORT_ATTACHMENT" and e and e.prefix == "object_" and not config.FLAGS.object_as_attachment:
        return None
    return base
