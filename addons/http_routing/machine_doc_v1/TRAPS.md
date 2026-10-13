# http_routing — Traps

Behaviours here that look wrong and are right, look like duplication and are
not, or look safe and are not. Each entry says what it costs to get wrong and
names the test that pins it, so a future refactor fails loudly instead of
quietly.

## 1. The two "is this URL local?" guards are NOT duplicates

`_url_for` tests scheme/netloc via `urlparse`; `_url_localized` tests the
leading slashes. Same shape, **different question**:

```python
_url_for("#top", "fr_FR")  # -> "/fr/current/page#top"
_url_localized("#top", "fr_FR")  # -> "#top"
```

`_url_for` asks *"is this relative"*, so `urljoin` can root it against the
current page — with a language forced it deliberately accepts a bare fragment,
which is exactly what a language switcher needs to keep the anchor.
`_url_localized` asks *"is this already a path I can match against the routing
table"*, and `#top` is not one.

Unifying them removes anchor-preserving language switching.
→ `TestUrlLang.test_bare_fragment_is_rooted_when_a_language_is_forced`

## 2. `_url_for` is not idempotent, on purpose

In a French context `_url_for("/en/shop")` → `/shop` → `/fr/shop`. The first step
strips an explicitly-default-language prefix (the server 303s it away anyway,
case /6), the second inserts the context language. Both are correct in
isolation; composed, they are not stable.

This matters if page content that has *already been through* `url_for` is
re-rendered — website-editor-saved DOM is the realistic case. Not changed here
because canonical-URL generation depends on the first step. Measured: 16
non-idempotent shapes, all `/<default-lang>/…`.

## 3. Id `0` had to be rejected in the converter, not later

`_get_records_forbidden_and_error_factory` does `browse(id_ for id_ in self._ids if id_)` — a **falsy id is
filtered out**, so `/<model>/0` got neither `MissingError` nor `AccessError`, and
then died in `_pre_dispatch` where `_slug` refuses to *produce* a 0-id slug:
an unauthenticated **500** on every frontend `<model(…)>` route, reachable by any
crawler. The grammar accepts more spellings than the obvious one — `-0`, `00`,
`my-post-0`: 61 of 2085 short segments fuzz to id 0.

`ValidationError` is werkzeug's "this rule does not match", so the URL falls
through to the remaining rules and then to a clean 404.
→ `TestModelConverter.test_id_zero_does_not_match`

**Scope note:** `_get_converters` is registry-wide, so this also applies to the
handful of non-`website` routes using `<model(…)>`. For an anonymous caller those
went `303` (login redirect) → `404`, because the converter now rejects before
authentication.

## 4. A missing record often 404s *only* because of the slug rebuild

`check_access` runs the `ir.access` domain against the id without ever checking that it
exists. On a model with no record rules, nothing detects a missing record —
except `_pre_dispatch`'s canonical-URL rebuild, which reads `display_name` and
raises `MissingError`.

Verified by ablation: disable that block and `/<model>/99999` answers **200** for
a rule-free model, while `/shop/999999` and `/blog/999999` still 404.

So the `except` around `rule.build` **must not** catch `MissingError` /
`AccessError`. A blanket `except Exception` there serves a 200 for a record that
does not exist.
→ `TestModelConverter.test_canonical_redirect_still_reports_a_vanished_record`

## 5. `rule.build()` returns a bare `None`, not `(_, None)`

So `_, path = rule.build(args)` raises `TypeError` before any `if path is None`
check can run. And the errors that actually occur — `ValueError` from `_slug` or
from `<any(…)>` — are not werkzeug `ValidationError`, so werkzeug never swallows
them into that `None` either. Both facts have to hold at once for the guard to
be right.
→ `TestModelConverter.test_canonical_redirect_survives_an_unbuildable_url`

## 6. `_slug` on a multi-record set used to link to the wrong page

`BaseModel.id` answers `_ids[0]`, so slugging a recordset silently produced a URL
for whichever record came first. `website`'s override reads `seo_name` and *does*
raise `Expected singleton` — the same mistake was loud or silent depending on
which addons were installed. Now `check_singleton()` on both.
→ `TestSlug.test_slug_rejects_a_multi_record_set`

## 7. Emitting a trailing slash costs the visitor a redirect

Every slashed frontend URL 301s to its bare form. `_url_for` normalizes the path
once, before the branches, so all four spellings of a link agree; only the
"insert a prefix" branch used to, which gave one link three different answers.
→ `TestUrlLang.test_trailing_slash_dropped_by_every_branch`

`/` is the homepage, not `""` with a stray slash — normalizing it away emits an
empty href, which resolves against the current page.
→ `TestUrlLang.test_root_is_not_mistaken_for_a_trailing_slash`

## 8. `MockRequest` must stay faithful, or assertions test the mock

`Mock` autovivifies any attribute, so a missing one does not fail — it silently
takes a branch. Four found this way:

