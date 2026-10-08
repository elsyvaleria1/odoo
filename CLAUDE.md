# Odoo 19 — Standalone Framework and Addons

Standalone repository at `github.com/Agro-Marin/odoo`, containing the framework, community addons, and the non-localization addons formerly held in `enterprise`. Localization modules live in the sibling `l10n` checkout (`Agro-Marin/l10n`). Module license declarations and the preserved enterprise notices continue to apply.

| Document | Role |
|---|---|
| `doc/architecture/module.md` | Canonical subsystem map: what the core contains, how it is layered, which dependencies are legal. Read before restructuring core. |
| `doc/architecture/ARCHITECTURE.md` | Front door indexing the above: context, design forces, cross-cutting mechanisms, where new code goes. |

> **"Repo root"** = the directory containing this file. Inside it, `odoo/` is the framework core *package*, not the checkout — which is why `ruff check odoo/` measures the core and not `addons/`.

## Branch Model

Diverged from upstream past the point where merging or cherry-picking between the two is possible.

| Branch | Rule |
|---|---|
| `19.0` | Pristine mirror of upstream `github.com/odoo/odoo` 19.0. **Not** an AgroMarin working branch, **not** the stable/production line. Exists to be read: diff against it, source upstream fixes from it, then **re-implement by hand** on `19.0-marin`. Never commit AgroMarin work here. |
| `19.0-marin` | Active AgroMarin production branch, forked from `19.0`. All work lands here, directly or via PR; this is the integration branch to build on. Nothing is ever merged in from `19.0` — **"this would conflict with upstream" is not a reason to hold back a refactor**, there is no merge for it to conflict with. Posture: *Scope and precedence*, `doc/coding_guidelines.rst`. |
| Feature branches | Cut from `19.0-marin`, merged back into it via PR. |

**No branch carries protection as of 2026-09-01 — direct pushes are allowed.** Feature branches and PRs stay preferred for planned work; never force-push a shared branch.

**Rebase, never merge.** A feature branch is updated by rebasing it onto `19.0-marin`, and syncing is `git pull --rebase`. No merge commits. Rebase before pushing — rewriting an already-pushed branch needs a force-push, which is a separate confirmed action. Rules: `doc/coding_guidelines.rst` §7.3, and *Rebasing* in `~/Odoo/agromarin-knowledge/config/general-context.md`.

## Checkout Requirements

| Requirement | Detail |
|---|---|
| Python ≥ 3.14 | Floor is `MIN_PY_VERSION` in `odoo/release.py`, enforced at import by `odoo/init.py`. |
| PostgreSQL | 18. |
| psycopg 3 | `psycopg[binary]>=3.3.4` with `psycopg-pool>=3.3.1` — the only driver `odoo/db/` uses. Never add a `psycopg2` import. |
| Requirements | `pip install -r requirements.txt -r requirements-addons.txt` for runtime; `requirements-dev.txt` for the gates. The two runtime files split on ownership: `requirements.txt` is what a server process imports whatever is installed, `requirements-addons.txt` is what individual bundled addons own and declare in `external_dependencies`. A development checkout wants both; only a deployment that knows which modules it loads wants the first alone. `requirements-test.txt` pulls in both, so every test run is unaffected. |
| Node | `package.json`'s `engines` (jsdom's range). The server runs Dart Sass (`sass-embedded`), `rtlcss`, `esbuild`, the ES-module lexer (`es-module-lexer`) and the OWL template precompiler (`acorn`, `jsdom`, `xpath`) from `node_modules`; they are `dependencies`, so a deployment installs them with `npm ci --omit=dev`; keep them out of `devDependencies`. Without Dart Sass every SCSS bundle fails to compile and pages lose their styling; without the precompiler templates compile in the browser and the server logs `event=unavailable`. |
| `crates/odoo_rust` | Build it into the environment, with a Rust toolchain on `PATH`. With `CI=true` or `ODOO_REQUIRE_NATIVE=1` its absence is an `ImportError` at `odoo/init.py`. Elsewhere its absence is a `RuntimeWarning` and the process runs on the pure-Python twins behind `odoo/libs/accel.py` — slower, not wrong. A *stale* build is fatal (`assert_fresh`). |

