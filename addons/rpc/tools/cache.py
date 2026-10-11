"""Cache identity for the `/doc` documents.

Two things are named here, and they have to agree: the ETag a client caches
under, and the attachment name the server stores the index under. Both are
derived from the same *generation* -- the state of the database that the
document's content depends on -- which is what lets the garbage collector
recognise, with a domain and no Python filtering, every index that can no
longer be served.
"""

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
