import re
from collections import defaultdict
from typing import BinaryIO

from .schemas import PrivacyCategory, PrivacyExample, PrivacyReport
from .service import (
    InvalidLogArchiveError,
    _parse_log_path,
    open_log_archive,
    read_log_text,
)

EXAMPLES_PER_CATEGORY = 3

# Patterns for data that can identify a patient (PHI) or a person (PII).
# Keyed fields like "mrn=" or "dob:" need the key, because a bare number or date
# is far too common in logs to flag on its own.
# Not included on purpose: IP addresses (a HIPAA identifier, but every cluster log is full of
# internal 10.x addresses, so it would drown out real findings) and free-text names
# (no reliable pattern without a key).
KEY = r"[\"']?\s*[:=]\s*[\"']?"
PATTERNS = [
    ("ssn", "Social Security number", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("email", "Email address", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("phone", "Phone number", re.compile(r"(?<![\d-])\(?\d{3}\)?[-. ]\d{3}[-.]\d{4}\b")),
    (
        "mrn",
        "Medical record / patient ID",
        re.compile(r"\b(mrn|medical_?record(_?number)?|patient_?id)" + KEY + r"[\w-]+", re.I),
    ),
    (
        "dob",
        "Date of birth",
        re.compile(r"\b(dob|date_?of_?birth|birth_?date)" + KEY + r"[\d/.-]+", re.I),
    ),
    (
        "name",
        "Patient name field",
        re.compile(r"\b(patient_?name|first_?name|last_?name)" + KEY + r"[A-Za-z][\w' -]*", re.I),
    ),
]


def mask(category: str, text: str) -> str:
    """Hides most of a match so the report can show where PHI is without repeating it."""
    if category == "email":
        user, _, domain = text.partition("@")
        return f"{user[:1]}***@{domain}"
    if category in ("ssn", "phone"):
        return "***" + text[-4:]
    # Keyed fields: keep the key so the engineer knows which field it is, hide the value
    key_match = re.match(r"(.*?" + KEY + r")(.*)", text)
    if key_match:
        key, value = key_match.groups()
        return f"{key}{value[:1]}***"
    return "***"


def scan_log_archive(file: BinaryIO) -> PrivacyReport:
    """Finds lines in a log zip that look like they contain PHI/PII."""
    zf, entries = open_log_archive(file)

    report = PrivacyReport(files_scanned=0, total_findings=0)
    found: dict = defaultdict(lambda: {"count": 0, "containers": set(), "examples": []})

    with zf:
        for info in entries:
            parsed = _parse_log_path(info.filename)
            if parsed is None:
                if info.filename != "manifest.json":
                    report.skipped_files.append(f"{info.filename} (not a container log)")
                continue
            namespace, pod, container, _ = parsed
            label = f"{namespace}/{pod}/{container}"

            try:
                text = read_log_text(zf, info)
            except Exception as e:
                report.skipped_files.append(f"{info.filename} (could not read: {e})")
                continue

            report.files_scanned += 1
            for line_number, line in enumerate(text.splitlines(), start=1):
                for category, _, pattern in PATTERNS:
                    for match in pattern.finditer(line):
                        entry = found[category]
                        entry["count"] += 1
                        entry["containers"].add(label)
                        if len(entry["examples"]) < EXAMPLES_PER_CATEGORY:
                            entry["examples"].append(
                                PrivacyExample(
                                    container=label,
                                    line_number=line_number,
                                    masked=mask(category, match.group(0)),
                                )
                            )

    if report.files_scanned == 0:
        raise InvalidLogArchiveError(
            "No container logs found. Expected files like logs/<namespace>/<pod>/<container>.log"
        )

    labels = {category: label for category, label, _ in PATTERNS}
    report.categories = sorted(
        (
            PrivacyCategory(
                category=category,
                label=labels[category],
                count=data["count"],
                containers=sorted(data["containers"]),
                examples=data["examples"],
            )
            for category, data in found.items()
        ),
        key=lambda c: -c.count,
    )
    report.total_findings = sum(c.count for c in report.categories)
    return report
