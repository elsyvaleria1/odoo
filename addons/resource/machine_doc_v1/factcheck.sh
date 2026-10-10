#!/bin/bash
# resource machine-doc fact-check. Run from any cwd. Read-only.
#
# Every assertion derives its expected value from the tree and then checks that
# the docs agree; no literal here is a second copy of the tree (rule:
# doc/coding_guidelines.rst §1.4). The mixins' hook contracts are method names
# hosts override by convention, which nothing in Python checks, so the models,
# every field, the mixin methods, the hosts in this checkout and the test files
# are gated.

set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_fc_root="$SCRIPT_DIR"
while [[ "$_fc_root" != "/" && ! -f "$_fc_root/odoo-bin" ]]; do
    _fc_root="$(dirname -- "$_fc_root")"
done
# shellcheck source=/dev/null
source "$_fc_root/doc/machine_doc/factcheck_env.sh"

MOD="$(dirname "$SCRIPT_DIR")"                  # <repo>/addons/resource
ADDONS="$(dirname "$MOD")"

fail=0
pass=0

ok()  { pass=$((pass + 1)); }
bad() { fail=$((fail + 1)); printf '  FAIL  %s\n' "$1"; }

assert_cited_in() {  # <file> <needle> <human description>
    if grep -qF -- "$2" "$SCRIPT_DIR/$1"; then ok
    else bad "$1 never cites $3 ($2)"; fi
}
manifest_key() {
    "$PY" - "$MOD/__manifest__.py" "$1" <<'PY'
import ast, sys
manifest = ast.literal_eval(open(sys.argv[1]).read())
value = manifest.get(sys.argv[2])
print(" ".join(value) if isinstance(value, list) else value)
PY
}

printf '== resource machine_doc_v1 factcheck ==\n'

for f in index.md MODEL_MAP.md; do
    [ -f "$SCRIPT_DIR/$f" ] && ok || bad "missing $f"
done

# ----------------------------------------------------------------- manifest --
version="$(manifest_key version)"
assert_cited_in index.md "| Version | $version |" "the manifest version"
for dep in $(manifest_key depends); do
    assert_cited_in index.md "\`$dep\`" "dependency $dep"
done

# ------------------------------------------------------------------- models --
mapfile -t declared < <(grep -rhoP '^\s+_name = "\K[^"]+' "$MOD"/models | sort -u)
for model in "${declared[@]}"; do
    assert_cited_in MODEL_MAP.md "## $model" "model $model"
done
mapfile -t documented < <(grep -oP '^## \K[a-z][a-z._]*' "$SCRIPT_DIR/MODEL_MAP.md" | sort -u)
for model in "${documented[@]}"; do
    if printf '%s\n' "${declared[@]}" | grep -qxF "$model"; then ok
    else bad "MODEL_MAP.md documents $model, which the module does not declare"; fi
done
# an AbstractModel extending another module's (base) declares no model of its own
abstract="$(grep -lP 'models\.AbstractModel' "$MOD"/models/*.py \
    | xargs grep -lP '^\s+_name = "' | wc -l)"
concrete=$(( ${#declared[@]} - abstract ))
assert_cited_in index.md "| Models | ${#declared[@]} ($concrete concrete, $abstract abstract) |" \
    "the model count"

# ------------------------------------------------------------------- fields --
while read -r field; do
    [ -z "$field" ] && continue
    assert_cited_in MODEL_MAP.md "\`$field\`" "field $field"
done < <(grep -hoP '^    \K[a-z_][a-z0-9_]*(?= = fields\.[A-Z])' "$MOD"/models/*.py | sort -u)

# --------------------------------------------------------------- mixin hooks --
for mixin in mixin_resource_scheduling mixin_resource_ledger mixin_resource_scheduling_tools; do
    for name in $(grep -hoP '^    def \K_[a-z_]+(?=\()' "$MOD/models/$mixin.py" | sort -u); do
        assert_cited_in MODEL_MAP.md "\`$name\`" "$mixin method $name"
    done
done

# -------------------------------------------------------------------- hosts --
# Every model in this checkout whose _inherit names one of the mixins, outside
# resource itself, is a host index.md names; a host added anywhere moves this.
hosts="$(py_capture - "$ADDONS" <<'PY'
import ast, pathlib, sys
addons = pathlib.Path(sys.argv[1])
mixins = ("mixin.resource", "mixin.resource.scheduling", "mixin.resource.allocation")
for path in sorted(addons.glob("*/models/*.py")):
    if path.parts[-3] == "resource":
        continue
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        continue
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        name = inherit = None
        for node in cls.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                try:
                    value = ast.literal_eval(node.value)
                except ValueError:
                    continue
                if node.targets[0].id == "_name":
                    name = value
                elif node.targets[0].id == "_inherit":
                    inherit = value if isinstance(value, list) else [value]
        host = name or (inherit[0] if inherit else None)
        for mixin in mixins:
            if inherit and mixin in inherit and host not in mixins:
                print(f"{mixin} {host} {path.parts[-3]}")
PY
)"
for mixin in mixin.resource mixin.resource.scheduling mixin.resource.allocation; do
    count="$(printf '%s\n' "$hosts" | grep -c "^$mixin ")"
    assert_cited_in index.md "| \`$mixin\` hosts in this checkout | $count |" "the $mixin host count"
done
while read -r _mixin host module; do
    [ -z "$host" ] && continue
    assert_cited_in index.md "\`$host\` ($module)" "host $host"
done <<< "$hosts"

# -------------------------------------------------------------------- tests --
for f in "$MOD"/tests/test_*.py "$MOD"/static/tests/*.test.js; do
    assert_cited_in index.md "$(basename "$f")" "test file $(basename "$f")"
done

printf '%s\n' "================================================================"
printf 'TOTAL: %d passed, %d failed\n' "$pass" "$fail"
printf '%s\n' "================================================================"
[ "$fail" -eq 0 ]
