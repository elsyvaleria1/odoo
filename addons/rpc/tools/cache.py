import hashlib

INDEX_NAME_PREFIX = "odoo-doc-index-"

ACCESS_CACHE_SEQUENCES = ("stable", "groups")


def doc_cache_generation(env):
    registry_sequence, cache_sequences = env.registry.get_sequences(env.cr)
    material = (
        registry_sequence,
        *(cache_sequences[name] for name in ACCESS_CACHE_SEQUENCES),
    )
    return hashlib.blake2b(repr(material).encode(), digest_size=6).hexdigest()


def index_attachment_name(generation, unique) -> str:
    return f"{INDEX_NAME_PREFIX}{generation}-{unique}.json"


def stale_index_domain(generation) -> list:
    return [
        ("name", "=like", f"{INDEX_NAME_PREFIX}%"),
        ("name", "not like", f"{INDEX_NAME_PREFIX}{generation}-"),
    ]
