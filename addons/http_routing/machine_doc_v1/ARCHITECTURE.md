# http_routing — Architecture

What this module is, what it owns, and the two mechanisms worth understanding
before editing it: the **multilang ladder** (how a URL picks a language) and the
**URL grammar** (who is allowed to know how a language sits in a path).

> **See also**: `TRAPS.md` — behaviours that look like bugs, or like duplication
> begging to be refactored, and are neither. Read it before "simplifying"
> anything here. `TEST_MAP.md` — which class covers what, and how to run it.

## Module identity

- **Technical name:** `http_routing` · **Depends:** `web` · **Category:** Hidden
- **Role:** turn `ir.http` into a *frontend* router. Everything public-facing
  (`portal`, `website`, and their dependents) sits on top of this.
- **Size:** ~1.3 kLOC of source, ~2.3 kLOC of tests.

It ships exactly **two routes**, both incidental to its real job:

| Route | Why it exists |
|---|---|
| `/website/translations` | serves the frontend's web translations (named once, as `ir_http.FRONTEND_TRANSLATIONS_ROUTE`, because `get_frontend_session_info` hands the same string to the browser). Not `website=True`: the language is its `lang` argument, so the ladder neither redirects it nor writes the visitor's `frontend_lang` cookie from it |
| `/web/session/logout` | re-declared `website=True, multilang=False` so logging out from the frontend stays on the frontend |

The module's substance is its **`ir.http` override**: converters, the language
ladder, URL generation, and the frontend error page.

## The request path

```
                    ir.http._match(path)                     models/ir_http.py
                             │
      ┌──────────────────────┴───────────────────────┐
      │ already routed? (hasattr request.is_frontend)│──yes─→ super()._match
      └──────────────────────┬───────────────────────┘
                             │ no
                    _match_and_flag(path)  ── sets is_frontend /
                             │                   is_frontend_multilang
              ┌──────────────┴───────────────┐
       matched, not frontend            NotFound, or frontend
              │                               │
         return rule ──────────────→   collapse "//" runs (301, GET/HEAD only)
                                              │
                                   _resolve_frontend_lang()   ── sets request.lang
                                              │                  under a borrowed
                                              │                  public user
                                   _reroute_for_lang()  ── THE LADDER, below
                                              │
                                   re-match, or reuse the /1 match
                                              │
                                   _pre_dispatch()  ── canonical-slug 301
```

## The ladder (`_reroute_for_lang`)

`request.lang` is resolved first, in priority order: **URL** → `frontend_lang`
cookie → context → site default. The ladder then decides what to do about the
URL itself. Each case below is marked `# See /N` on its own branch of
`_reroute_for_lang`, and `factcheck.sh` asserts all eight are still there. They
used to live in `_match`'s docstring, where 869409d761a's docstring strip took
all eight at once -- on the branch, that cannot happen.

| # | URL carries a lang | Requested lang | May redirect | Outcome |
|---|---|---|---|---|
| /1 | — | — | — | endpoint is not `website=True` → serve, ladder never runs |
| /2 | no | = default | — | **serve** as-is |
| /3 | no | ≠ default, UA is a bot | — | **serve** as-is, forced to the default lang |
| /4 | no | ≠ default | no | **serve** as-is |
| /5 | no | ≠ default | yes | **303** → `/<lang>` + path |
| /6 | yes, the default or an alias of it (`en_US`) | — | yes | **303** → path without the prefix, in one hop |
| /7 | yes, an alias (`fr_FR`) | — | yes | **301** → `/<url_code>` + path |
| /8 | yes, bare `/<lang>/` | — | yes | **301** → `/<lang>` |
| /9 | yes, canonical *or* redirecting forbidden | — | — | **rewrite**: strip the prefix, serve |

Three properties hold and are pinned by tests:

- **"May redirect" is `GET`/`HEAD` only** (`_REDIRECTABLE_METHODS`). RFC 9110
  lets a client replay a 301/302 on an unsafe method as `GET`, and a 303
  *mandates* it — so redirecting a `POST` silently drops the body. `OPTIONS` is
  excluded too: a browser never follows a redirect on a CORS preflight.
- **Case /9 is the catch-all for unsafe methods.** /6../8 are tried only under
  `allow_redirect`, and whatever none of them took is rewritten, so
  `POST /fr_FR/x` reaches dispatch instead of 404ing on a prefix nothing would
  strip. No input is left undecided: there is no "couldn't route" branch.
- **/6 compares the resolved language, not the URL segment.** `/en_US/x` used
  to 301 to `/en/x` (case /7) and only then 303 to `/x`: two round trips, the
  first of them cached permanently by the browser.
- **Every 3xx exits through `_redirect_lang`**, which carries the query string
  and pins the `frontend_lang` cookie to `request.lang` — the same value
  `_frontend_pre_dispatch` writes on the request that is finally served, so the
  redirect and the followed request cannot disagree about the language.

## The URL grammar — who owns what

The recurring failure mode in this file's history is **a second implementation
of "how a language sits in a path"**, drifting from the first. There are now
four primitives, and everything else is required to go through them.

