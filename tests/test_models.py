from backend.app import models  # noqa: F401 - import registers model metadata
from backend.app.core.database import Base


def test_core_tables_are_registered() -> None:
    assert "users" in Base.metadata.tables
    assert "workspaces" in Base.metadata.tables
    assert "runs" in Base.metadata.tables
    assert "run_events" in Base.metadata.tables
