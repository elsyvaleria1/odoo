# The gates — what is mechanically enforced, and what that is worth

> Referenced by [`ARCHITECTURE.md`](ARCHITECTURE.md). The architecture is in
> [`module.md`](module.md) and [`runtime.md`](runtime.md); this file is the
> operator's manual for the machinery that keeps them true.

What is enforced is the standard tools on their pinned versions, `test_lint`,
and the DB-backed suites. Every gate runs by hand, from the
repo root: there is no CI and no runner script. Of the dependency rules in
[`module.md`](module.md#dependency-rules), the ORM half of the façade
boundary is `test_lint`'s; the rest are held by review. A
`from odoo... import name` whose module or binding no longer exists surfaces
only when a database loading its importer fails to build its registry.

## Running the checks

The commands, from the repo root with the venv's tools:

```bash
uv pip install --dry-run -r requirements.txt -r requirements-addons.txt \
    -r requirements-dev.txt                    # the venv is the pinned one: "Would make no changes"
ruff check . --no-cache                        # the whole checkout, hard zero
ruff format --check tests/
(cd ../l10n && ruff check . --no-cache)        # each sibling, under its own ruff.toml
(cd ../agromarin && ruff check . --no-cache)
npx oxlint -c oxlint.config.mjs                # whole repo
npx oxfmt --check "**/*.{js,mjs,cjs,scss}"     # whole repo
npx tsc --project tsconfig.json --noEmit       # whole repo
(cd ../l10n && ../odoo/node_modules/.bin/oxlint -c oxlint.config.mjs)   # each sibling
(cd ../l10n && ../odoo/node_modules/.bin/oxfmt --check "**/*.{js,mjs,cjs,scss}")
(cd ../l10n && ../odoo/node_modules/.bin/tsc -p tsconfig.json --noEmit)
(cd ../agromarin && ../odoo/node_modules/.bin/oxlint -c oxlint.config.mjs)
(cd ../agromarin && ../odoo/node_modules/.bin/oxfmt --check "**/*.{js,mjs,cjs,scss}")
(cd ../agromarin && ../odoo/node_modules/.bin/tsc -p tsconfig.json --noEmit)
python odoo/addons/test_lint/lint_source_gates.py   # test_lint's tree scans, no database
python odoo/addons/test_lint/lint_ruff_gates.py     # the ruff fork's E85 rules against test_lint's floors
python odoo-bin -d <db> -i test_lint --test-enable --stop-after-init
bash doc/architecture/factcheck.sh                  # this directory's figures
for h in addons/*/machine_doc_v*/factcheck.sh odoo/addons/*/machine_doc_v*/factcheck.sh \
         odoo/tests/machine_doc_v*/factcheck.sh; do bash "$h" || echo "RED $h"; done
cargo fmt --all --check --manifest-path crates/Cargo.toml
cargo clippy --workspace --manifest-path crates/Cargo.toml -- -D warnings
cargo test --workspace --manifest-path crates/Cargo.toml
```

To judge a revision other than the working tree, run the same commands in
`git worktree add --detach <dir> <rev>` (symlink `node_modules` into it for the
JS tools), then `git worktree remove` it.

`mypy` is measured with mypy alone installed (`ignore_missing_imports`
resolves `lxml`, `psycopg`, `dateutil` to `Any`), never in the shared venv,
over `odoo.orm`, `odoo.db`, `odoo.libs`, `odoo.http`, `odoo.service`,
`odoo.modules`, and separately `odoo.tools`, `odoo.cli`, `odoo.tests`.
Build that bare environment once per pin with the venv's `uv`, and run both
halves with it:

```bash
uv venv --python python3 ~/.cache/odoo-mypy/<pin> && uv pip install --python ~/.cache/odoo-mypy/<pin> mypy==<pin>
~/.cache/odoo-mypy/<pin>/bin/mypy --no-incremental --config-file mypy.ini \
    -p odoo.orm -p odoo.db -p odoo.libs -p odoo.http -p odoo.service -p odoo.modules
~/.cache/odoo-mypy/<pin>/bin/mypy --no-incremental --config-file mypy.ini \
    -p odoo.tools -p odoo.cli -p odoo.tests
```

`<pin>` is the `mypy==` line of `requirements-dev.txt`. `mypy.ini`
holds `odoo.orm` to `disallow_untyped_defs` and `disallow_incomplete_defs`
outside its test trees (0 on 2026-09-22, from 384 that morning): a function
added to the ORM without a complete signature fails the core lane. It holds
`warn_return_any` there too (0 on 2026-10-03, from 82): a function that
declares a type and returns an `Any` fails it; a value from untyped territory
(a psycopg row, the context, a memo dict, a field read by a runtime name) is
declared on a local, not cast. And it holds `disallow_any_generics` (0 on
2026-10-03, from 869 that evening, through a ratchet retired at
zero): a `dict`, `tuple` or `Field` written without its parameters fails the
core lane; a field of any value type is `Field[Any]`. `BaseModel`
declares `env: Environment` (the mixins keep `Any` for their own shortcuts), so
an addon's `self.env` is typed; `odoo-bin stubs -d <db>` writes
`odoo_registry_stubs.pyi` from a live registry and `mypy_registry_plugin.py`
(repo root, standalone so the checker never runs the framework bootstrap)
types every `env["<name>"]` from it. With generated registry types loaded, an
unknown literal model name is an error; dynamic strings retain the base type.
Finite unions of literal names retain the union of their model types and check
every alternative against the generated registry.
On generated recordsets, `mapped()` uses literal field paths to distinguish
scalar lists from related recordsets, including dotted paths and empty paths.
Unknown fields and scalar traversal are errors. Record-valued callbacks retain
their recordset type; dynamic paths and mixed scalar/record callbacks remain
`Any`. Field metadata changes recheck mapped callers in a running daemon.
A literal lookup with missing or empty registry types reports a setup error.
Regenerating the stub rechecks model lookups in the running mypy daemon.
Generated methods preserve staticmethod and classmethod binding, and model
class names avoid the stub's own imported and generated names. Optional
parameter defaults and coroutine methods retain their call semantics. Generated
stubs preserve readable properties and whether they have a setter, without
invoking their getters during generation. Property values remain `Any`. The CLI
stages the complete stub on the destination filesystem before replacing it,
so readers and failed writes preserve the preceding complete snapshot.
Measured on `sale/models` + `stock/models`
against the four-module set's stubs with `check_untyped_defs`: 3 222 readings
without the plugin, 2 854 with it -- 413 attribute complaints resolved, 56
additional diagnostics (a `Char` handed to `dict.get`, a recordset assigned
where an `OrderedSet` was declared, `with_company` given `Any | BaseModel`).
The `with_company` diagnostic was a declaration defect: a company record need
not have the receiver's model. Its input now accepts model records and the
environment's company protocol, while its result retains the receiver's type.
`doc/architecture/factcheck.sh` derives the figures these pages state (mixin
composition, `tools` re-exports, signalling tables, loader phases, service
defaults) from the code, and fails when a page stops citing one.

The module machine docs are checked the same way, by the loop above: every
`addons/*/machine_doc_v*/factcheck.sh`,
`odoo/addons/*/machine_doc_v*/factcheck.sh` and
`odoo/tests/machine_doc_v*/factcheck.sh` the tree holds, so a new harness is
covered the day it lands: a module that adds a model, a file or a test without
its machine doc reddens its harness instead of leaving a red for the next
reader. The harnesses find the venv beside the checkout (`ODOO_VENV_PYTHON`
and `VENV_PY` override it), and `web`'s `prepare_suite` counts need
`ODOO_CONF` set to the `<env>.conf`. In a detached worktree with no sibling
checkouts, assertions about `l10n`, `agromarin` or `design-themes`
report SKIP rather than pass; the repository's own figures are still checked.
A harness whose check needs a named database (`FACTCHECK_DB`) skips without one.
`web`'s bundle-size budgets hold only for the install of
`TestWebBundleSize.CALIBRATION_ROOTS` on the narrow addons path — the roots plus
what the loader installs with them, computed from the registry, so a new
auto-install module joins the set rather than silently skipping the test;
`addons/web/tests/bundle_size.sh` builds that database, and
`--update-baseline` rewrites the per-input baseline its failures are explained
against.

**`test_lint`** (`odoo/addons/test_lint/tests/`) holds the rules no general
linter knows and the pinned ruff fork does not carry: manifest and XML
conventions, the unique constraints that read every model of a repository
(`E8512`, `E8517`), and the gates that read an installed registry. The
per-file Python rules it used to run (SQL-injection shapes, gettext discipline,
N+1 query shapes, record-field order, `orm-import` (`E8508`) and the rest) are
the fork's `E85xx` rules, held to the same floors below. Its floors live in
`odoo/addons/test_lint/tests/floors.json`, one integer per gate;
a gate with no entry is a hard zero. `assert_ratchet` is exact: a count above
the floor fails, and a count below it fails until the floor is lowered in the
same change.
`odoo/addons/test_lint/lint_source_gates.py` runs the same suites without a
database: a test that asks for one
(`get_db_name()`) skips, and every test that reads only the tree runs, against
the same floors and the narrow addons path. The database run still grades
both halves; this one fails a tree scan before a module install is spent on it.
`odoo/addons/test_lint/lint_ruff_gates.py` holds the Odoo rules of the ruff fork
`requirements-dev.txt` pins (`Agro-Marin/ruff`, prefix `E85`, the per-file AST
checks test_lint ran in Python) to the same `floors.json`: each
`lint_<rule name>_<repo>` is the count of `ruff check --select E85` under that
repository's own `ruff.toml`, for this checkout and the sibling `l10n` and
`agromarin`. Vendored code, migration scripts and the link doors are left out on
its command line, not in `ruff.toml`: a stock ruff, as an editor bundles, refuses
an E85 code there. `abolished-method-call` (`E8535`) is counted with every noqa
ignored; `noqa-rationale` (`E8544`) is never suppressed.
`TestViewDepends` reads the installed registry: every SQL-view model
(`_auto = False`, or a `_table_query`) must name in `_depends` every stored
field its SQL reads, as PostgreSQL's view dependencies report them, because a
search flushes only what `_depends` names and otherwise reads the last flushed
value (`coding_guidelines.rst` §2.6). It is a zero rule per repository
(`view_depends_undeclared_{odoo,enterprise,agromarin}`, no floor entry); the
narrow scope installs few SQL views, so grade it on a fuller install
(`odoo/addons/test_lint/lint_full_scope.sh`).
`tests/test_elevation.py` counts per repository the bare `sudo()` calls
(`bare_sudo_<repo>`), the `has_group` checks (`has_group_<repo>`) and the public
model methods — RPC entry points — that write through an elevation without
first asking the caller's own right (`public_elevation_<repo>`); the machine
doc (`odoo/addons/test_lint/machine_doc_v1/index.md`) states what counts as an
elevation, a write and a guard. The enterprise and agromarin floors are read
only where those repositories are on the addons path (`lint_full_scope.sh`).

One database-free pytest suite, `tests/transport` (the HTTP/1.1 parser, the
threaded server and the prefork worker over real sockets; each test must give
back every thread and descriptor it took), and four real-dependency suites run
only when named: `tests/contract` (`ODOO_CONTRACT_REQUIRE_DEPS=1`; PostgreSQL + psql +
pg_dump), `tests/process` (boots real `odoo-bin` processes), `tests/loading`
(installs `base` into a scratch database; pins the loader phase order, the
uninstall reload, migration ordering, migration-stage schema visibility and the
refusal to update a database older than a module's `oldest_upgradable_version`)
and `tests/perf` (`pytest tests/perf --perf-counts-only` for the counts alone,
without the flag for the time floors too;
installs `base` and the four-module set
`sale,purchase,stock,account` into two scratch databases and reads the ORM's
cost on them: statements per `res.partner` create, batch create, write loop,
batch write and `search_fetch`, per `sale.order` create and create+confirm, and
per order entry by a salesman through the form (`odoo.tests.Form`: the
onchanges for a customer and three lines, the save, the confirmation; its time
is the server's, `_bench.ServerClock`, not the form emulation's), as
**exact ratchets** for every measured operation, residual wall time — wall minus
driver, the fastest of the rounds, the median kept beside it — and the warm
`Registry loaded in` as **one-sided
floors** with a 25 % tolerance
(`ODOO_PERF_TOLERANCE`), plus the in-memory tier's cost per create and per
stored compute. The floors are `tests/perf/floors.json`, one machine's,
moved in the same change that moves the count; a reading below a time floor
passes and is the cue to lower it. **A time floor is judged only on a machine
running at the speed it was set on**: every check first times a fixed
interpreter-bound loop (`_bench.calibration_ms`), and above the file's
`calibration_ms` reference plus the tolerance the time floors print "not
judged" instead of failing; statement counts stay exact either way. The same
code read 51 and 127 ms an hour apart as this machine throttled, and dividing
by the calibration over-corrected (the loop slowed 3× where the ORM slowed
1.9×), which is why it gates rather than scales. Every `measure`d flow also
reads `sql_chars`, the characters of SQL text it sends per operation: as
deterministic as the count, so judged on every machine and under `--perf-counts-only`,
but held to a **±10 % band** both ways (an alias or a reordered clause moves it
by a few characters; above the band is red, below it asks for the floor to be
lowered). It catches a query that grows without a statement more: 973d24045b0f
took the document list and count from 39 299 and 37 958 characters to 95 384
and 94 043 with every count unchanged, and only the time floors — not judged in
CI — saw it. Re-read the reference, on a
calm machine, whenever the floors are re-read. Attribute *where* time goes with a
signal-based sampler on the main thread, never cProfile shares or a sampling
thread: `agromarin-knowledge/research/2026-09-22-orm-best-in-class.md` §6).

**DB-backed integration suites** — run against PostgreSQL 18, **each against
its own database**:

```bash
python odoo-bin --addons-path=odoo/addons,addons -d <db> -i <module> \
    --test-enable --test-tags /<module> --stop-after-init
```

The suites run this way: `base` (less the excluded `TestReportsRendering` and
`TestIrModelFieldsTranslation`), `test_http`, `test_orm`, `mrp`, `certificate`,
`stock`, `rpc`, `crm`, `data_recycle`, `mixin_report_sql` with
`test_mixin_report_sql`, `test_read_group`, `test_access_rights`,
`hr_work_entry` with `hr_work_entry_holidays`, `hr_holidays`, `resource` with
`test_resource`, the three `extract` branches, `test_trade` with `test_trade_account`, `approval` with `test_approval`,
`integration_machine_learning`, `project_hr`, `exchange`, `date_range`, `team`, `account`'s chart-of-accounts
classes (`TestAccountCoa`, `TestAccountRoot`, `TestAccountCodeMapping`,
`TestAccountNameDuplication`, `TestAccountCopyAndName`, `TestSplitCodeName`),
`test_performance_compare`, `mail`, `test_mail`, `mail_group` and `mail_speech`.
`rpc`, `mail`, `test_mail`, `mail_group`, `mail_speech`, `test_orm`, `crm`,
`data_recycle`, `test_access_rights`, `stock`, `mrp`, `test_trade`,
`hr_holidays` and `approval` run **with** the HTTP server on a free port: each
carries `HttpCase` classes, and under `--no-http` such a class is an error, not
a skip (`ODOO_REQUIRE_INFRA`; on 2026-10-01 the last nine read 1-9 errors each
that way, and green with the server). The rest run `--no-http`.

**The query-count pins** run as their own lane. For each of `mail`,
`test_mail`, `test_mail_full`, `test_mail_sms`, `test_discuss_full`,
`test_website_modules` and the bundled `test_discuss_full_enterprise`, create a
scratch database through `odoo-bin` (so `db_template` applies) installing that
module alone, run its tests tagged `is_query_count`, and drop the database:

```bash
python odoo-bin -c ../<env>.conf --addons-path odoo/addons,addons --load base,rpc,web \
    -d <scratch> --db-filter '^<scratch>$' -i <module> --test-enable \
    --test-tags is_query_count/<module> --no-http --workers=0 --max-cron-threads=0 \
    --stop-after-init
dropdb <scratch>
```

`test_discuss_full_enterprise` runs with `--test-tags
is_query_count/test_discuss_full`. The tag is derived: every test whose own source calls
`self.assertQueryCount`, plus the classes and methods that assert through a
helper and carry the tag themselves (`TestDiscussFullPerformance`,
`TestInboxPerformance`, `TestMailTrackingDurationMixin`, and
`test_website_modules`' page and `/shop` pins, which count through website's
`_check_url_hot_query`). `test_website_modules` runs twice, without demo data
and `--with-demo`, because its `/shop` pin counts the statements demo data adds
(`preview_variants` on the demo attributes) and each branch holds only on its
own kind of database. `test_mail_sms`, both discuss suites and
`test_website_modules` run with the HTTP server on a free port (their classes
are `HttpCase`, so `--http-port <free port>` in place of `--no-http`), the rest
`--no-http`. A suite that ran no test is red.
**Each suite gets a
database of its own because a pin counts the statements of one install**: every
installed module that overrides a step of the flow adds its statements, so a
database that also holds `test_discuss_full`'s dependencies (`hr_holidays`,
`hr_homeworking`, `im_livechat`, …) reddens `test_mail`'s pins with the code
unchanged (2026-09-26: 15 failed of 78 there, 0 of 78 on `test_mail` alone),
and `test_discuss_full_enterprise` — auto-installed beside `test_discuss_full`
when its dependencies are installed — moves `test_discuss_full`'s by its own
`+=`. That suite's pins are the community ones
plus those adjustments, so it installs from `odoo/addons` and `addons` only;
neither `agromarin` nor `design-themes` is on its path. On 2026-09-26 the lane took 646 s (296 of them the enterprise suite);
on 2026-09-28, with `test_website_modules`' two runs added and other sessions
loading the machine, 1298 s (411 the enterprise suite, 206 and 231 the two
`test_website_modules` runs).

**The access matrices** run as one more suite, on one database holding every
module that ships one: `-i sale,purchase,account,hr,project,document,approval
--test-tags access_matrix`. Each module's `tests/test_access_matrix.py` states,
per persona, what it may do with each record (every persona a cell does not
name expects nothing), and the runner (`odoo/addons/base/tests/access_matrix.py`)
asks every cell three ways: the check (`has_access`), the SQL filter (the
record in the principal's search, or in a sudo search of its access domain)
and `ir.access._explain_record` rebuilt from its rows, so the three cannot drift
apart. A cell where the system still does something else names its finding and
today's answer (`today=`), and its fix turns the cell red. What a co-installed
module changes in a persona's answer by design is stated on the cell and
applied only where that module is installed -- `installed={"crm":
{"salesman_a": "wc"}}` adds, a `-` prefix (`"-wcd"`) withdraws -- so a matrix
holds on any composition, not only on the database above. test_lint's
`access_matrix_coverage` holds a module with a matrix to every model it grants;
`access_matrix_missing` counts the modules still without one.

`test_orm` — **1,239 test methods** under its `tests/` directory (2026-09-11)
— is the addon written to test the ORM. Above all
`test_domain_evaluator_parity.py`: the only check that a `Domain` means the
same to `search()` (SQL) and `filtered_domain()` (the in-memory predicate),
with a generative suite asserting the two evaluators agree *or both refuse*.
No other suite can see a SQL/predicate divergence.
`TestBackendDifferential.test_divergence_ilike_unaccent` skips on
`registry.unaccent_status`, since a bare `template0` database lacks the
extension every developer database inherits from `db_template`.

`test_read_group` (123 test methods, the only coverage of the five
`read_group/` units) and `test_access_rights` (55, record rules and ACLs) are
counted by method, not by line. **A suite outside the set is a suite nobody
runs.**

### The limits of "enforced"

**The integration suites are the only thing that runs addon tests in Python.**
The integration suites and `tests/contract`, `tests/process`, `tests/loading`
and `tests/perf` are what run Python against a database; `tests/transport` is
the one DB-free suite, and it covers the HTTP transport only.

**The JS suites run through `WebSuite` and `MobileWebSuite`** in
`addons/web/tests/test_js.py`, and `website`'s `WebsiteSuite` and
`MobileWebsiteSuite` (`addons/website/tests/test_js.py`, on `-i website`,
`--test-tags /website:WebsiteSuite,/website:MobileWebsiteSuite`): the website
builder, the public interactions and `@html_builder`, the builder framework
`website` consumes, which has no runner of its own. They are addon tests like
any other, but an integration run that is `--stop-after-init` and `--no-http`
skips these classes at `setUpClass`. The mobile classes run only the files
tagged `mobile` under their suites (`MobileHOOTMixin`); no `html_builder` file
is. Every other addon's HOOT suites run through the generated `AddonSuite` and
`MobileAddonSuite` (tag `addon_js`), on whatever module set its database holds. They must run **under both presets**, desktop and mobile, because
the two presets select by tag and neither set is a superset of the other. Gate
each pass on its own passed-test **count** as well as on the exit code: a suite
contributing zero tests under a preset is not an error to the runner.

**Accessibility is checked on named surfaces, not on the product.**
`addons/web/static/tests/webclient/accessibility.test.js` runs axe-core (the
test-only `web.axe_lib` bundle) over the home menu, the navbar inside an app,
the home tiles in customize mode, a form, a list with a row selected and the
search bar's open autocomplete, and asserts zero violations. A screen not
mounted there is unchecked: extend that file rather than calling a screen
accessible because it passes its own suite. axe covers what markup and
computed style can prove (names, roles, ARIA validity, contrast); focus order
and what a screen reader actually announces are still review.

**Missing infrastructure fails a run.** `OdooTestResult`
(`odoo/tests/result.py`) treats a class whose `setUpClass` skips for want of a
server or a browser as an error, in mixed selections too; ordinary deliberate
skips keep their behaviour. `ODOO_REQUIRE_INFRA=0` is the explicit opt-out for
an incomplete local run and warns that coverage is missing; a post-install
phase that prepared tests and started none fails the run regardless.
`tests/loading/test_post_install_exit_code.py` pins the latter.

**Demo data that fails to load fails a run with tests.** An install catches
the failure, logs *installed without demo data* and exits 0, which is how
`account_depreciation`'s and `hr_fleet`'s demo stayed broken through every
per-module run. With `--test-enable` the loader also records it as an error of
the run (`OdooTestResult.record_demo_failure`), named in the summary line, so
the process exits non-zero; production installs keep the warning.
`ODOO_REQUIRE_DEMO=0` is the explicit opt-out. The suites above run without
demo, so the check bites only in a `--with-demo` run, and
`odoo/addons/test_lint/lint_full_scope.sh` is that run: `lint_full_scope.sh` installs its module set with demo and fails when any
installed module is left without it (`ir_module_module.demo`, which a failed
demo leaves false on the module and on every module depending on it), naming
the failures from the install logs; `--without-demo` skips both. It reads the
flag rather than installing with `--test-enable`, because a test run is handed
the fixed test-run encryption key (`mixin_encryption`'s
`provide_test_run_key`), and that key hides a demo that needs the credential
vault: `stock_delivery`'s validated a delivery whose SMS confirmation created
an IAP account, whose token only a configured key can seal.
`tests/loading/test_demo_failure_exit_code.py` pins it.

**Suites interfere through the registry.** `test_http` depends on `mail`,
whose `res_partner_views.xml` inherits `base.view_res_partner_filter` anchored
on `<filter name="inactive">`, and base's
`test_hard_reset_from_file_still_works` overwrites that view with a minimal
`<search>`. The write re-validates the children, so `-i base` is green while
`-i base,test_http` raises `ValidationError`. One database per suite.

## Known boundary exceptions

**None that are debt.** Two, both `core-does-not-depend-on-addons`, both
scoped to `odoo.service`: `service/_threaded.py` and `service/_worker.py` call
`IrCron._process_jobs` / `IrJob._process_jobs`, `@staticmethod` entry points
that open their own cursor because they run *before* a registry exists for the
database, so there is no `env` to route through. Both imports are deferred to
call time (four call sites), and no override of either exists anywhere in
`odoo`/`enterprise`/`agromarin`.

Performance runs retain wall time, thread CPU time, driver time and residual wall
time separately in the `--perf-output <file>` JSON. Statement counts are judged on every
machine; machine-specific time limits apply only without `--perf-counts-only`. Missing
PostgreSQL fails the performance run instead of skipping it.

The counter measures driver submissions: one execute, executemany or COPY call
is one statement. SQL time includes pipeline synchronization waits. Batch creation
now counts COPY too; its baseline correction is recorded in qualities.md.
