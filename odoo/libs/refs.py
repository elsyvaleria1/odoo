__all__ = ["split_refs"]


def split_refs(value: str) -> list[str]:
    return [ref for part in value.split(",") if (ref := part.strip())]
