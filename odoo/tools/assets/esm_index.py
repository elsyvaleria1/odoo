import hashlib
from collections.abc import Iterable, Mapping
from typing import Any

_SOURCE_KEY_VERSION = "6"


DEFAULT_VARIANT = "default"


def variant_key(
    assets_params: Mapping[str, Any] | None = None,
    *,
    page_scope: Iterable[str] = (),
    standalone: bool = False,
) -> str:
    parts = [
        f"{key}={value}"
        for key, value in sorted((assets_params or {}).items())
        if value not in (None, False, "")
    ]
    if page_scope:
        parts.append("page=" + "+".join(sorted(page_scope)))
    if standalone:
        parts.append("standalone")
    return ";".join(parts) or DEFAULT_VARIANT


def source_key(
    bundle: str,
    native_modules: Iterable[Any],
    dynamic_child_specs: Iterable[str] | None,
    secondary_stubs: dict[str, str],
    exported_specs: Iterable[str] | None,
    target: str,
    source_maps: str,
    registered_reach: Mapping[str, str] | None = None,
    legacy_scripts: Iterable[Any] = (),
    *,
    inlined_sources: Mapping[str, str],
    esbuild_version: str,
    external_specifiers: Iterable[str],
    script_format: str = "",
) -> str:
    digest = hashlib.sha256()
    if script_format:
        digest.update(script_format.encode())
        digest.update(b"\0")
    for part in (
        _SOURCE_KEY_VERSION,
        bundle,
        target,
        source_maps,
        esbuild_version,
        ",".join(sorted(external_specifiers)),
        ",".join(sorted(dynamic_child_specs or ())),
        ",".join(sorted(exported_specs or ())),
    ):
        digest.update(part.encode())
        digest.update(b"\0")
    for spec in sorted(secondary_stubs):
        digest.update(spec.encode())
        digest.update(secondary_stubs[spec].encode())
        digest.update(b"\0")
    for spec, url in sorted((registered_reach or {}).items()):
        digest.update(f"{spec}={url}".encode())
        digest.update(b"\0")
    for script in legacy_scripts:
        digest.update(script.unique_descriptor.encode())
        digest.update(b"\0")
    for asset in native_modules:
        digest.update((asset.module_path or asset.url or "").encode())
        digest.update(b"\0")
        raw = asset.raw_content
        digest.update(raw.encode() if isinstance(raw, str) else raw)
        digest.update(b"\0")
    _update_inlined(digest, inlined_sources)
    return digest.hexdigest()[:16]


def _update_inlined(digest: Any, inlined_sources: Mapping[str, str]) -> None:
    for spec in sorted(inlined_sources):
        digest.update(spec.encode())
        digest.update(b"\0")
        digest.update(inlined_sources[spec].encode())
        digest.update(b"\0")


def sidecar_urls(url: str) -> dict[str, str]:
    return {
        "metafile": url.removesuffix(".esm.js") + ".meta.json",
        "sourcemap": url + ".map",
    }


def group_source_key(
    group: str,
    entries: dict[str, Iterable[Any]],
    templates: dict[str, str],
    parent_specs: Iterable[str],
    secondary_stubs: dict[str, str],
    target: str,
    source_maps: str,
    *,
    inlined_sources: Mapping[str, str],
    esbuild_version: str,
    external_specifiers: Iterable[str],
) -> str:
    digest = hashlib.sha256()
    for part in (
        _SOURCE_KEY_VERSION,
        group,
        target,
        source_maps,
        esbuild_version,
        ",".join(sorted(external_specifiers)),
        ",".join(sorted(parent_specs)),
    ):
        digest.update(part.encode())
        digest.update(b"\0")
    for name in sorted(templates):
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(templates[name].encode())
        digest.update(b"\0")
    for spec in sorted(secondary_stubs):
        digest.update(spec.encode())
        digest.update(secondary_stubs[spec].encode())
        digest.update(b"\0")
    for name in sorted(entries):
        digest.update(name.encode())
        digest.update(b"\0")
        for asset in entries[name]:
            digest.update((asset.module_path or asset.url or "").encode())
            digest.update(b"\0")
            raw = asset.raw_content
            digest.update(raw.encode() if isinstance(raw, str) else raw)
            digest.update(b"\0")
    _update_inlined(digest, inlined_sources)
    return digest.hexdigest()[:16]