| Primitive | Owns |
|---|---|
| `_url_split_suffix(url)` | RFC 3986 `path[?query][#fragment]`. The fragment starts at the **first** `#`; a `?` after it belongs to the fragment. |
| `_lang_url_prefix(path, url_code)` | gluing a language onto a path (`/` → `/fr`, never `/fr/`) |
| `_lang_url_prefix_unless_default(path, lang, force_default_lang=False)` | the same, but the default language takes no prefix. Every "path in this language" answer goes through it: `_url_localized`, the canonical-slug 301 in `_pre_dispatch`, `website`'s trailing-slash 301 |
| `_lang_url_split(path, url_codes=None)` | the inverse: recognizing a leading `url_code`. Only `url_code`, never the full `code` — `/fr_FR/…` is case /7's business |
| `_frontend_url_codes()` | *what may appear* as a language prefix. `website` narrows it per site, so all three above narrow with it |

Built on them:

| Caller | Question it answers |
|---|---|
| `_url_for` | "make this href right for the current page's language" — every href of every frontend page (`ir.qweb._post_processing_att`) |
| `_url_localized` | "give me this URL *in* language X", re-slugging its `<model(…)>` segments |
| `_is_multilang_url` | "is the content at this path translated?" — never for `_is_asset_or_webclient_path`, which `website`'s rewriting `_url_for` excludes on the same test |
| `url_rewrite` | "what does the routing table say this path resolves to?" (ormcached, request-free) |

`_lang_url_split` takes the codes explicitly so a **request-free** caller — a
sitemap builder, a cron, `_is_multilang_url` — can ask at all.

`_url_for` puts a language in a URL only when the site serves it, with one
deliberate exception: a language the *caller named* (`_url_for(url, "de_DE")`)
is kept, as its `url_code`, even when the site does not list it, because the
target may serve more languages than the site does — `survey` serves every
installed one. A language that merely came from the context, typically a backend
user's, falls back to the default. With `website` installed, "served" and
"default" mean the website's even in a backend request (`TRAPS.md` §12).

## The error page

```
exception ─→ _prepare_exception_code_and_values ─→ (status, values)
                                              │
              status in (404, 403) ───────────┤─→ _serve_fallback()  (website's CMS pages)
                                              │
                             _get_error_template(code, values) ─→ xmlid
                                              │
                             _get_error_html  ─→ (status, html)
```

**The fallback runs once per request.** An unrouted URL has been through
`_serve_fallback` in the core (`_serve_ir_http_fallback`) before its `NotFound`
reaches `_handle_error`, which marks `request.attempt_scratch.fallback_tried`;
`_handle_error` tries the fallback itself only for a 404/403 raised by a
*routed* endpoint. Running it twice cost every unrouted 404 a second CMS-page,
attachment and redirect lookup (5 queries, ~4 ms). The traceback in the error
values is `lazy` for the same reason: only an editor or debug mode renders it.

**Status and template are two decisions, taken by two methods**, and that split
is load-bearing: `_handle_error` keys the `_serve_fallback` attempt off the
*status*, so an override that smuggled a template through the status (as
`website` once did) silently denied a designer the fallback a visitor got.
To render a different page for the same status, override `_get_error_template`.

`_get_error_html` degrades to `http_routing.4xx` / `http_routing.http_error`
when no template matches the status, **keeping the status**. So does
`_handle_error` when the status page itself fails to render: it logs, falls
back to `http_routing.http_error`, and still answers the original status. It
used to answer `418 I'm a teapot` there, which turned a broken 404 template into
a site where every missing URL told crawlers and monitors something else.

### The templates

| xmlid | Role |
|---|---|
| `http_routing.error_page` | the shared 4xx body: heading, hint, then the debug accordion or the error message |
| `http_routing.400`, `http_routing.403`, `http_routing.415`, `http_routing.4xx` | one `t-call` each into `error_page`, carrying only a `t-set` heading and hint. A status with nothing to add over `4xx` gets no template of its own (422, a refused form, is one): `_get_error_html` falls back to `4xx` |
| `http_routing.404` | its own page (illustration + popular links); `website` inherits it |
| `http_routing.500` | deliberately standalone — **no `frontend_layout`, no assets, no `csrf_token`**, because the cursor may already be broken when it renders |
| `http_routing.http_error` | the generic fallback, and the page ~20 controllers across other modules answer a refusal with, through `_serve_error_page` — treat its values as a public contract |
| `http_routing.error_message`, `http_routing.http_error_debug` | structural fragments used by the above; the debug accordion renders only under `editable or debug` |

**A controller answers a refusal with `_serve_error_page(title, message,
status=200)`, never `request.render("http_routing.http_error", …)`.** The page
is a frontend page: with `portal` or `website` installed its layout reads
`frontend_languages` / `website`, which only `_prepare_frontend_environment`
puts in the qcontext, and only for a request `_match_and_flag` marked frontend. A route that is not `website=True` --
a backend download, an OAuth callback, an export -- is made one by the helper
(`is_frontend`, never multilang, the frontend lang, `_frontend_pre_dispatch`)
before it renders; see `TRAPS.md` §11.

The 4xx pages share one body and differ only by a `t-set` heading and hint. That
text is still an ordinary translatable QWeb term — `TestErrorPageTranslatability`
exists because losing it would not fail any other test, it would quietly serve
English error pages to everyone.

## Slugs

A slug is `[<name>-]<id>`, built from `_SLUG_NAME` / `_SLUG_ID` / `_SLUG_END` so
the matching regex (`_UNSLUG_ROUTE_PATTERN`, non-capturing — werkzeug forbids
groups in a converter regex) and the parsing one (`_UNSLUG_RE`) cannot drift.

`ModelConverter` rejects **id `0`**: it is the one id the grammar accepts that
can never name a record, and nothing downstream catches it (see `TRAPS.md`).
A negative id is retried as its absolute value, because `foo--5` is far more
likely "a record named `foo-`, id 5".