```bash
cd crates/odoo_rust && maturin develop --release
```

### `--release` is not optional

`maturin develop` defaults to the `dev` profile. A debug build is not merely slower — three exports come in slower than the pure Python they exist to delete:

| Export | Debug vs pure Python |
|---|---|
| `origin_ids` | 4.08x |
| `to_prefetch_ids` | 2.53x |
| `sort_ids_by_cache` | 2.41x |

The profile is stamped beside the source fingerprint; `odoo/libs/native.py` refuses to start on a debug build. Escape hatch for attaching a debugger: `ODOO_ALLOW_DEBUG_RUST=1`.

### A stale build is worse than a missing one

The pure-Python twins step in only when the extension is *absent*; a stale `.so` is imported and used. A stale build can segfault on a cyclic `fast_clone` or silently mis-order timezone-aware columns, and neither failure names its cause. A fresh build never sees it, so it is a long-lived-virtualenv problem only.

Each crate's `build.rs` stamps a CRC of its sources into the binary (`crates/odoo_build`); `odoo/libs/native.py` refuses to proceed when it disagrees with the crate on disk, naming the rebuild command. Rebuild after any `git pull` that touched `crates/`. Escape hatch: `ODOO_SKIP_RUST_FRESHNESS_CHECK=1`.

### `crates/` is a cargo workspace of three

| Crate | Role |
|---|---|
| `odoo_rust` | The runtime extension above. |
| `odoo_lint` | Parallel source scanner behind five `test_lint` gates. **Not** a runtime dependency — build only to run those gates: `cd crates/odoo_lint && maturin develop --release`. Separate wheel because it is test-only and would dominate the runtime one: 1156 KB / 35 crates with it, 266 KB / 15 without. |
| `odoo_build` | Shared build-script support, so the fingerprint algorithm that must match `odoo/libs/native.py` exists once. |

Run `cargo fmt --all`, `cargo clippy --workspace`, `cargo test --workspace` from `crates/`, not from a member.

The crate checks are `cargo fmt --all --check`, `cargo clippy --workspace -D warnings`, `cargo test --workspace`, both maturin builds, and the exported symbols — including that `odoo_rust` does **not** carry the scanner.

## Pre-Work Check

Some modules carry a `machine_doc_v<N>/` directory (e.g. `machine_doc_v1/`) with structured, machine-consumable maps of routes, models, architecture, conventions and test tags.

- **Check for `machine_doc_v*/` first and read it before doing anything else.** This eliminates redundant codebase exploration.
- A module's own README.md or CLAUDE.md comes next — named without backticks on purpose: these are file *kinds* a module may carry, not paths, and a backticked path in this repo asserts that one particular file exists.
- That is an enforced rule, not a stylistic note: `factcheck.sh` resolves every backticked path in these directories, including inside a backticked *command*, so a deliberately-absent file is named in plain prose.

### Figures are gated or frozen, never bare

You read these first, so their numbers become your premises (`doc/coding_guidelines.rst` §1.4).

| Kind | Meaning |
|---|---|
| Gated | The module's `factcheck.sh` derives it from the tree and asserts the document cites it (`assert_doc_cites`). The expected value is never a literal in the script — that would make the script a second copy of the tree. |
| Frozen | Pinned to a named base commit, for readings that cannot be re-derived (a profile, a benchmark, an ad-hoc scanner); where a history rewrite erased the base, to the measurement date and the rewrite, never to the lost hash. **Do not "correct" a frozen figure to a current value** — the argument built on it rests on that base. |

Run the module's harness after changing its docs, and before believing them:

```bash
bash addons/<module>/machine_doc_v1/factcheck.sh
```

**And after changing its `tests/`.** A gated figure is derived from the tree, so a page counting test classes and methods is a function of `tests/`, and any commit adding or removing a test invalidates it — while every suite of the changed module still passes, because the page is checked by its harness and not by the tests. **A file you did not edit can be invalidated by the one you did, and no run of the changed file will say so**; the harness is blocking and unratcheted, so the cost is a red gate nobody owns.

### The machine_doc harnesses

