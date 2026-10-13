#!/bin/bash
# doc/architecture fact-check. Run from any cwd. Read-only.
#
# The architecture pages state figures the tree can answer -- how many mixins
# compose BaseModel, the loader's phases, the service defaults an operator
# sizes a deployment from. Since `tooling/` went (2026-09-11)
# nothing failed when one drifted, and one did: module.md and gates.md said
# "seven statements" for two days after 99b81f3472ed ported two of them.
#
# Every expected value is DERIVED here, from the code, and the pages must
# cite it. No literal in this
# file (doc/coding_guidelines.rst §1.4). A dated figure ("31 on 2026-09-11") is
# frozen, not gated, and is not checked here.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/../machine_doc/factcheck_env.sh"
ROOT="$FACTCHECK_ROOT"

fail=0
pass=0
ok()  { pass=$((pass + 1)); }
bad() { fail=$((fail + 1)); printf '  FAIL  %s\n' "$1"; }

printf '== doc/architecture factcheck ==\n'

# The pages this harness knows about, checked BOTH ways. `tooling/`'s
# test_architecture_doc.py read every .md in the directory as one document and
# failed if its list and the directory disagreed in either direction, so a new
# view could not land unpinned; it went on 2026-09-11 and this harness, written
# on 2026-09-15 to replace it, was born two pages short -- deployment.md and
# scenarios.md had been in the directory since 2026-08-07 and are in no list
# here. Only the forward direction was rebuilt, and the forward direction is
# the half that cannot notice.
PAGES="ARCHITECTURE.md authentication-clients.md data.md deployment.md gates.md module.md qualities.md risks.md runtime.md scenarios.md uom.md"

for f in $PAGES; do
    [ -f "$SCRIPT_DIR/$f" ] && ok || bad "$f is in this harness's list and not in doc/architecture/"
