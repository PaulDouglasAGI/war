"""
Triage engine: CVSS-based severity scoring and vulnerability classification.

Implements a simplified CVSS v3.1 calculator and auto-triage heuristics
to help analysts quickly assess incoming bug reports.
"""

from dataclasses import dataclass
from typing import Optional
from .models import Severity, VulnType


# ---------------------------------------------------------------------------
# CVSS v3.1 simplified scoring
# ---------------------------------------------------------------------------

# Attack Vector
AV_NETWORK = 0.85
AV_ADJACENT = 0.62
AV_LOCAL = 0.55
AV_PHYSICAL = 0.20

# Attack Complexity
AC_LOW = 0.77
AC_HIGH = 0.44

# Privileges Required
PR_NONE = 0.85
PR_LOW = 0.62
PR_HIGH = 0.27

# User Interaction
UI_NONE = 0.85
UI_REQUIRED = 0.62

# Scope
SCOPE_UNCHANGED = "U"
SCOPE_CHANGED = "C"

# Impact (Confidentiality / Integrity / Availability)
IMPACT_NONE = 0.00
IMPACT_LOW = 0.22
IMPACT_HIGH = 0.56


@dataclass
class CVSSVector:
    """CVSS v3.1 base vector components."""
    attack_vector: float = AV_NETWORK          # AV
    attack_complexity: float = AC_LOW          # AC
    privileges_required: float = PR_NONE       # PR
    user_interaction: float = UI_NONE          # UI
    scope: str = SCOPE_UNCHANGED               # S
    confidentiality: float = IMPACT_HIGH       # C
    integrity: float = IMPACT_HIGH             # I
    availability: float = IMPACT_HIGH          # A


def calculate_cvss(vector: CVSSVector) -> float:
    """Calculate CVSS v3.1 base score (0.0 – 10.0)."""
    # Adjust PR when scope is Changed
    pr = vector.privileges_required
    if vector.scope == SCOPE_CHANGED:
        if pr == PR_LOW:
            pr = 0.50
        elif pr == PR_HIGH:
            pr = 0.50

    exploitability = 8.22 * vector.attack_vector * vector.attack_complexity * pr * vector.user_interaction

    isc_base = 1 - (
        (1 - vector.confidentiality) *
        (1 - vector.integrity) *
        (1 - vector.availability)
    )

    if vector.scope == SCOPE_UNCHANGED:
        impact = 6.42 * isc_base
    else:
        impact = 7.52 * (isc_base - 0.029) - 3.25 * ((isc_base - 0.02) ** 15)

    if impact <= 0:
        return 0.0

    raw = min(10.0, impact + exploitability)

    # Round up to nearest 0.1
    score = round(raw * 10) / 10
    return score


def cvss_to_severity(score: float) -> Severity:
    """Map CVSS base score to severity label (CVSS v3.1 ratings)."""
    if score == 0.0:
        return Severity.INFORMATIONAL
    elif score < 4.0:
        return Severity.LOW
    elif score < 7.0:
        return Severity.MEDIUM
    elif score < 9.0:
        return Severity.HIGH
    else:
        return Severity.CRITICAL


# ---------------------------------------------------------------------------
# Vulnerability type presets
# Default CVSS vectors for common vuln types (worst-case assumptions)
# Analysts can override these during triage.
# ---------------------------------------------------------------------------

