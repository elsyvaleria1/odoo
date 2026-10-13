#!/usr/bin/env bash
set -euo pipefail

workspace="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
python="$workspace/p314o19m/bin/python"
odoo_bin="$workspace/odoo/odoo-bin"
config="$workspace/p314o19m.conf"
report_dir="$(mktemp -d "$workspace/.data/method-name-verification.XXXXXXXX")"
export PATH="$workspace/p314o19m/bin:$PATH"
export ODOO_REQUIRE_INFRA=1
export ODOO_CONTRACT_REQUIRE_DEPS=1

echo "Verification logs: $report_dir"

# Fail before creating a test database if this execution context denies sockets.
"$python" - 2>&1 <<'PY' | tee "$report_dir/preflight.log"
import socket
import psycopg

with socket.socket() as server:
    server.bind(('127.0.0.1', 0))
with psycopg.connect(dbname='postgres', user='marin') as connection:
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
        assert cursor.fetchone() == (1,)
print('Local HTTP sockets and PostgreSQL are available.')
PY

modules=("$@")
if ((${#modules[@]} == 0)); then
    modules=(base web mail bus http_routing rpc test_http test_lint)
fi

for module in "${modules[@]}"; do
    if [[ ! "$module" =~ ^[a-z][a-z0-9_]*$ ]]; then
        echo "Invalid addon name: $module" >&2
        exit 2
    fi
    manifest_found=false
    for addon_root in "$workspace/odoo/odoo/addons" "$workspace/odoo/addons" \
        "$workspace/l10n" "$workspace/agromarin" "$workspace/design-themes" \
        "$workspace/odoo-rust-orm/addons"; do
        if [[ -f "$addon_root/$module/__manifest__.py" ]]; then
            manifest_found=true
            break
        fi
    done
    if [[ "$manifest_found" == false ]]; then
        echo "No addon manifest found for $module" >&2
        exit 2
    fi
    database="codex_names_${module:0:20}_$("$python" -c 'import uuid; print(uuid.uuid4().hex[:20])')"
    psql -U marin -l > "$report_dir/databases-before-$module.txt"
    psql -U marin -d postgres -Atc 'SELECT datname FROM pg_database' > "$report_dir/database-names.txt"
    if rg -Fxq "$database" "$report_dir/database-names.txt"; then
        echo "Refusing an existing database: $database" >&2
        exit 1
    fi
    port="$("$python" - <<'PY'
import socket
with socket.socket() as server:
    server.bind(('127.0.0.1', 0))
    print(server.getsockname()[1])
PY
)"
    echo "Testing $module in $database on port $port"
    test_options=()
    if [[ "$module" == test_lint ]]; then
        test_options=(
            "--addons-path=$workspace/odoo/odoo/addons,$workspace/odoo/addons"
            --load=base,rpc,web
        )
    fi
    if ! "$python" "$odoo_bin" -c "$config" -d "$database" -i "$module" \
        "${test_options[@]}" --test-enable --test-tags "/$module" --http-port "$port" --stop-after-init \
        > "$report_dir/$module.log" 2>&1; then
        tail -80 "$report_dir/$module.log"
        echo "Failed database retained for investigation: $database" >&2
        exit 1
    fi
    if ! rg -q 'of [1-9][0-9]* tests' "$report_dir/$module.log"; then
        echo "No nonzero test summary for $module; inspect $report_dir/$module.log" >&2
        exit 1
    fi
    rg 'failed, .*error\(s\).*of .*tests' "$report_dir/$module.log"
    "$python" "$odoo_bin" db -c "$config" drop "$database" \
        > "$report_dir/$module-cleanup.log" 2>&1
done

cd "$workspace/odoo"
"$python" -m pytest tests/transport tests/contract tests/loading tests/process tests/perf \
    > "$report_dir/framework-tests.log" 2>&1
tail -20 "$report_dir/framework-tests.log"
echo "Requested addon and framework suites passed. Logs: $report_dir"