| Attribute | What the mock did instead |
|---|---|
| `httprequest.method` | a truthy object equal to nothing → every `_REDIRECTABLE_METHODS` branch took its "unsafe method" side |
| `httprequest.args` | a plain `list` → `keep_query().getlist()` and `redirect_query` were never exercised |
| `httprequest.user_agent` | a `Mock` → `is_a_bot()` raises `TypeError`, so ladder case /3 was unreachable from a unit test |
| `redirect` | bound to the *model* method `ir.http._redirect`, which takes no `local=` — it could not be called the way production calls it |

When adding an attribute to `MockRequest`, prefer binding the real
`odoo.http.Request` method (`prepare_response`, `redirect`, `redirect_query` are
self-contained) over inventing a stub.

## 9. `_url_localized` must never re-enter `ir.http._match`

`_match` is the dispatch entry point: it stamps `is_frontend`/`lang`, and case /9
calls `request.reroute()` — on the request being served. A URL-*generation*
helper that goes through it steers the live request. It matches the routing map
directly instead.
→ `TestUrlLocalized.test_does_not_steer_the_live_request`

## 10. Log-flood shapes

`_is_multilang_url` runs **once per generated link**. It used to swallow any
routing-probe failure with a `warning(..., exc_info=True)` and answer "not
multilang": one full traceback per href, and links silently left unprefixed.
`_url_rewrite` already answers every `HTTPException` and redirect loop itself,
and nothing else raised over 3,012 fuzzed paths, so the guard is gone: a real
failure now fails the render once, at the first link. `_pre_dispatch`'s guard
still logs one line with the exception, because the request it protects can be
served without the slug redirect.

## 11. `request.render("http_routing.http_error")` off the frontend is a 500 with `portal` or `website`

`web.frontend_layout` is extended for every render by the modules above it,
and they read what only `_prepare_frontend_environment` puts in the qcontext:
`portal.language_selector` takes `len(frontend_languages)` (`TypeError` on
`None`), `website.layout` reads `website.id` in its first `t-set` (`KeyError:
'website'`). A request whose route is not `website=True` never runs it, so the
visitor reads a bare 500 instead of the refusal. With `http_routing` alone the
same render succeeds, so a suite whose database has neither stays green over
the defect. `_serve_error_page` makes
the request a frontend one first; flagging each such route `website=True`
instead also changes its whole dispatch (the website's companies in the
context, `website_id`, the multilang redirect).
→ `test_website`'s `tests/test_error.py`

## 12. `_url_for` treats a named language and a context language differently

`_url_for(url)` takes the language from the context, `_url_for(url, code)` from
the caller. When the site does not serve that language, the first gets **no**
prefix and the second keeps the language, as its `url_code`:

```python
# website serves en_US + fr_FR; a backend user reads in de_DE
_url_for("/slides/embed/7")  # -> "/slides/embed/7"
_url_for("/survey/print/tok", "de_DE")  # -> "/de/survey/print/tok"
```

The named case must keep it: `survey` serves every installed language on its
own paths (`web_force_installed_langs`), so `/de/survey/…` resolves there while
`/de/contactus` 404s. The context case must not: a link built in a backend
request (a slide's embed code, `website.get_suggested_controllers`) carried the
backend user's language, and every one of them 404'd on the website.

That second defect needed **two** halves, and neither alone fixes it. Off the
frontend, `website` used to answer "served languages" with every *active*
language and "default" with `ir.default`, so `de_DE` counted as served and the
link came out `/de/…` without ever reaching the fallback above. `website` now
answers both from the website even off the frontend (its `_frontend_url_codes`
and `_get_default_lang`), which is what makes the fallback reachable there. A
probe that simulates the backend with a *frontend* `MockRequest` exercises
neither half: it is how the first version of this fix was wrongly believed
complete.

Unifying the named and context cases in either direction breaks one of them.
→ `TestUrlLangContext.test_unserved_context_lang_is_not_put_in_the_url`,
`TestUrlLangContext.test_unserved_lang_named_by_the_caller_is_kept`, and the
backend cases in `website`'s `tests/test_lang_url.py`

## 13. A URL segment is a language only when it is shaped like one

`_match` reads the first segment of an unrouted path as a language before any
CMS page is looked up. It used to hand *any* segment to `get_nearest_lang`,
whose base match took `en_vivo` for English and `fr_vivo` for French: a
published page at `/en_vivo` answered **303 → /** and was unreachable. Meanwhile
`/FR/x`, `/fr-FR/x` and `/en-US/x` -- real tags -- answered 404.

A configured `url_code` still matches exactly first. Otherwise the segment must
fit `_LANG_TAG_RE` (2-3 letters, optionally `_` or `-` and a 2-letter or
3-digit region, optionally `@script`, any case), and is canonicalized
(`fr-fr` → `fr_FR`) before `get_nearest_lang`. A page whose whole first segment
is tag-shaped (`/es-mx`) is still read as a language; that is the price of
accepting the hyphenated tags people and crawlers type.
→ `TestLangUrlSegment`, `TestLangLadder.test_a_segment_not_shaped_like_a_language_is_not_one`,
and the `/en_vivo` page case in `website`'s `tests/test_lang_url.py`