Every `factcheck.sh` under `odoo` and `addons` blocks. Nothing runs them for you: run the one for each module you touched, or the loop in `doc/architecture/gates.md` for all of them.

- Discovery must walk the whole repo: `odoo/tests/machine_doc_v1` lies outside both `odoo/addons` and `addons`.
- A machine_doc with no harness is the standing list of what is ungated. **That list is empty**: every machine doc in this repository is gated and blocking. An empty warning list is the thing to keep true, not permission to skip checking.

## Tests

### Python — pytest, from the repo root

`pytest` alone runs all five suites under `tests/`, and each runs alone when named. One is database-free, `tests/transport`; the other four need real dependencies. Run them **from the repo root**: `testpaths` and `pythonpath = .` resolve against the rootdir located by `pytest.ini`. Started from a parent, the tree is collected as plain files and fails en masse rather than skipping quietly.

```bash
pytest tests/transport                               # no database: parser, servers, raw sockets; seconds
ODOO_CONTRACT_REQUIRE_DEPS=1 pytest tests/contract   # needs PostgreSQL + psql + pg_dump
pytest tests/process                                 # boots real odoo-bin processes
pytest tests/loading                                 # installs base into a scratch database
```

`tests/transport` holds `odoo/libs/http1.py`, `odoo/service/_transport.py`, `httpd.py` and the prefork worker over real sockets: framing and smuggling cases, pipelining, timeouts, descriptor and thread leaks. Each of its tests must give back every thread and descriptor it took (`conftest.py`). Run it after any change to those files.

`tests/contract` pins what we *assume* about psycopg, psql and pg_dump against the real programs. It is skip-guarded: without that variable a missing dependency reports green while comparing nothing.

```bash
pytest tests/perf                                    # local time + count floors
pytest tests/perf --perf-counts-only                 # counts alone, judged on any machine
```

`tests/perf` installs `base` into a scratch database and holds the ORM to `tests/perf/floors.json`: statement counts per flow are exact ratchets, the SQL text each flow sends (`sql_chars`) is held to a ±10 % band on every machine, residual wall time (wall minus SQL, distinct from thread CPU) and the warm registry load are floors with a 25 % tolerance. Run it after any change under `odoo/orm/`, and move a floor in the same change that moves the count. To find *where* time goes, use a signal-based sampler on the main thread; cProfile shares and sampling threads both misattribute (`doc/architecture/qualities.md`, Scenario 0).

### JS (HOOT)

HOOT suites run through `WebSuite` / `MobileWebSuite` in `addons/web/tests/test_js.py`, which need the HTTP server (`--http-port <n>`, never `--no-http`) and Chrome:

```bash
odoo-bin -d <db> -i web --test-enable --test-tags /web:WebSuite --http-port 8079 --stop-after-init
```

Run **both presets** — desktop (`WebSuite`) and mobile (`MobileWebSuite`) select by tag and neither is a superset of the other. `website`'s suites run the same way, on a database with `website` installed: `WebsiteSuite` (desktop, and `@html_builder`, which has no runner of its own) and `MobileWebsiteSuite` (`addons/website/tests/test_js.py`).

## Coding Guidelines

**Before writing or modifying any code in this repo, read and follow `doc/coding_guidelines.rst` (repo root).** It is the single authoritative source for AgroMarin coding standards — built on Odoo 19.0 + OCA conventions, authoritative where it speaks; where silent, follow upstream Odoo 19 / OCA. It supersedes any other `coding_guidelines` file.

