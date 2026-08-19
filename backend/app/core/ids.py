from __future__ import annotations

import ulid


def new_id() -> str:
    """Return a sortable ULID string for public domain identifiers."""

    return str(ulid.new())


__all__ = ["new_id"]
