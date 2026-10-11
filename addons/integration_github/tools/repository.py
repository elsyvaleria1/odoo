def repository_domain(field: str, repository: str) -> list[tuple[str, str, str]]:
    literal = repository.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return [(field, "=ilike", literal)]


def same_repository(left: str | None, right: str | None) -> bool:
    return bool(left and right) and left.lower() == right.lower()
