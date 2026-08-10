"""Pure validation of the canonical BibLaTeX bibliography model."""

import re

from .bibliography import Bibliography
from .results import ValidateResult

_GENERATED_CITEKEY = re.compile(r"^[a-z]+-(?:[0-9]{4}|unknown)-[0-9a-f]{8}$")


def validate_bibliography(bibliography: Bibliography) -> ValidateResult:
    """Check parse/model, identity, citekey, and core BibLaTeX semantics."""
    issues: list[str] = []
    try:
        bibliography.validate()
    except ValueError as error:
        return ValidateResult(valid=False, issues=(str(error),))

    for entry in bibliography:
        fields: dict[str, str] = {}
        for field in entry.fields:
            name = field.key.casefold()
            if name in fields:
                issues.append(f"entry '{entry.key}' has duplicate '{name}' fields")
            else:
                fields[name] = str(field.value)

        if not _GENERATED_CITEKEY.fullmatch(entry.key):
            issues.append(f"entry '{entry.key}' does not have a generated citekey shape")
        if not entry.entry_type.strip():
            issues.append(f"entry '{entry.key}' has an empty entry type")
        if not any(name in fields for name in ("title", "journaltitle", "booktitle")):
            issues.append(f"entry '{entry.key}' has no title-bearing field")

        eprinttype = fields.get("eprinttype", fields.get("archiveprefix", ""))
        if eprinttype.strip().casefold() == "arxiv" and not fields.get("eprint", "").strip():
            issues.append(f"entry '{entry.key}' declares arXiv without a nonempty eprint")
        if "eprintclass" in fields and eprinttype.strip().casefold() != "arxiv":
            issues.append(f"entry '{entry.key}' has eprintclass without eprinttype=arxiv")

    return ValidateResult(valid=not issues, issues=tuple(issues))
