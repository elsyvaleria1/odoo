#!/bin/bash
# geoengine machine-doc fact-check. Run from any cwd. Read-only.
#
# Every assertion DERIVES its expected value from the module and then checks
# that the docs agree. No expected value is written down here: a literal in this
# script would be a second copy of the tree, drifting independently of the
# first. Rule: `doc/coding_guidelines.rst` §1.4. Rationale: ADR-0043. Modelled
# on `approval/machine_doc_v1/factcheck.sh`, which this repo shipped until
# `7e468c4f8` handed Base Approval to `odoo/addons`.
#
# WHY THIS MODULE NEEDS ONE. Two reasons, both measured rather than assumed.
#
# 1. It already drifted. Until 2026-08-26 `static/lib/README.md`,
#    `static/lib/versions.json` and `machine_doc_v1/architecture.md` all told the
#    reader that the `ol`, `chroma-js` and `geostats` specifiers were registered
#    in `ODOO_EXTERNAL_LIBS` and `EXTERNAL_BARE_SPECIFIERS`. Odoo `491b6c0f3bb`
#    (2026-08-16) deleted both names in favour of the manifest's
#    `esm.external_libs` key, so for ten days the documented way to add a library
#    here pointed at two symbols that resolved nowhere.
#
# 2. Vendored version and source pins must agree with the shipped artifacts.
#    The shared `tooling/assets/check_vendored_libs.py` checks the probes and
#    checksums here as well as in web.
#
# Roots come from this script's own location, so a run always validates the tree
# it ships in.

set -euo pipefail
UPDATE=0
[ "${1:-}" = "--update" ] && UPDATE=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_fc_root="$SCRIPT_DIR"
while [[ "$_fc_root" != "/" && ! -f "$_fc_root/odoo-bin" ]]; do
    _fc_root="$(dirname -- "$_fc_root")"
