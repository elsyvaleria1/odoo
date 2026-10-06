#!/usr/bin/env bash
# The web bundle-size budgets (test_web_bundle_size.py) on the install they are
# calibrated for, in a scratch database created and dropped here.
#
#   addons/web/tests/bundle_size.sh                    check every budget
#   addons/web/tests/bundle_size.sh --update-baseline  rewrite the per-input baseline
#   addons/web/tests/bundle_size.sh --keep             keep the database
#
# The install is TestWebBundleSize.CALIBRATION_ROOTS on the narrow addons path:
# an input from another repository would make the bundle one no budget describes.
set -u

usage() { sed -n '2,10p' "$0"; exit 2; }

KEEP=0 UPDATE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --keep) KEEP=1 ;;
        --update-baseline) UPDATE=1 ;;
        -h|--help) usage ;;
        *) echo "unknown option: $1" >&2; usage ;;
    esac
    shift
done

CHECKOUT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PYTHON="${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/}python"
DB="bundle_size_${USER:-ci}_$$"
DATA_DIR="$(mktemp -d "${TMPDIR:-/tmp}/bundle_size.XXXXXX")"
ROOTS="$("$PYTHON" - "$CHECKOUT/addons/web/tests/test_web_bundle_size.py" <<'EOF'
import ast, sys
tree = ast.parse(open(sys.argv[1]).read())
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and any(
        getattr(target, "id", None) == "CALIBRATION_ROOTS" for target in node.targets
    ):
        print(",".join(sorted(ast.literal_eval(node.value.args[0]))))
EOF
)"
[ -n "$ROOTS" ] || { echo "bundle_size.sh: no CALIBRATION_ROOTS found" >&2; exit 1; }

cleanup() {
    if [ "$KEEP" -eq 1 ]; then
        echo "kept database $DB (data dir $DATA_DIR)"
        return
    fi
    dropdb --if-exists "$DB"
    rm -rf "$DATA_DIR"
}
trap cleanup EXIT

EXTRA_ENV=()
[ "$UPDATE" -eq 1 ] && EXTRA_ENV=(ODOO_BUNDLE_SIZE_UPDATE_BASELINE=1)

createdb "$DB" || exit 1
env "${EXTRA_ENV[@]}" "$PYTHON" "$CHECKOUT/odoo-bin" \
    --addons-path="$CHECKOUT/odoo/addons,$CHECKOUT/addons" --data-dir="$DATA_DIR" \
    -d "$DB" --db-filter="^$DB\$" -i "$ROOTS" --without-demo=all --test-enable \
    --test-tags /web:TestWebBundleSize --stop-after-init --workers=0 \
    --max-cron-threads=0 --no-http --log-level=info
