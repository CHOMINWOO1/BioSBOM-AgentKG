"""Offline OSV version evaluation. Unknown is distinct from outside a snapshot range.

Version ranges use PEP 440 (PyPI) or strict SemVer 2.0. Git commit ranges are
not compared with package release strings when release ranges are available.
"""

from __future__ import annotations

from packaging.version import InvalidVersion, Version
from semver import Version as SemVersion


def range_contains(version: str, span: dict, ecosystem: str) -> bool | None:
    """Return True/False for a supported valid range, None for unknown evidence."""
    if not isinstance(span, dict):
        return None
    kind = span.get("type")
    parser = (
        SemVersion.parse
        if kind == "SEMVER"
        else (Version if kind == "ECOSYSTEM" and ecosystem == "PyPI" else None)
    )
    if parser is None:
        return None
    events = span.get("events")
    if not isinstance(events, list) or not events:
        return None
    try:
        installed = parser(version)
        # Local distribution builds can carry patches unrelated to upstream releases.
        if isinstance(installed, Version) and installed.local is not None:
            return None
        parsed, limits, keys = [], [], set()
        for event in events:
            if not isinstance(event, dict) or len(event) != 1:
                return None
            key, value = next(iter(event.items()))
            if key not in {"introduced", "fixed", "last_affected", "limit"}:
                return None
            if not isinstance(value, str) or not value:
                return None
            keys.add(key)
            if key == "limit":
                limits.append(None if value == "*" else parser(value))
            else:
                parsed.append(
                    (None if key == "introduced" and value == "0" else parser(value), key)
                )
        if "introduced" not in keys or {"fixed", "last_affected"} <= keys:
            return None
        # A duplicate boundary with contradictory transitions is not guessed.
        parsed.sort(key=lambda event: (event[0] is not None, event[0]))
        for previous, current in zip(parsed, parsed[1:], strict=False):
            if previous[0] == current[0]:
                return None
        if parsed[0][1] != "introduced":
            return None
        if limits and not any(limit is None or installed < limit for limit in limits):
            return False
        vulnerable = False
        for boundary, key in parsed:
            if key == "introduced" and (boundary is None or installed >= boundary):
                vulnerable = True
            elif key == "fixed" and installed >= boundary:
                vulnerable = False
            elif key == "last_affected" and installed > boundary:
                vulnerable = False
        return vulnerable
    except (InvalidVersion, ValueError, TypeError, OverflowError):
        return None


def affected_match(version: str, affected: dict) -> tuple[str | None, str]:
    """Union of explicit affected versions and applicable release ranges."""
    versions = affected.get("versions", [])
    if version in versions:
        return "exact_version", "Installed version explicitly listed as affected"
    spans = affected.get("ranges", [])
    if not isinstance(spans, list):
        return "ambiguous", "Malformed range evidence requires review"
    release_spans = [
        span for span in spans if not isinstance(span, dict) or span.get("type") != "GIT"
    ]
    if not release_spans:
        if spans or not versions:
            return (
                "ambiguous",
                "No applicable release range; commit or incomplete evidence requires review",
            )
        return None, "Version absent from explicit affected list"
    ecosystem = affected["package"].get("ecosystem")
    if not ecosystem and affected["package"].get("purl", "").startswith("pkg:pypi/"):
        ecosystem = "PyPI"
    outcomes = [range_contains(version, span, ecosystem) for span in release_spans]
    if True in outcomes:
        return "range_version", "Installed version falls within an OSV release range"
    if None in outcomes:
        return "ambiguous", "Unsupported or invalid release range/version requires review"
    return None, "Outside supplied release ranges; not a general safety verdict"