VULN_TYPE_DEFAULTS: dict[str, CVSSVector] = {
    VulnType.RCE.value: CVSSVector(
        attack_vector=AV_NETWORK, attack_complexity=AC_LOW,
        privileges_required=PR_NONE, user_interaction=UI_NONE,
        scope=SCOPE_CHANGED, confidentiality=IMPACT_HIGH,
        integrity=IMPACT_HIGH, availability=IMPACT_HIGH,
    ),
    VulnType.SQLI.value: CVSSVector(
        attack_vector=AV_NETWORK, attack_complexity=AC_LOW,
        privileges_required=PR_NONE, user_interaction=UI_NONE,
        scope=SCOPE_UNCHANGED, confidentiality=IMPACT_HIGH,
        integrity=IMPACT_HIGH, availability=IMPACT_LOW,
    ),
    VulnType.XSS.value: CVSSVector(
        attack_vector=AV_NETWORK, attack_complexity=AC_LOW,
        privileges_required=PR_NONE, user_interaction=UI_REQUIRED,
        scope=SCOPE_CHANGED, confidentiality=IMPACT_LOW,
        integrity=IMPACT_LOW, availability=IMPACT_NONE,
    ),
    VulnType.SSRF.value: CVSSVector(
        attack_vector=AV_NETWORK, attack_complexity=AC_LOW,
        privileges_required=PR_NONE, user_interaction=UI_NONE,
        scope=SCOPE_CHANGED, confidentiality=IMPACT_HIGH,
        integrity=IMPACT_LOW, availability=IMPACT_NONE,
    ),
    VulnType.IDOR.value: CVSSVector(
        attack_vector=AV_NETWORK, attack_complexity=AC_LOW,
        privileges_required=PR_LOW, user_interaction=UI_NONE,
        scope=SCOPE_UNCHANGED, confidentiality=IMPACT_HIGH,
        integrity=IMPACT_LOW, availability=IMPACT_NONE,
    ),
    VulnType.AUTH_BYPASS.value: CVSSVector(
        attack_vector=AV_NETWORK, attack_complexity=AC_LOW,
        privileges_required=PR_NONE, user_interaction=UI_NONE,
        scope=SCOPE_UNCHANGED, confidentiality=IMPACT_HIGH,
        integrity=IMPACT_HIGH, availability=IMPACT_NONE,
    ),
    VulnType.CSRF.value: CVSSVector(
        attack_vector=AV_NETWORK, attack_complexity=AC_LOW,
        privileges_required=PR_NONE, user_interaction=UI_REQUIRED,
        scope=SCOPE_UNCHANGED, confidentiality=IMPACT_NONE,
        integrity=IMPACT_HIGH, availability=IMPACT_NONE,
    ),
    VulnType.XXE.value: CVSSVector(
        attack_vector=AV_NETWORK, attack_complexity=AC_LOW,
        privileges_required=PR_NONE, user_interaction=UI_NONE,
        scope=SCOPE_UNCHANGED, confidentiality=IMPACT_HIGH,
        integrity=IMPACT_NONE, availability=IMPACT_NONE,
    ),
    VulnType.OPEN_REDIRECT.value: CVSSVector(
        attack_vector=AV_NETWORK, attack_complexity=AC_LOW,
        privileges_required=PR_NONE, user_interaction=UI_REQUIRED,
        scope=SCOPE_UNCHANGED, confidentiality=IMPACT_LOW,
        integrity=IMPACT_NONE, availability=IMPACT_NONE,
    ),
    VulnType.INFO_DISCLOSURE.value: CVSSVector(
        attack_vector=AV_NETWORK, attack_complexity=AC_LOW,
        privileges_required=PR_NONE, user_interaction=UI_NONE,
        scope=SCOPE_UNCHANGED, confidentiality=IMPACT_LOW,
        integrity=IMPACT_NONE, availability=IMPACT_NONE,
    ),
    VulnType.PRIVILEGE_ESCALATION.value: CVSSVector(
        attack_vector=AV_NETWORK, attack_complexity=AC_LOW,
        privileges_required=PR_LOW, user_interaction=UI_NONE,
        scope=SCOPE_CHANGED, confidentiality=IMPACT_HIGH,
        integrity=IMPACT_HIGH, availability=IMPACT_HIGH,
    ),
    VulnType.BROKEN_ACCESS.value: CVSSVector(
        attack_vector=AV_NETWORK, attack_complexity=AC_LOW,
        privileges_required=PR_LOW, user_interaction=UI_NONE,
        scope=SCOPE_UNCHANGED, confidentiality=IMPACT_HIGH,
        integrity=IMPACT_HIGH, availability=IMPACT_NONE,
    ),
    VulnType.MISCONFIG.value: CVSSVector(
        attack_vector=AV_NETWORK, attack_complexity=AC_LOW,
        privileges_required=PR_NONE, user_interaction=UI_NONE,
        scope=SCOPE_UNCHANGED, confidentiality=IMPACT_LOW,
        integrity=IMPACT_NONE, availability=IMPACT_NONE,
    ),
    VulnType.OTHER.value: CVSSVector(
        attack_vector=AV_NETWORK, attack_complexity=AC_HIGH,
        privileges_required=PR_NONE, user_interaction=UI_NONE,
        scope=SCOPE_UNCHANGED, confidentiality=IMPACT_LOW,
        integrity=IMPACT_LOW, availability=IMPACT_NONE,
    ),
}


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def similarity_score(title_a: str, asset_a: str, type_a: str,
                     title_b: str, asset_b: str, type_b: str) -> float:
    """
    Rough similarity score (0.0 – 1.0) between two reports.
    Returns a value >= 0.7 when reports are likely duplicates.
    """
    score = 0.0

    # Same asset is a strong signal
    if asset_a.lower().strip() == asset_b.lower().strip():
        score += 0.4

    # Same vulnerability type
    if type_a == type_b:
        score += 0.3

    # Title word overlap
    words_a = set(title_a.lower().split())
    words_b = set(title_b.lower().split())
    if words_a and words_b:
        overlap = len(words_a & words_b) / max(len(words_a), len(words_b))
        score += 0.3 * overlap

    return round(score, 2)


def auto_triage(vuln_type: str, custom_vector: Optional[CVSSVector] = None) -> tuple[float, Severity]:
    """
    Return (cvss_score, severity) for a given vulnerability type.
    Uses preset vectors unless a custom vector is provided.
    """
    vector = custom_vector or VULN_TYPE_DEFAULTS.get(vuln_type, VULN_TYPE_DEFAULTS[VulnType.OTHER.value])
    score = calculate_cvss(vector)
    severity = cvss_to_severity(score)
    return score, severity
