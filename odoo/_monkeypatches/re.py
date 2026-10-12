import re


def patch_module() -> None:
    setattr(re, "_MAXCACHE", 4096)  # noqa: B010 -- re's private cache bound is absent from typeshed
