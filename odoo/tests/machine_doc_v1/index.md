# odoo.tests — Machine Documentation v1

## Purpose

`odoo/tests` is the **test framework** of this fork: vendored unittest
machinery (case/suite/result), the Odoo test-case hierarchy
(`BaseCase → TransactionCase → HttpCase`), the savepoint-based `TestCursor`,
the server-side `Form` emulator, tag-based test selection, and a headless
Chrome (CDP) driver for browser/tour tests.

It is **framework, not an addon**: no models, no manifest. Tests *for* this
package live in `odoo/addons/base/tests/` (see Conventions).

## Files at a Glance

| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports `common.*` (per `common.__all__`), `Form`, proxies |
| `case.py` | Vendored `unittest.TestCase` (trimmed run loop, traceback surgery) |
| `suite.py` | Vendored `TestSuite` + `OdooSuite` (class setup/teardown, stats) |
| `result.py` | `OdooTestResult`: log-as-you-fail, counters, per-test stats, `soft_fail` |
| `loader.py` | Discover test modules per addon, build/run suites (`prepare_suite`/`run_suite`) |
| `tag_selector.py` | `TagsSelector`: parses `--test-tags` specs, filters tests |
| `common.py` | The public façade: decorators (`tagged`, `users`, `warmup`, `no_retry`, `freeze_time`, `standalone`), `new_test_user`, `test_xsd`, and the re-exports `__all__` names |
| `transaction_case.py` | `BaseCase`/`TransactionCase`/`SingleTransactionCase`, their assertions, and the registry-lock, statement-recorder and stranded-cursor machinery they own |
| `in_memory_case.py` | `InMemoryCase`: hosts a module's own `TransactionCase` class on the in-memory backend -- a `model_test_env` for the class with `hosts_modules`' data files loaded, `allow_inherited_tests_method` so the hosted methods are collected, and the per-test snapshot plus the cache clears a dict rollback does not cover |
| `domain_fuzz.py` | The domain semantics differential: random datasets and domains over a set of models (`build_schema`), each domain answered by the backend's search, by `filtered_domain` and by its conditions searched alone and combined as sets (`evaluators`, `composed`); a `Campaign` collects disagreements and shrinks them to a minimal domain and dataset. `ODOO_DOMAIN_FUZZ_ROUNDS`, `_SEED` and `_DEPTH` lengthen a run; hosted by test_orm's `TestDomainSemanticsFuzz` (PostgreSQL) |
| `matchers.py` | `Like`, `Approx`, `WhitespaceInsensitive`, `RecordCapturer` and the XML normaliser — value comparison, no dependency on the case hierarchy |
| `pdf_signing.py` | A test PKI (root, intermediate, leaf) and `sign_incrementally`, which signs a PDF as an incremental update so the output starts with the original bytes; for tests of `odoo.tools.pdf.signature.get_verified_pdf_signature` and of addons that accept signed documents |
| `xsd.py` | The XSD harness behind `test_xsd`: loads a schema from a path or a URL (a single `.xsd` or a zip of them) into attachments, resolves `schemaLocation` imports against them, and validates through `odoo.tools.xml_utils.check_with_xsd` |
| `file_samples.py` | Sample file payloads as constants -- `PNG`, `GIF`, `BMP`, `JPG`, `WEBP`, `SVG`, `ZIP` base64-encoded, `NAMESPACED_SVG`, `XML` and `TXT` raw -- for the attachment, image and mimetype tests of test_orm and website_slides |
| `media_recordings.py` | Synthetic media built with PyAV on call: `build_recording` (Matroska with optional video, audio and ASS subtitles), `build_container` (any container and codec triple, with subtitles), `build_audio_with_cover` (MP4 audio with an attached cover picture); `av` and `numpy` are imported inside each builder, so the module imports without them. Used by extract's tests |
| `css.py` | Reads a compiled stylesheet the way the cascade does -- declarations, `:root` and the `data-color-scheme="dark"` block, `var()` resolution, colour canonicalisation (`color-mix`, relative `hsl(from …)`, `calc()`) -- plus `composite()` and `measure()`, the dark-scheme comparison of a light bundle against its dark reference; shared by `test_lint`'s scheme gate, web's design-system tests and web_studio's scheme test |
| `http.py` | `HttpCase`/`Opener`/`Transport`/`JsonRpcException` (extracted from common; still re-exported there) |
| `browser.py` | `ChromeBrowser` CDP client, `Screencaster`, Chrome discovery |
| `clock.py` | The harness's own clock (`monotonic`, `wall`): exempt from every freezegun freeze, so a tour or request wait under `freeze_time` still times out |
| `utils.py` | `HOST`, `get_db_name`, `save_test_file`, `env_int` (shared by common+http+browser, no cycle) |
| `cursor.py` | `TestCursor`: savepoint-simulated commit/rollback over one real cursor |
| `form.py` | `Form`/`O2MForm` + x2many proxies: server-side form-view emulation |
| `shell.py` | `run_tests(env, tags)` for interactive `odoo-bin shell` use |
| `benchmark.py` | `BenchmarkStats`/`compute_stats`/timers for perf suites |
| `module_operations.py` | CLI: install/uninstall/cycle modules, `@standalone` runner |

## Entry Points

- Module loading runs tests via `loader.prepare_suite` + `run_suite`
  (called from `odoo/modules/loading.py` when `--test-enable`/`--test-tags`).
- `odoo-bin shell` → `odoo.tests.shell.run_tests(env, test_tags)`.
- `python -m odoo.tests.module_operations -d db [cycle|uninstall|standalone]`.

## Read Next

- [`architecture.md`](architecture.md) — execution flow, cursor/lock model, tag grammar, browser stack
- [`conventions.md`](conventions.md) — where the tests live, tags, gotchas, what NOT to do
