"""Structural contract tests for the bundled identifier schema."""

import json
from pathlib import Path


def test_schema_supports_legacy_records_and_optional_extensions() -> None:
    path = Path("src/biblio/schema/identifier_collection.schema.json")
    schema = json.loads(path.read_text(encoding="utf-8"))
    record = schema["additionalProperties"]

    assert record["required"] == ["main_identifier", "identifiers"]
    assert set(record["properties"]) == {
        "main_identifier",
        "identifiers",
        "identifier_alternates",
        "key_history",
    }
    assert schema["$defs"]["identifierValue"] == {"type": "string", "minLength": 1}
    assert record["properties"]["identifiers"]["additionalProperties"] == {
        "$ref": "#/$defs/identifierValue"
    }
    assert set(record["properties"]["identifiers"]["properties"]) == {
        "doi",
        "isbn13",
        "arxiv",
        "url",
        "mrnumber",
        "zbl",
        "zbmath",
        "jfm",
        "oclc",
        "hdl",
        "acmdl_doi",
    }
    assert schema["$defs"]["alternateValues"] == {
        "type": "array",
        "items": {"$ref": "#/$defs/identifierValue"},
        "minItems": 1,
        "uniqueItems": True,
    }
    assert record["properties"]["identifier_alternates"]["additionalProperties"] == {
        "$ref": "#/$defs/alternateValues"
    }
    assert record["properties"]["key_history"]["items"]["properties"]["identifier"] == {
        "$ref": "#/$defs/identifierValue"
    }