done
source "$_fc_root/doc/machine_doc/factcheck_env.sh"
MOD="$(dirname "$SCRIPT_DIR")"                  # <repo>/geoengine
LIB="$MOD/static/lib"
VERSIONS="$LIB/versions.json"
DOCS=("$SCRIPT_DIR"/*.md)

fail=0
pass=0
skip=0
unverified=()

ok()   { pass=$((pass + 1)); }
bad()  { fail=$((fail + 1)); printf '  FAIL  %s\n' "$1"; }
note() { skip=$((skip + 1)); printf '  SKIP  %s\n' "$1"; }

# The machine docs must cite a string that was measured from the tree.
assert_doc_cites() {  # <needle> <human description>
    if grep -qF -- "$1" "${DOCS[@]}"; then ok; else bad "docs never cite $2 ($1)"; fi
}

# Same, against one named file anywhere in the module.
assert_file_cites() {  # <path-relative-to-MOD> <needle> <human description>
    if grep -qF -- "$2" "$MOD/$1"; then ok
    else bad "$1 never cites $3 ($2)"; fi
}

assert_file_omits() {  # <path-relative-to-MOD> <needle> <human description>
    if grep -qF -- "$2" "$MOD/$1"; then bad "$1 still cites $3 ($2)"; else ok; fi
}

libs_json() {  # <python expression over the parsed libs mapping, printed>
    "$PY" - "$VERSIONS" "$1" <<'PY'
import json, sys
libs = json.load(open(sys.argv[1]))["libs"]
print(eval(sys.argv[2], {"libs": libs, "sorted": sorted, "len": len}))
PY
}

manifest_key() {  # <dotted key path>
    "$PY" - "$MOD/__manifest__.py" "$1" <<'PY'
import ast, sys
value = ast.literal_eval(open(sys.argv[1]).read())
for part in sys.argv[2].split("."):
    value = value.get(part, {}) if isinstance(value, dict) else {}
if isinstance(value, dict):
    print(" ".join(f"{k}={v}" for k, v in sorted(value.items())))
elif isinstance(value, list):
    print(" ".join(value))
else:
    print(value)
PY
}

printf '== geoengine machine_doc_v1 factcheck ==\n'

# ---------------------------------------------------------------- structure --
for f in index.md architecture.md models.md conventions.md; do
    [ -f "$SCRIPT_DIR/$f" ] && ok || bad "missing $f"
done
[ -f "$VERSIONS" ] && ok || bad "missing static/lib/versions.json"
[ -f "$LIB/README.md" ] && ok || bad "missing static/lib/README.md"

# ----------------------------------------------------------------- manifest --
dependencies="$(manifest_key depends)"
for dep in $dependencies; do
    assert_doc_cites "$dep" "dependency $dep"
done

# ------------------------------------------------------- ESM registration ----
# The rot this harness exists for. Three properties, each derived:
#
#   a) every specifier the manifest declares is documented in the lib README;
#   b) every URL it declares resolves to a file that is actually shipped —
#      an import-map external that 404s takes the map view down with a bare
#      module-resolution error and no server-side trace;
#   c) the manifest and versions.json agree on the specifier set, so neither
#      can gain a library the other has never heard of.
declare -A declared=()
external_libs="$(manifest_key esm.external_libs | tr ' ' '\n')"
while IFS= read -r pair; do
    [ -z "$pair" ] && continue
    spec="${pair%%=*}"
    url="${pair#*=}"
    declared["$spec"]="$url"

    assert_file_cites "static/lib/README.md" "\`$spec\`" "declared specifier $spec"

    # /geoengine/static/lib/... -> <repo>/geoengine/static/lib/...
    rel="${url#/geoengine/}"
    if [ -f "$MOD/$rel" ]; then ok
    else bad "esm.external_libs['$spec'] points at $url, which ships no file"; fi
done <<< "$external_libs"

if [ "${#declared[@]}" -eq 0 ]; then
    bad "manifest declares no esm.external_libs, but the docs describe three"
else
    ok
fi

manifest_specs="$(printf '%s\n' "${!declared[@]}" | sort | tr '\n' ' ')"
versions_specs="$(libs_json 'sorted(v.get("specifier", k) for k, v in libs.items())' \
    | tr -d "[]',")"
if [ "$(echo "$manifest_specs" | xargs)" = "$(echo "$versions_specs" | xargs)" ]; then ok
else bad "manifest specifiers ($manifest_specs) disagree with versions.json ($versions_specs)"; fi

# The two framework symbols that used to own registration were deleted by odoo
# `491b6c0f3bb`. The machine docs must not name them again: a reader following
# either one finds nothing and has no way to reach the real mechanism. The lib
# README is deliberately NOT checked here — it names both, once, in a paragraph
# explaining that they are gone, and that paragraph is what stops the next
# reader "restoring" them.
for sym in ODOO_EXTERNAL_LIBS EXTERNAL_BARE_SPECIFIERS; do
    if grep -qF -- "$sym" "${DOCS[@]}"; then
        bad "machine docs cite $sym, deleted by odoo 491b6c0f3bb"
    else ok; fi
done
assert_file_cites "static/lib/README.md" "esm.external_libs" \
    "the manifest key that replaced them"

# ------------------------------------------------------------ vendored libs --
# The probe loop `versions.json` asks for: re-derive each pinned version from
# the tree rather than trusting the number written beside it.
if "$PY" "$_fc_root/tooling/assets/check_vendored_libs.py" "$LIB"; then ok
else bad "vendored version probes or artifact checksums do not match"; fi
library_report="$("$PY" - "$VERSIONS" <<'PY'
import json, sys
for name, spec in sorted(json.load(open(sys.argv[1]))["libs"].items()):
    print("\x1f".join([
        name,
        str(spec.get("version", "")),
        (spec.get("probe") or {}).get("file", ""),
        spec.get("rebuild", ""),
    ]))
PY
)"
while IFS=$'\x1f' read -r name version probe_file rebuild; do
    [ -z "$name" ] && continue
    dir="$LIB/$name"

    if [ ! -d "$dir" ]; then
        bad "versions.json lists $name, which has no directory under static/lib"
        continue
    fi
    ok

    # Every pinned version must appear in the README inventory table.
    assert_file_cites "static/lib/README.md" "$version" "$name's pinned version"

    # A lib that declares a rebuild script must ship it, executable: the
    # artifact is generated, and a missing build.sh makes it unreproducible.
    if [ -n "$rebuild" ]; then
        if [ -x "$dir/$rebuild" ]; then ok
        else bad "$name declares rebuild '$rebuild', which is missing or not executable"; fi
    fi

    if [ -z "$probe_file" ]; then
        note "$name: no probe — nothing to re-derive"
        unverified+=("$name")
        continue
    fi
done <<< "$library_report"

# Reverse: a directory shipping a library that versions.json has never heard of
# is an unpinned dependency with no licence record and no upgrade procedure.
for dir in "$LIB"/*/; do
    name="$(basename "$dir")"
    if [ "$(libs_json "'$name' in libs")" = "True" ]; then ok
    else bad "static/lib/$name ships a library absent from versions.json"; fi
done

# Every vendored library must carry its upstream licence next to it.
for dir in "$LIB"/*/; do
    name="$(basename "$dir")"
    if compgen -G "$dir/LICENSE*" > /dev/null; then ok
    else bad "static/lib/$name ships no LICENSE file"; fi
done

# ------------------------------------------------------- restated figures ----
# Every `path.js` (N lines) and every | `path` | N | row is DERIVED here, never
# read. Measured 2026-08-26: 81 of the 82 such figures in these documents were
# wrong, several by more than 30%, and five named files that had been renamed --
# geoengine/CLAUDE.md was already telling readers to treat a number here as
# unverified, which is a warning label where a gate belongs.
#
# A line count moves whenever anyone edits the file, so asserting it alone would
# turn every code change into a doc chore and the gate into something people
# route around. `--update` rewrites them instead, the way odoo's
# doc_restated_counts.py does for the architecture pages: the gate is what
# notices, the flag is what fixes.
#
#     bash machine_doc_v1/factcheck.sh --update
figures_report=$("$PY" - "$SCRIPT_DIR" "$MOD" "$UPDATE" <<'PY'
import pathlib, re, sys

doc_dir, mod, update = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3] == "1"

index = {}
for path in mod.rglob("*"):
    if path.is_file() and path.suffix in (".js", ".py", ".scss"):
        index.setdefault(path.name, []).append(path)

PROSE = re.compile(r"`([A-Za-z0-9_./-]+\.(?:js|py|scss))`(\s*\()(\d[\d,]*)( lines\))")
ROW = re.compile(r"(^\| `([A-Za-z0-9_./-]+\.(?:js|py|scss))` \| )(\d[\d,]*)( \|)", re.M)

def real_lines(name):
    hits = index.get(pathlib.PurePath(name).name)
    if not hits:
        return None
    # Prefer a hit whose tail matches the cited path, so `renderer/x.js` and a
    # same-named file elsewhere cannot be confused for one another.
    for hit in hits:
        if str(hit).endswith(name):
            return len(hit.read_text().splitlines())
    return len(hits[0].read_text().splitlines())

for doc in sorted(doc_dir.glob("*.md")):
    text = original = doc.read_text()

    def fix(match, name_group, num_group, rebuild):
        name = match.group(name_group)
        claimed = int(match.group(num_group).replace(",", ""))
        actual = real_lines(name)
        if actual is None:
            print(f"BAD|{doc.name} states a line count for {name}, which resolves to no file")
            return match.group(0)
        if actual == claimed:
            print(f"OK|{name}")
            return match.group(0)
        if update:
            print(f"UPD|{doc.name}: {name} {claimed} -> {actual}")
            return rebuild(match, f"{actual:,}" if claimed > 999 or actual > 999 else str(actual))
        print(f"BAD|{doc.name} says {name} is {claimed} lines; it is {actual}")
        return match.group(0)

    text = PROSE.sub(lambda m: fix(m, 1, 3, lambda mm, v: f"`{mm.group(1)}`{mm.group(2)}{v}{mm.group(4)}"), text)
    text = ROW.sub(lambda m: fix(m, 2, 3, lambda mm, v: f"{mm.group(1)}{v}{mm.group(4)}"), text)

    if update and text != original:
        doc.write_text(text)
PY
)
while IFS='|' read -r verdict detail; do
    [ -z "$verdict" ] && continue
    case "$verdict" in
        OK)  ok ;;
        UPD) printf '  UPDATED  %s\n' "$detail"; ok ;;
        *)   bad "$detail" ;;
    esac
done <<< "$figures_report"

# --------------------------------------------------- backticked path sweep ---
# A backticked path asserts that one particular file exists. A deliberately-
# absent file, or one in a sibling checkout, is named in PLAIN PROSE instead --
# the rule odoo/CLAUDE.md states and applies to itself. This repo's CI checks
# out alone, so sibling-checkout paths cannot be resolved by this gate.
# Framework paths under odoo/ are local now that geoengine lives in core.
path_report=$("$PY" - "$SCRIPT_DIR" "$MOD" <<'PY'
import pathlib, re, sys

doc_dir, mod = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
repo = mod.parent.parent if mod.parent.name == "addons" else mod.parent
TOKEN = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|xml|js|md|csv|sh|scss|json))`")
SIBLINGS = ("enterprise/", "l10n/", "design-themes/", "agromarin-knowledge/")

# The tree under test must be findable, or every path reads as dead and the
# sweep reports a wall of false failures. A gate that fails on everything is
# read as broken and ignored, which costs as much as one that passes on
# everything.
if not (mod / "__manifest__.py").exists():
    print("BAD|module root misresolved (no __manifest__.py at %s) -- sweep would be blind" % mod)
    raise SystemExit(0)

docs = list(doc_dir.glob("*.md")) + [mod / "static" / "lib" / "README.md"]
for doc in sorted(d for d in docs if d.exists()):
    for token in sorted({m.group(1) for m in TOKEN.finditer(doc.read_text())}):
        if token.startswith(SIBLINGS):
            print(f"BAD|{doc.name} backticks {token}, which lives in a sibling "
                  f"checkout this repo's CI does not have -- name it in plain prose")
            continue
        # A root-relative asset URL (/geoengine/static/...) is a URL, not a path.
        probe = token.lstrip("/")
        if probe.startswith("geoengine/"):
            probe = probe[len("geoengine/"):]
        if any((base / probe).exists() for base in (doc_dir, mod, repo)):
            print(f"OK|{token}")
        elif list(mod.rglob(pathlib.PurePath(probe).name)):
            print(f"OK|{token}")
        else:
            print(f"BAD|{doc.name} backticks {token}, which resolves to no file "
                  f"in this module")
PY
)
while IFS='|' read -r verdict detail; do
    [ -z "$verdict" ] && continue
    [ "$verdict" = "OK" ] && ok || bad "$detail"
done <<< "$path_report"

# ------------------------------------------------------------------ summary --
# A pin with no probe passes nothing; saying "green" without naming it would let
# an unverifiable version read as a checked one. odoo's check_vendored_libs.py
# ends the same way, and for the same reason.
printf '\n%d passed, %d failed, %d skipped\n' "$pass" "$fail" "$skip"
if [ "${#unverified[@]}" -gt 0 ]; then
    printf '%d pinned version(s) NOT verified: %s\n' \
        "${#unverified[@]}" "$(printf '%s, ' "${unverified[@]}" | sed 's/, $//')"
    printf '  Do not read this run as a clean result for those.\n'
fi
[ "$fail" -eq 0 ] || exit 1
