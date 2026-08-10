"""Cross-artifact bibliography workspace aggregate."""

from dataclasses import dataclass

from .bibliography import Bibliography
from .identifier_collection import (
    SUPPORTED_IDENTIFIER_KIND_SET,
    IdentifierCollection,
    IdentifierRecord,
    identifier_equality_token,
    identifiers_from_entry,
)
from .identifiers import hash_exact_legacy_identifier


def _hash_issue(key: str, exact_identifier: str) -> str | None:
    expected = hash_exact_legacy_identifier(exact_identifier)
    actual = key.rsplit("-", 1)[-1]
    if actual != expected:
        return f"key '{key}' suffix '{actual}' does not match exact identifier hash '{expected}'"
    return None


@dataclass(slots=True)
class WorkspaceAggregate:
    """One validated view of the bibliography, inventory, and order ledger."""

    bibliography: Bibliography
    identifiers: IdentifierCollection
    add_order: tuple[str, ...]

    def validation_issues(self) -> tuple[str, ...]:
        """Return all deterministic cross-artifact and provenance issues."""
        issues: list[str] = []
        try:
            self.bibliography.validate()
        except ValueError as error:
            issues.append(str(error))

        bibliography_keys = tuple(entry.key for entry in self.bibliography)
        bibliography_keyset = set(bibliography_keys)
        identifier_keyset = set(self.identifiers)
        order_keyset = set(self.add_order)
        if not (bibliography_keyset == identifier_keyset == order_keyset):
            issues.append(
                "canonical keysets differ: "
                f"bibliography_only={sorted(bibliography_keyset - identifier_keyset)}; "
                f"identifiers_only={sorted(identifier_keyset - bibliography_keyset)}; "
                f"order_missing={sorted(bibliography_keyset - order_keyset)}; "
                f"order_extra={sorted(order_keyset - bibliography_keyset)}"
            )
        if bibliography_keys != self.add_order:
            issues.append("physical bibliography order differs from add-order ledger")

        for canonical_key, record in self.identifiers.items():
            issues.extend(self._record_issues(canonical_key, record))
            if canonical_key not in bibliography_keyset:
                continue
            entry = self.bibliography.resolve(canonical_key)
            aliases = self.bibliography.aliases_for(canonical_key)
            issues.extend(self._history_issues(canonical_key, aliases, record))
            try:
                projected = identifiers_from_entry(entry)
            except ValueError as error:
                issues.append(str(error))
                continue
            for kind, value in projected.items():
                inventory = record.inventory_values(kind)
                try:
                    token = identifier_equality_token(kind, value)
                    matches = any(
                        identifier_equality_token(kind, candidate) == token
                        for candidate in inventory
                    )
                except ValueError as error:
                    issues.append(
                        f"entry '{canonical_key}' identifier '{kind}' cannot be compared: {error}"
                    )
                    continue
                if not matches:
                    issues.append(
                        f"entry '{canonical_key}' bibliography identifier '{kind}' "
                        "is absent from its JSON inventory"
                    )
        issues.extend(self._injectivity_issues())
        return tuple(issues)

    def validate(self) -> None:
        """Raise with the complete deterministic issue report when invalid."""
        issues = self.validation_issues()
        if issues:
            raise ValueError("; ".join(issues))

    @staticmethod
    def _record_issues(canonical_key: str, record: IdentifierRecord) -> tuple[str, ...]:
        issues: list[str] = []
        all_kinds = (
            set(record.identifiers)
            | set(record.identifier_alternates)
            | {record.main_identifier}
            | {item.main_identifier for item in record.key_history}
        )
        for kind in sorted(all_kinds):
            if kind not in SUPPORTED_IDENTIFIER_KIND_SET:
                issues.append(f"record '{canonical_key}' has unknown identifier kind '{kind}'")
        exact_main = record.identifiers.get(record.main_identifier)
        if exact_main is None:
            issues.append(
                f"record '{canonical_key}' main identifier '{record.main_identifier}' "
                "is absent from primary identifiers"
            )
        else:
            hash_issue = _hash_issue(canonical_key, exact_main)
            if hash_issue is not None:
                issues.append(hash_issue)

        for kind, value in record.identifiers.items():
            issues.extend(WorkspaceAggregate._empty_identifier_issues(canonical_key, kind, value))

        for kind, alternates in record.identifier_alternates.items():
            if not alternates:
                issues.append(
                    f"record '{canonical_key}' alternate identifier list '{kind}' is empty"
                )
            primary = record.identifiers.get(kind)
            if primary is None:
                issues.append(
                    f"record '{canonical_key}' alternate identifier kind '{kind}' "
                    "has no primary value"
                )
            seen: set[str] = set()
            for value in alternates:
                issues.extend(
                    WorkspaceAggregate._empty_identifier_issues(canonical_key, kind, value)
                )
                if value == primary:
                    issues.append(
                        f"record '{canonical_key}' alternate '{kind}' "
                        "duplicates primary exact value"
                    )
                if value in seen:
                    issues.append(
                        f"record '{canonical_key}' alternate '{kind}' repeats exact value '{value}'"
                    )
                seen.add(value)
        return tuple(issues)

    @staticmethod
    def _empty_identifier_issues(
        canonical_key: str, kind: str, exact_value: str
    ) -> tuple[str, ...]:
        if not exact_value.strip():
            return (f"record '{canonical_key}' identifier '{kind}' must not be empty",)
        try:
            token = identifier_equality_token(kind, exact_value)
        except ValueError:
            return ()
        if not token:
            return (f"record '{canonical_key}' identifier '{kind}' has an empty comparison token",)
        return ()

    def _injectivity_issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        global_tokens: dict[tuple[str, str], tuple[str, str]] = {}
        for canonical_key, record in self.identifiers.items():
            kinds = dict.fromkeys((*record.identifiers, *record.identifier_alternates))
            for kind in kinds:
                local_tokens: dict[str, str] = {}
                for exact_value in record.inventory_values(kind):
                    try:
                        token = identifier_equality_token(kind, exact_value)
                    except ValueError as error:
                        issues.append(
                            f"record '{canonical_key}' identifier '{kind}' "
                            f"cannot be compared: {error}"
                        )
                        continue
                    prior_local = local_tokens.get(token)
                    if prior_local is not None:
                        if prior_local != exact_value:
                            issues.append(
                                f"record '{canonical_key}' has equivalent duplicate '{kind}' "
                                f"values '{prior_local}' and '{exact_value}'"
                            )
                        continue
                    local_tokens[token] = exact_value
                    identity = (kind, token)
                    prior_global = global_tokens.get(identity)
                    if prior_global is not None and prior_global[0] != canonical_key:
                        issues.append(
                            f"identifier '{kind}' value '{exact_value}' in record "
                            f"'{canonical_key}' collides with record '{prior_global[0]}'"
                        )
                    else:
                        global_tokens[identity] = (canonical_key, exact_value)
        return tuple(issues)

    @staticmethod
    def _history_issues(
        canonical_key: str, aliases: tuple[str, ...], record: IdentifierRecord
    ) -> tuple[str, ...]:
        if not record.key_history:
            return (f"record '{canonical_key}' aliases require key_history",) if aliases else ()

        issues: list[str] = []
        history_keys = tuple(item.key for item in record.key_history)
        if len(set(history_keys)) != len(history_keys):
            issues.append(f"record '{canonical_key}' key_history keys must be unique")
        if set(history_keys) != {canonical_key, *aliases}:
            issues.append(
                f"record '{canonical_key}' key_history keys must equal canonical key and aliases"
            )
        history_alias_order = tuple(key for key in history_keys if key != canonical_key)
        if history_alias_order != aliases:
            issues.append(
                f"record '{canonical_key}' key_history alias order differs from BibLaTeX ids"
            )

        canonical_items = [item for item in record.key_history if item.key == canonical_key]
        if len(canonical_items) == 1:
            canonical_item = canonical_items[0]
            exact_main = record.identifiers.get(record.main_identifier)
            if (
                canonical_item.main_identifier != record.main_identifier
                or canonical_item.identifier != exact_main
            ):
                issues.append(
                    f"record '{canonical_key}' canonical key_history item differs "
                    "from current main identifier"
                )

        for item in record.key_history:
            issues.extend(
                WorkspaceAggregate._empty_identifier_issues(
                    canonical_key, item.main_identifier, item.identifier
                )
            )
            if item.identifier not in record.inventory_values(item.main_identifier):
                issues.append(
                    f"record '{canonical_key}' history key '{item.key}' references an identifier "
                    "absent from the complete inventory"
                )
            hash_issue = _hash_issue(item.key, item.identifier)
            if hash_issue is not None:
                issues.append(hash_issue)
        return tuple(issues)
