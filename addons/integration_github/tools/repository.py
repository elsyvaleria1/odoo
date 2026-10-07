def repository_domain(field: str, repository: str) -> list[tuple[str, str, str]]:
    """``field`` names ``repository``, as GitHub does: whatever the case. Its
    ``_`` and ``%`` are literal, not wildcards."""
    literal = repository.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return [(field, "=ilike", literal)]


def same_repository(left: str | None, right: str | None) -> bool:
    return bool(left and right) and left.lower() == right.lower()
