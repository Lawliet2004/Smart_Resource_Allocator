"""Helpers for safe SQL text search."""

LIKE_ESCAPE_CHAR = "\\"


def like_pattern(value: str) -> str:
    """Build a ``%contains%`` pattern with LIKE wildcards neutralized.

    Without this, a search for ``%`` matches every row and a long run of
    wildcards makes Postgres do far more work than the user asked for. Use with
    ``Column.ilike(like_pattern(q), escape=LIKE_ESCAPE_CHAR)``.
    """
    escaped = (
        value.replace(LIKE_ESCAPE_CHAR, LIKE_ESCAPE_CHAR * 2)
        .replace("%", f"{LIKE_ESCAPE_CHAR}%")
        .replace("_", f"{LIKE_ESCAPE_CHAR}_")
    )
    return f"%{escaped}%"