Each rule names the gate that catches it — `[ruff CODE]` (`E85xx` is the pinned ruff fork's `Odoo` linter), `[oxlint RULE]`, `[test_lint CODE]`, `[fixer NAME]` or `[review]`; see *How rules are enforced* at the top of the guide.

**A marker is not evidence the gate exists.** Of §2.4's (method naming) `[ratchet …]` / `[gate …]` markers, only `[ruff RUF022]` names a tool that exists. `doc/architecture/gates.md` is the list of what runs and no entry of it reads a method name; `test_lint`'s `test_naming.py` checks one property, that no public method takes `ids` or `context`. Read §2.4's naming markers as `[review]`, and **re-derive any figure there before relying on it** — most of its census rows are false, and some cannot be re-derived at all.

Method refactors follow §2.4.21: search related implementations, compare typed inputs/results and effects, extract at the shared owner, and verify callers, failures and batching. Identical source is a candidate, not proof of equivalence; predicates return booleans on normal completion, and data RPCs retain their operation names.

Return contracts follow §2.4.23: one typed contract per name, `None` or the empty value for absence (never `is False`), a result type for several outcomes, `dict | None` for actions (never `True`: `test_lint` `return_action_bool_result_<repo>` counts the rest), an override keeps the base's contract; `method-census/batch-06/mixed_report.py` ranks the mixed ones.

System-setting reads follow §10.9: trusted server code uses `env.registry.settings.get(env, key, default)` to receive a scalar without holding an elevated recordset. A migrated `get_param(key)` passes `False` explicitly; typed values come from `get_int`/`get_float`/`get_bool`; the `_settings_port_reads` fixer rewrites elevated reads; setting writes retain their normal ACL.

### `ruff.toml` (repo root)

Linter and formatter config, with the rationale for every suppression.

- `ruff check .` (the whole checkout, `addons/` included) is a hard zero, and so is `ruff check .` in `../l10n` and `../agromarin` under their own `ruff.toml`.
- `ruff`, `mypy`, `tsc`, `oxlint` and `oxfmt` run on their pinned versions (`requirements-dev.txt`, `package.json`).

### `oxlint.config.mjs` and `.oxfmtrc.jsonc` (repo root)

The JS lint ruleset and the JS/SCSS formatter scope. oxlint loads a JS config only when named, so every run is `oxlint -c oxlint.config.mjs`. `makeConfig` is the shared factory: its full ruleset applies to every `.js`/`.mjs` file, `../l10n` and `../agromarin` call it with only what is particular to them (ignores, page globals), and its plugins load from this checkout by absolute path — `tooling/oxlint/plugin.mjs` (`odoo/no-restricted-syntax`, ESLint's selector rule) and the vendored `tooling/oxlint/simple_import_sort/`. oxlint reads no `/* global */` comment: a global a page defines goes in the `pageGlobals` table. `no-console` allows only `warn` and `error`; a trace someone turns on goes through `makeLogger` (`@web/core/debug/debug_logger`). Beyond eslint's recommended set it runs the correctness category of the unicorn, oxc and promise plugins; the config states why `no-useless-spread`, `no-new-array`, `no-unused-expressions` and `no-callback-in-promise` stay off. Do not enable the `import` plugin: oxlint 1.86 segfaults on this tree with it.

### `odoo/addons/test_lint/`

The fork's own AST checkers and registry gates, one checker or suite per file under `tests/`: SQL built from non-constant values, gettext misuse, `Markup()` over an already-formatted string, N+1 queries, ORM-facade imports, XML/manifest canonical form, the XML data-file rules, OWL templates and `setup()` hooks, asset bundles, elevation (`sudo()`, `has_group`, public methods that write through one), wizard naming, unreachable and orphaned overrides, manifest descriptions. A gate graded per repository is named `<gate>_<repo>`; `owl_bare_member` needs node with jsdom.

Each is an exact-match ratchet, so an undone fix fails as loudly as a new offence. The AST and XML rules run at the narrow scope below; the registry-dependent classes need a fuller install. The per-file AST rules, `E8501`–`E8543` but the cross-unit `E8512` and `E8517`, plus `E8544` (noqa-rationale), are the pinned ruff fork's `Odoo` linter, counted against the same floors by `odoo/addons/test_lint/lint_ruff_gates.py`. The newest, `empty-recordset-mutation` (`E8543`), is `unlink`/`write`/archive on a bare `env["model"]`, which changes nothing; none is advisory and none fails outright — the floor decides.

**The floors are defined at the narrow scope**, which is `--addons-path=odoo/addons,addons` with only `test_lint` installed. Harvest and verify them there, not against a workspace that also carries `enterprise/` — the two measure different trees, and floors taken from the larger one cannot pass at the narrow scope:

```bash
odoo-bin --addons-path=odoo/addons,addons -d <db> -i test_lint \
    --test-enable --test-tags /test_lint --stop-after-init --no-http
```

**The floors are in `odoo/addons/test_lint/tests/floors.json`**, one integer per gate name; `LintCase.assert_ratchet` reads that file and treats an absent gate as zero. Handed an integer it raises. Move a floor by editing the file in the same change that moves the count.

Gates that read the *installed registry* rather than the tree cannot be graded at the narrow scope at all:

| Gate | Behaviour at narrow scope |
|---|---|
| `test_docstring` | One-sided ratchet: measures 1 there, 32 on a fuller install. Do not floor it at the former. |
| `ViewFieldAccessLinter` | Zero rule (`view_field_access`): no element of an installed primary view may carry an expression reading a field some of its viewers cannot read, as the view validator's "Access Rights Inconsistency" warning reports it. A view restricted by `group_ids` is graded as those groups see it. The narrow scope installs few such views, so it passes there for want of them. Grade it on a fuller install. |
| `TestSchemeDuplication` | Zero rule: no declaration of a module in this repository may resolve differently under `data-color-scheme="dark"` in the light bundle from what the dark bundle serves. At the narrow scope it measures only what is installed there, so it passes for want of modules. Grade it on a fuller install. |
| `TestViewDepends` | Zero rule per repository (`view_depends_undeclared_{odoo,enterprise,agromarin}`): a SQL-view model names in `_depends` every stored field its SQL reads, or a search reads it stale (`coding_guidelines.rst` §2.6). The narrow scope installs few SQL views, so it passes there for want of them. Grade it on a fuller install. |
| `TestFieldDeclarations`, `TestIndex`, `OrphanLabelLinter`, `DroppedViewTextLinter`, `TestBundleTokenDefs` | Floors are zero and pass at the narrow scope over the little installed there; point_of_sale's dead lock-date constraint read 0 narrow and 4 with point_of_sale installed. |
| `TestUnreachableOverrides` | Ratchets (`unreachable_override`, `orphan_super`) over the installed registry: the narrow scope measures `base` and `test_lint` only, where a mixin-order fault in an addon cannot show. Grade it on a fuller install. |

The fuller-install grading is `odoo/addons/test_lint/lint_full_scope.sh`: installs a named module set with demo data into a scratch database, repeats `-i` until nothing more goes missing, fails if any installed module is left without its demo, runs `/test_lint`, drops the database.

`odoo/addons/test_lint/machine_doc_v1/` is the map: two halves (`_rules.py` declares what a rule is, `_py_scan.py` runs the scan), which fixer answers to which document-identity invariant, and what each scope can and cannot measure.

### Other gates

There is no runner script and no CI: every gate runs by hand, and `doc/architecture/gates.md` gives each command — that the venv matches `requirements*.txt` (`uv pip install --dry-run …`; a drifted environment runs every suite against unpinned versions), ruff's hard zeros (this checkout and the sibling repos), bare-env mypy, `test_lint`'s tree scans without a database (`odoo/addons/test_lint/lint_source_gates.py`), the ruff fork's E85 rules against `test_lint`'s floors (`odoo/addons/test_lint/lint_ruff_gates.py`), `doc/architecture/factcheck.sh` and every module machine_doc harness (`addons/*`, `odoo/addons/*`, `odoo/tests`), the cargo and JS toolchains, and the addons' query-count pins (`mail`, `test_mail`, `test_mail_full`, `test_mail_sms`, `test_discuss_full`, `test_website_modules` without and with demo, and `test_discuss_full_enterprise`), each on a scratch database installing that suite's module alone — a pin holds only on such a database, so never judge one on a shared install. The Rust checks are the crate workspace's own `cargo` commands. There is no other gate tree.

### Changing the guidelines

Manifest identity and capability claims: `doc/coding_guidelines.rst` §1.2.1.
Mandatory review; structural manifest gates do not certify semantic accuracy.

Edit `doc/coding_guidelines.rst` directly. Its *Change protocol* binds what you do next:

- The same PR updates the `CLAUDE.md` files that summarise the rule — this one included — and adds a row to Appendix D.
- Rules are retired into Appendix C, never deleted silently.
- A rule whose rationale is architectural states that rationale in the rule itself, or in the gate's own module docstring.