done
for path in "$SCRIPT_DIR"/*.md; do
    name="$(basename "$path")"
    case " $PAGES " in
        *" $name "*) ok ;;
        *) bad "$name is in doc/architecture/ and in no list here; add it, and gate whatever figures it states" ;;
    esac
done

# Each line: LABEL|value|page|regex the page must match, with @ standing for
# the value spelled as the page spells it (digits, or the number word).
report=$(cd "$ROOT" && "$PY" - "$SCRIPT_DIR" <<'PY'
import ast, pathlib, re, sys

sys.path.insert(0, ".")
import odoo.init  # noqa: F401  # the interpreter floor and the native build
from odoo.orm.models.base import BaseModel
from odoo.db import cursor
from odoo.orm.runtime import _registry_signaling as signaling
from odoo.orm.runtime import transaction
from odoo.service import transaction as transaction_svc

pages = pathlib.Path(sys.argv[1])
WORDS = dict(enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()
))

def spelled(value):
    return {str(value), WORDS.get(value, "")} - {""}

def cite(label, value, page, pattern):
    text = (pages / page).read_text()
    for form in spelled(value):
        if re.search(pattern.replace("@", re.escape(form)), text):
            print(f"OK|{label}")
            return
    print(f"BAD|{page} does not cite {label} = {value} ({pattern})")

bases = BaseModel.__bases__
public = sum(1 for b in bases if not b.__name__.startswith("_"))
private = len(bases) - public
cite("BaseModel mixins", len(bases), "module.md", r"BaseModel \+ @ mixins")
cite("BaseModel mixins (prose)", len(bases), "module.md", r"composed from @ `__slots__ = \(\)` mixins")
cite("public mixins", public, "module.md", r"@ public \(`CreateMixin`")
cite("private mixins", private, "module.md", r"plus @ private")

# module.md's façade paragraph counts what tools/__init__.py takes straight
# from odoo.libs. It named the `__all__` total beside it too, which drifted
# from the tree while nothing read it, and now names none.
tools_init = ast.parse(pathlib.Path("odoo/tools/__init__.py").read_text())
imported_from = {
    alias.asname or alias.name: node.module or ""
    for node in tools_init.body
    if isinstance(node, ast.ImportFrom) and not node.level
    for alias in node.names
}
tools_all = next(
    node.value
    for node in tools_init.body
    if isinstance(node, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
)
from_libs = sum(
    1
    for element in tools_all.elts
    if imported_from.get(element.value, "").startswith("odoo.libs")
)
cite(
    "tools re-exports straight from libs",
    from_libs,
    "module.md",
    r"re-exports \*\*@ of its `__all__` symbols straight from",
)

auth_event = {
    node.targets[0].id: node.value.value
    for node in ast.parse(pathlib.Path("odoo/addons/base/models/auth_event.py").read_text()).body
    if isinstance(node, ast.Assign)
    and isinstance(node.targets[0], ast.Name)
    and isinstance(node.value, ast.Constant)
}
cite(
    "event retention default",
    auth_event["RETENTION_DAYS_DEFAULT"],
    "authentication-clients.md",
    r"defaults to @ days",
)
cite(
    "event expiry batch",
    auth_event["EXPIRY_BATCH_SIZE"],
    "authentication-clients.md",
    r"at most @ oldest events",
)

# data.md's diagram counts the signalling tables. They are generated from a
# cache list rather than written down, so the page cannot be read off the
# source by eye: it said 8 from the day it was written (2026-08-07) while the
# list moved two days later, and the comment beside the definition has said
# "eleven watermarks" ever since.
cite("signalling tables", len(signaling.SIGNALING_TABLES), "data.md", r"\(@ of them\)")
# runtime.md states the same count as the width of the sequence read. Found by
# asking, of every figure gated here, which other page states its value near
# its own subject -- the generalisation of runtime.md citing scenarios.md.
# (`_registry_signaling.py`'s own comment, "the eleven watermarks", is a third
# statement of it, in source prose this harness does not read.)
cite(
    "signalling tables (runtime.md)",
    len(signaling.SIGNALING_TABLES),
    "runtime.md",
    r"@ sequence reads",
)

# qualities.md's contention scenario names the retry budget and the back-off
# curve it describes. They are constants, not measurements -- the 2026-08-28
# stamp on that scenario belongs to its throughput table -- so they are gated
# and not frozen. `\s*` because the page wraps between the name and the value.
cite(
    "retry budget",
    transaction_svc.MAX_TRIES_ON_CONCURRENCY_FAILURE,
    "qualities.md",
    r"`MAX_TRIES_ON_CONCURRENCY_FAILURE`\s*\(@\)",
)
cite(
    "back-off base",
    transaction_svc.BASE_CONCURRENCY_BACKOFF_SECONDS,
    "qualities.md",
    r"`BASE_CONCURRENCY_BACKOFF_SECONDS`\s*\(@\)",
)
cite(
    "back-off ceiling",
    transaction_svc.MAX_CONCURRENCY_BACKOFF_SECONDS,
    "qualities.md",
    r"`MAX_CONCURRENCY_BACKOFF_SECONDS`\s*\(@\)",
)

# scenarios.md numbers the load it considers worth naming and says how many
# it left out. `restore_relations_dropped_by_migrations` landed on 2026-09-20
# and appeared in neither table for a day: the page said 23 calls where the
# loader made 24, which is the drift the deleted test_architecture_doc.py
# would have caught the moment a phase was added.
loading = ast.parse((pathlib.Path("odoo/modules/loading.py")).read_text())
load_modules = next(
    n for n in ast.walk(loading)
    if isinstance(n, ast.FunctionDef) and n.name == "load_modules"
)
phases = [
    n.func.attr for n in ast.walk(load_modules)
    if isinstance(n, ast.Call)
    and isinstance(n.func, ast.Attribute)
    and isinstance(n.func.value, ast.Name)
    and n.func.value.id == "loader"
]
scenarios = (pages / "scenarios.md").read_text()
tabled = re.findall(r"^\| \d+ \| `([a-z_]+)\(\)`", scenarios, re.M)
# The left-out table only, and only its first column: its second column
# cites names of its own (`at_install`), and a later table on the page lists
# the migration script kinds (`pre`, `post`, `end`) in the same shape.
lines = scenarios.splitlines()
first = next(i for i, l in enumerate(lines) if "left out split two ways" in l)
after = next(
    (i for i, l in enumerate(lines[first + 1 :], first + 1) if l.strip() and not l.startswith("|")),
    len(lines),
)
left_out = [
    name
    for line in lines[first:after]
    if line.startswith("| `")
    for name in re.findall(r"`([a-z_]+)`", line.split("|")[1])
]
cite("load_modules phases", len(phases), "scenarios.md", r"`load_modules`' @ calls")
cite("load_modules phases tabled", len(tabled), "scenarios.md", r"(?i)@ of `load_modules`")
cite("load_modules phases left out", len(phases) - len(tabled), "scenarios.md", r"The @ left out")
# runtime.md states the same loader total for its own sketch, and tells the
# reader how many scenarios.md selects. The second is a page citing a page:
# correcting scenarios.md's table from thirteen to fourteen left runtime.md
# saying thirteen, and a gate that reads one page cannot see that.
cite("load_modules phases (runtime.md)", len(phases), "runtime.md", r"of the @ `loader\.\*` calls")
cite("load_modules phases (runtime.md prose)", len(phases), "runtime.md", r"Every one of the @ is")
cite("scenarios' selection as runtime.md cites it", len(tabled), "runtime.md", r"selects @")

cite(
    "fixpoint ceiling",
    transaction.MAX_FIXPOINT_ITERATIONS,
    "runtime.md",
    r"MAX_FIXPOINT_ITERATIONS \(@\)",
)
cite(
    "flush passes",
    cursor.BaseCursor._MAX_FLUSH_PASSES,
    "runtime.md",
    r"_MAX_FLUSH_PASSES \(@\)",
)

# deployment.md states the defaults an operator sizes a deployment from. Each
# text is built from the live constant, so a default that moves becomes a
# string the page does not hold.
import os
from unittest.mock import patch
from odoo.release import MIN_PG_VERSION
from odoo.service import _limits, _prefork, _threaded, _worker, httpd, lifecycle
from odoo.service import settings as server_settings
from odoo.service._prefork import _EXIT_OUTCOMES
from odoo.service._transport import TransportLimits, get_http_socket_timeout

MIB = 1024 * 1024
deployment = (pages / "deployment.md").read_text()

def bus_constant(name, module="websocket.py"):
    # bus is an addon, outside the core this script imports: read its module
    # source for the constant instead, class attributes included.
    import ast

    tree = ast.parse((pages / "../../addons/bus" / module).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == name for t in node.targets
        ):
            return eval(compile(ast.Expression(node.value), module, "eval"), {"__builtins__": {}})
    raise LookupError(name)


def bus_notify_payload_default():
    import ast

    tree = ast.parse((pages / "../../addons/bus/models/bus.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "get_notify_payload_max_length":
            return node.args.defaults[0].value
    raise LookupError("get_notify_payload_max_length")


def contains(label, text):
    print(f"OK|{label}" if text in deployment else f"BAD|deployment.md does not state {label} ({text!r})")

s = server_settings.ServerSettings()
with patch.dict(os.environ, {}, clear=False), server_settings.override(test_enable=False):
    for name in [n for n in os.environ if n.startswith("ODOO_HTTP_")]:
        del os.environ[name]
    lim, socket_timeout = TransportLimits.from_environment(), get_http_socket_timeout()
beat = int(_prefork.SUPERVISION_BEAT_S)
for label, text in {
    "workers": f"| `workers` | `{s.workers}` |",
    "max_cron_threads": f"| `max_cron_threads` | `{s.max_cron_threads}` |",
    "limit_request": f"| `limit_request` | `{s.limit_request}` |",
    "limit_memory_soft": f"| `limit_memory_soft` | `{s.limit_memory_soft // MIB} MB` |",
    "limit_time_cpu": f"| `limit_time_cpu` | `{s.limit_time_cpu} s` |",
    "limit_time_real": f"| `limit_time_real` | `{s.limit_time_real} s` |",
    "limit_time_real_module_operation": f"| `limit_time_real_module_operation` | `{s.limit_time_real_module_operation}` |",
    "limit_time_worker_cron": f"| `limit_time_worker_cron` | `{s.limit_time_worker_cron}` |",
    "db_maxconn": f"| `db_maxconn` | `{s.db_maxconn}` |",
    "_CANCEL_GRACE_S": f"`_CANCEL_GRACE_S` ({int(_worker.Worker._CANCEL_GRACE_S)} s)",
    "SUPERVISION_BEAT_S": f"`SUPERVISION_BEAT_S` ({beat} s)",
    "the master's beat in prose": f"The prefork master's beat is {beat} s",
    "DESCRIPTOR_HEADROOM": f"`DESCRIPTOR_HEADROOM` ({lifecycle.DESCRIPTOR_HEADROOM})",
    "graceful stop bound": f"`ODOO_GRACEFUL_STOP_TIMEOUT`, {int(_limits.GRACEFUL_STOP_TIMEOUT_S)} s",
    "listener join floor": f"(at least {int(_threaded.LISTENER_JOIN_TIMEOUT_S)} s)",
    "MIN_PG_VERSION": f"`MIN_PG_VERSION` (`odoo/release.py`) is {MIN_PG_VERSION}",
    "socket timeout": f"| `ODOO_HTTP_SOCKET_TIMEOUT` | `{int(socket_timeout)} s`",
    "head timeout": f"| `ODOO_HTTP_HEAD_TIMEOUT` | `{int(lim.head_timeout)} s` |",
    "keepalive timeout": f"| `ODOO_HTTP_KEEPALIVE_TIMEOUT` | `{int(lim.keepalive_timeout)} s` |",
    "idle connections": f"| `ODOO_HTTP_MAX_IDLE_CONNECTIONS` | `{lim.max_idle_connections}` |",
    "drain bytes": f"| `ODOO_HTTP_DRAIN_BYTES` | `{lim.drain_bytes // MIB} MiB` |",
    "max queue": f"| `ODOO_HTTP_MAX_QUEUE` | `max({httpd.MIN_QUEUE}, {httpd.QUEUE_PER_THREAD} × ODOO_MAX_HTTP_THREADS)` |",
    "body timeout": f"| `ODOO_HTTP_BODY_TIMEOUT` | `{int(lim.body.timeout)} s` |",
    "body min rate": f"| `ODOO_HTTP_BODY_MIN_RATE` | `{int(lim.body.min_rate)} B/s` |",
    "websocket cap": f"| `ODOO_WEBSOCKET_MAX_CONNECTIONS` | `{_limits.WEBSOCKET_MAX_CONNECTIONS}` |",
    "websocket descriptors": f"`WEBSOCKET_DESCRIPTORS` ({_limits.WEBSOCKET_DESCRIPTORS}:",
    "websocket drain timeout": f"| `ODOO_WEBSOCKET_DRAIN_TIMEOUT` | `{bus_constant('DRAIN_TIMEOUT'):g} s` |",
    "websocket drain timeout in prose": f"`ODOO_WEBSOCKET_DRAIN_TIMEOUT`\n({bus_constant('DRAIN_TIMEOUT'):g} s)",
    "websocket lane depth": f"at most {bus_constant('LANE_DEPTH')} queued frames",
    "notify payload cap": f"| `ODOO_NOTIFY_PAYLOAD_MAX_LENGTH` | `{bus_notify_payload_default()}` |",
    "bus gc retention": f"default\n`{bus_constant('DEFAULT_GC_RETENTION_SECONDS', 'models/bus.py')}` s)",
    "websocket send buffer": f"kernel send buffer is capped at {bus_constant('SEND_BUFFER') // 1024} KiB",
    "websocket write buffer limit": f"more than {bus_constant('WRITE_BUFFER_LIMIT') // 1024} KiB its client has not read",
    "websocket outbound limit": f"while the process holds {bus_constant('OUTBOUND_LIMIT', 'tools/websocket_hub.py') // MIB} MiB",
    "websocket write stall": f"whose client takes nothing for {bus_constant('WRITE_STALL_TIMEOUT')} s is cut",
    "websocket write stall metric": f"for taking nothing for {bus_constant('WRITE_STALL_TIMEOUT')} s while bytes waited",
    "websocket db threads floor": f"| `ODOO_WEBSOCKET_DB_THREADS` | `max({_limits.WEBSOCKET_MIN_DB_THREADS}, ",
}.items():
    contains(label, text)

# The worker-exit metric's row, both ways: an outcome the page omits is one
# nobody alerts on, and one the metric cannot emit is an alert that never fires.
row = next((l for l in deployment.splitlines() if "`odoo_worker_exits_total`" in l), "")
documented = set(re.findall(r"`([a-z_]+)`", row)) - {"odoo_worker_exits_total", "outcome"}
missing = sorted(set(_EXIT_OUTCOMES) - documented)
stale = sorted(documented - set(_EXIT_OUTCOMES))
print("OK|worker exit outcomes documented" if row and not missing else f"BAD|deployment.md omits worker exit outcomes: {missing}")
print("OK|no worker exit outcome the metric cannot emit" if not stale else f"BAD|deployment.md lists outcomes the metric cannot emit: {stale}")

unknown = sorted(set(tabled + left_out) - set(phases))
print(
    f"OK|every phase scenarios.md names is a loader call"
    if not unknown
    else f"BAD|scenarios.md names phases load_modules does not call: {unknown}"
)
unnamed = sorted(set(phases) - set(tabled) - set(left_out))
print(
    "OK|every loader call scenarios.md accounts for"
    if not unnamed
    else f"BAD|load_modules calls phases scenarios.md never names: {unnamed}"
)
PY
) || { bad "the derivation itself failed (see stderr above)"; report=""; }

while IFS='|' read -r verdict detail; do
    [ -z "$verdict" ] && continue
    [ "$verdict" = "OK" ] && ok || bad "$detail"
done <<< "$report"

printf 'doc/architecture: %d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
