from __future__ import annotations

import pytest

from backend.scripts.ensure_database import validate_database_name


def test_database_setup_rejects_identifier_injection() -> None:
    assert validate_database_name("company_agent") == "company_agent"
    with pytest.raises(ValueError):
        validate_database_name("company_agent; DROP DATABASE mysql")
