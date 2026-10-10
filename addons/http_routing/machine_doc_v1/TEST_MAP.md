# http_routing — Test map

All suites are `post_install` (`@tagged("-at_install", "post_install")`) and run
through `odoo-bin`; none is a pytest tier-1 suite.

```bash
odoo-bin -c <conf> -d <db> -i http_routing --stop-after-init --no-http
odoo-bin -c <conf> -d <db> --test-enable --test-tags '/http_routing' --stop-after-init
# one class:
odoo-bin -c <conf> -d <db> --test-enable --test-tags '/http_routing:TestRerouteLadder' --stop-after-init
```

`--no-http` is **not** usable for the test run: several classes are `HttpCase`.
Give each concurrent run its own `-d` and its own `-p` / `--gevent-port`.

## What covers what

| File | Class | Kind | Covers |
|---|---|---|---|
| `test_url.py` | `TestUrlCommon` | fixture | not a test: the shared two-language fixture (`fr_FR` + `en_US` default) every class below inherits |
| | `TestUrlLang` | unit | `_url_for`: lang insert / strip / replace, fragments, trailing slashes, `[lang]` placeholder |
| | `TestUrlLangContext` | unit | a context with no usable `lang` (`None`, `False`, absent) must still produce a URL |
| | `TestLangUrlPrefix`, `TestLangUrlUnprefix` | unit | the two path/language primitives and their round trip |
| | `TestUrlSplitSuffix` | unit | RFC 3986 `path[?query][#fragment]`, incl. losslessness |
| | `TestIsMultilangUrl`, `TestIsMultilangUrlWithoutRequest` | unit | translatability probe, with and without an ambient request |
| | `TestUrlLocalized` | unit | every "cannot rebuild → degrade" path; must never raise, never steer the live request |
| | `TestDefaultLang` | unit | stale `ir.default`, and that the lookup is cached (it is on the per-link path) |
| | `TestUrlRewrite` | unit | `MethodNotAllowed`, redirect loops, cache non-poisoning, request-free use |
| `test_lang.py` | `TestNearestLang` | unit | base-language matching (`kab` ≠ `ka`, `sr@latin` ↔ `sr`) |
| | `TestLangUrlSegment` | unit | which URL segments are a language at all, and their canonical code (`FR`, `fr-fr`, `sr@latin`; not `en_vivo`) |
| | `TestRedirectLang` | unit | the single 3xx exit: status, Location, cookie, repeated query params |
| | `TestRerouteLadder` | unit | **the ladder as a table** — cases /2../9, incl. an alias of the default language leaving in one hop |
| | `TestLangLadder` | HttpCase | the same ladder end to end: proof it is wired into dispatch, plus the `//` merge and unsafe methods |
| `test_slug.py` | `TestSlug` | unit | the `name-id` grammar: unicode, id 0, negative ids, query/fragment/trailing slash |
| | `TestModelConverter` | unit | id-0 rejection, `abs()` fallback, and both halves of the `rule.build` guard |
| `test_error_page.py` | `TestExceptionCodeValues` | unit | exception → HTTP status |
| | `TestErrorHtml`, `TestErrorTemplateSelection` | unit | status → template, and that overriding the template leaves the status alone |
| | `TestErrorPageTranslatability` | unit | the shared 4xx body did not make its headings untranslatable |
| | `TestErrorStatusEndToEnd` | HttpCase | the status a visitor actually receives |
| | `TestErrorPageOffFrontend` | HttpCase | `_serve_error_page` from a `website=False` route answers the page with the status it asks for |
| `test_translations_route.py` | `TestWebsiteTranslations` | HttpCase | `/website/translations` serves the server-side allow-list in the language its caller names, never redirects or writes the language cookie, and a caller cannot grow the shared ormcache |
| `test_res_lang.py` | `TestFormCreate` | unit | `res.lang` stays creatable through the form view this module extends (`url_code` must not be required) |
| `test_mock_request_cursor.py` | `TestMockRequestCursor` | HttpCase | the test thread may open its own `registry.cursor()` under a `MockRequest`, and a `MockRequest` does not stop `authenticate()` |

## Why some of it is unit and not HttpCase

The module ships no `website=True, multilang=True` route, so the end-to-end
tests route one of their own, `tests/common.py`'s `FRONTEND_PROBE_ROUTE`, and
reach only the ladder branches a plain public page makes reachable, at a server
round trip each. `TestRerouteLadder` and
`TestRedirectLang` assert the decisions directly, which is how branches needing a
bot User-Agent, an unsafe method, or a language the site does not serve get
covered at all. `TestLangLadder` stays as the proof that the decision is wired
into dispatch.

## `tests/common.py`

- `MockRequest(env, …)` — a frontend request. **Faithfulness matters**: see
  `TRAPS.md` §8 before adding an attribute. `mock_router=False` matches against
  the real routing map; `is_frontend=None` simulates a not-yet-routed request.
- `setup_frontend_langs(env, langs, default)` — stack-aware: also writes
  `website.language_ids` / `default_lang_id` when `website` is installed, because
  `website` overrides `_get_frontend` / `_get_default_lang` and a fixture that
  only set `ir.default` would silently configure nothing.
- `FRONTEND_PROBE_ROUTE` / `route_frontend_probe(cls)` — a public `website=True`
  http route declared by the test package itself, for a test that needs the
  ladder or the frontend error handling on a real request; call
  `route_frontend_probe` from `setUpClass` so the routing map picks it up.
- `OFF_FRONTEND_REFUSAL_ROUTE` — an `auth="user"` route that is **not**
  `website=True` and answers through `_serve_error_page`, the shape of a backend
  download refusing; `route_frontend_probe` registers it too. Its failure mode
  needs `portal` or `website` (TRAPS §11), so `test_website`'s
  `tests/test_error.py` is the one that would go red without the promotion.

## Verifying a change beyond the suite

Two techniques this module's history has needed, both cheap to redo:

- **Differential run.** Put a pristine checkout in a `git worktree`, install the
  same modules into a second DB, and compare `_url_for` / `_is_multilang_url`
  over a generated URL corpus. A change to URL generation should have a blast
  radius you can name; ~4 k cases takes seconds and says exactly which shapes moved.
- **Ablation.** To find out whether a guard is load-bearing, disable it and see
  what still passes. That is how §4 in `TRAPS.md` was established.
