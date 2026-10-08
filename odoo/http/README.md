# `odoo/http/` — the HTTP layer / WSGI application

This package prepares and dispatches every HTTP request to its controller: from
a raw request arriving on the WSGI entrypoint to a `Request` reaching a module
controller with a fully set-up ORM.

Application developers meet this package through `Controller` and the `@route`
decorator, which register the methods that deliver web content to matching URLs.

`doc/architecture/runtime.md` sketches this flow in three lines and
flattens it deliberately; **this file is the canonical, unflattened version.**
It lived in
`odoo/http/__init__.py`'s module docstring until `4ffeacacd8c` stripped
docstrings from `odoo/`, which left the sketch as the only surviving copy. It is
a document rather than a docstring now so that the strip policy and the call
graph stop competing for the same lines.

## Call graph

Every processing layer a request passes through before the `@route`-decorated
endpoint runs:

```
Application.__call__
    if path is like '/<module>/static/<path>':
        Request._serve_static

    elif path in Application.db_free_paths:
        Request._serve_nodb

    elif not request.db:
        Request._serve_nodb
            App.nodb_routing_map.match
            Dispatcher.pre_dispatch
            Dispatcher.dispatch
                route_wrapper
                    endpoint
            Dispatcher.post_dispatch

    else:
        Request._serve_db
            env['ir.http']._match
            if not match:
                transaction.retrying(Request._serve_ir_http_fallback)
                    env['ir.http']._authenticate_explicit('public')
                    env['ir.http']._serve_fallback
                    env['ir.http']._post_dispatch
            else:
                transaction.retrying(Request._serve_ir_http)
                    env['ir.http']._authenticate
                    env['ir.http']._pre_dispatch
                    Dispatcher.pre_dispatch
                    Dispatcher.dispatch
                        env['ir.http']._dispatch
                            route_wrapper
                                endpoint
                    env['ir.http']._post_dispatch
```

The `Request._serve_*` methods are defined on `_RequestServeMixin` in
`_serve.py`; `Request` (in `request_class.py`) composes it.

## The stages

**`Application.__call__`** — WSGI entry point. Sanitizes the request, wraps it in
a werkzeug request and itself in an Odoo HTTP request, exposes it at
`http.request`, gives it an id (`request.id`: a well-formed `X-Request-Id` the
client sent, else a fresh token) that every log line of the request carries as
`rid:` and every response echoes as `X-Request-Id`, then forwards to `_serve_static`, `_serve_nodb` or `_serve_db`
depending on the request path and the presence of a database. Also responsible
for logging any error and encapsulating it in an HTTP error response. The
request is closed when the WSGI server closes the response body, not when
`__call__` returns, and so is the request a `reroute` built from it: a streamed
body may still read an upload the reroute handed over. `REQUEST_URI`, the
request target as the client sent it, is guaranteed on the environ (`RAW_URI`,
else the quoted path and query): PEP 3333 does not define it, the transport and
werkzeug's server set it, and website reads the original URI through it after a
reroute.

When the database cannot be reached (`RegistryError`), the entry point tells a
database that is gone from one that is out of reach for now. Gone (not in the
catalogue, or failing for a non-transient reason): the session is logged out
and the request is served database-free, a select-db path rerouted without its
`?db=`. Out of reach for now (a connection or pool failure on a database the
catalogue still lists): `503 Service Unavailable` with `Retry-After`, the
session untouched, the body in the dispatcher the request's media type picks.
The no-database routing map uses the same signed `int` converter as the
database maps (`SignedIntConverter`, owned here and imported by `base`).

**`Request._serve_static`** — streams an already-resolved file via
`Stream.prepare_response`. A static file needs no database: `__call__` resolves
the path before `_post_init`, so the database is never selected for it, and the
session is read only for its debug mode (`debug=assets` serves without cache). It does **not** resolve the path: `Application.resolve_static_file`
does, before the request reaches here, with `file_path()` plus a
`Path.resolve().is_relative_to()` containment check. It takes the request path
as a path — already decoded, so never re-parsed as a URL, where a decoded `?`,
`#` or `;` would cut the name short. `get_static_file_path(url, host)` is the
URL form `ir.attachment` asks with: it strips scheme, host, query and fragment,
then delegates. There is one resolver on
purpose — a second one lived in this method until it was found to be unreachable.

**`Application.db_free_paths`** — the exact paths of the no-database routing
map whose route declares `@route(database=False)` (the process probes
`/web/health`, `/web/healthz`, `/web/readyz`, `/web/metrics`). `__call__` serves
them through `_serve_nodb` before `_post_init`: no session is read, no database
selected, no cursor opened, whatever cookie or `X-Odoo-Database` the request
carries; the request holds a throwaway session that is never saved. Such a route
must be `auth='none'` (`RouteDefinitionError` otherwise), and a check it needs
opens its own connection (`/web/readyz` asks the `postgres` database).

**`Request._serve_nodb`** — handles `@route(auth='none')` endpoints when there is
no database connection. It matches the `auth='none'` endpoint from the request
path and delegates to the `Dispatcher`. An unmatched path infers a dispatcher
from the request's media type, exactly as `_serve_db` does, so a JSON client is
answered in JSON and a browser gets the `NOT_FOUND_NODB` page. `application/json`
is both `json2`'s and `jsonrpc`'s media type: a body that is a JSON-RPC 2.0
envelope is answered in that envelope, its `id` echoed, anything else as a
`json2` problem document. A JSON-RPC error answers 200, a fault of the call,
except for an HTTP exception of 500 or more: that one keeps its status and
headers (the 503 and `Retry-After` of a database out of reach), which the web
client retries as a lost connection.

**`Request._serve_db`** — handles every non-static request when a database can be
reached. Opens a registry, manages the request cursor and environment, and
decides read-only versus read/write: `check_signaling`, `match` and
`serve_fallback` share one read-only cursor; `_serve_ir_http` reuses that same
read-only cursor, or a read/write one. Without a replica the cursor handed out
for the signaling check is already read/write and is kept: a readonly route
goes on in the check's transaction, since a read-only transaction never fails
to serialize and a fresh one would cost a ROLLBACK and, once the handler runs
SQL, a second BEGIN for nothing (a handler that runs none ends the check's
transaction with a COMMIT instead of the ROLLBACK, the same one message), while
a writing route rolls it back first so its snapshot starts with the handler.

**`Request._serve_aborted`** — handles explicit response control flow;
it does not appear in the graph above. An exception carrying
its own response (`abort(prepare_no_content_response())`, the CORS preflight) is delivered
verbatim; a status-less one goes through the dispatcher, so the error body
matches the route's media type rather than always being werkzeug's HTML page.
Inside a database transaction, `_serve_transaction_target` converts these
exceptions into returned responses so the transaction commits normally.

**`service.transaction.retrying`** — manages the cursor, the environment, and the
exceptions raised while executing the wrapped callable. Recovers from
serialization errors; resets the environment and **re-raises** everything else.
It does *not* attach an HTTP response — `_serve._update_served_exception`, which
wraps both `retrying()` calls, is what asks `ir.http._handle_error` for one. The
read-only → read/write promotion is `_serve_db`'s, not `retrying`'s: it catches
`psycopg.errors.ReadOnlySqlTransaction`, replays the retry participant and calls
`retrying()` a second time on a fresh read/write cursor. `retrying` also
performs the commit and signals registry changes once the callable returns.

**`ir.http._match`** — matches the controller endpoint corresponding to the
request path. Note the significant override for portal and website in the
`http_routing` module.

**`ir.http._serve_fallback`** — finds alternative ways to serve a request whose
path matches no controller: an attachment URL, a blog page, and so on. The
caller authenticates explicitly as `public`, including validation of an
authenticated cookie, before accessing these resources.

**`ir.http._authenticate`** — ensures the user on the current environment
satisfies `@route(auth=...)`. Using the ORM outside abstract models is unsafe
before this runs.

**`ir.http._pre_dispatch` / `Dispatcher.pre_dispatch`** — prepares the system for
the request; often saves extra query-string parameters in the session (`?debug=1`).
It settles the request's context first (`_update_request_context`: the language,
and for a frontend route the website, its companies and the frontend language),
and only then checks each record argument of the route for read, so an access
domain reading the website or the companies decides the argument under the
context the endpoint then reads it with.

**`ir.http._dispatch` / `Dispatcher.dispatch`** — deserializes the request body
into `request.params` according to `@route(type=...)`, calls the endpoint, and
serializes the return value into a `Response`. An endpoint that returns an
`HTTPException` instead of raising it has it raised for it, whatever the route
type (`check_endpoint_result`): a `jsonrpc` or `json2` route used to serialize
the exception's text as a successful result. A `jsonrpc` route that returns a
`Response` is a `TypeError`, as an `http` route returning a dict is: the
JSON-RPC envelope cannot carry one (a `json2` route serves it as is).

**`ir.http._post_dispatch` / `Dispatcher.post_dispatch`** — post-processes the
response: injects headers such as Content-Security-Policy and stages the
session through `Request._save_session()`. Every `text/html` response gets
`script-src 'nonce-<n>' 'strict-dynamic' 'unsafe-eval' 'unsafe-inline' https:;
object-src 'none'; base-uri 'self'` (`_csp.py`), appended to a policy the
controller already set (`frame-ancestors`) unless that one names `script-src` or
`default-src`. The nonce is the request's: QWeb writes it on every `<script>` and
`modulepreload` it compiles from a template, never on markup that reaches the
page as a value, so an escaping slip renders a script the browser refuses. A
browser that knows nonces ignores `'unsafe-inline'`; one that knows
`'strict-dynamic'` also ignores `https:` and trusts what a nonced script loads.
`'unsafe-eval'` stays while a page compiles any OWL template itself: a bundle's
templates arrive compiled (`/web/assets/owl/…`, `addons/web/static/src/core/precompiled_templates.js`),
but inline `xml` templates and view archs still compile in the browser. Static files
(`_serve_static`) never reach post-dispatch and carry no script policy. A database-bound request reserves a
rotation's new SID and token in memory, then persists the session and publishes
its cookie after a successful commit. Rollback restores the attempt's original
session. Error rendering starts after rollback, so an error handler can still
log out an expired session without preserving failed controller mutations.

Liveness is the request's call, not the page's: the store records the file's
mtime on load, and `_save_session` keeps a session alive — `utime` on the file
and a fresh cookie — once that age passes half the inactivity budget,
whichever request notices first. The budget is `sessions.max_inactivity_seconds`
for an authenticated session; an anonymous one carries a `SESSION_LIFETIME`
cookie, but `ir.http._gc_sessions` reaps every session idle past the inactivity
setting, so its liveness is judged against the lower of the two. An active
session therefore costs at most two liveness writes per budget window, and an
RPC-only client stays alive without ever loading a page.

`_save_session` decides: bound to the request's own live cursor it binds the
transaction and stages; otherwise it calls `_persist_session`, the one place
that writes the store and stages the cookie. `_bind_session_transaction`
registers cursor callbacks and captures the session snapshot. `_flush_session`
is idempotent: the postcommit callback invokes it, and the successful return
from `retrying` also invokes it for cursor adapters such as `TestCursor` that
suppress transaction callbacks; it persists through `_persist_session`.
`_restore_session_snapshot` is its rollback twin: the postrollback callback
invokes it, and so does `RequestRetryParticipant.on_rollback`; every call lands on
the same state, so the order does not matter. The snapshot stays armed until the
commit or the next bind, so a handler's own rollback followed by a retry still
restores. The one case that reads the disk: an explicit-environment save
(`request._save_session(env)` against another database) persisted the session
during the attempt, possibly rotating its file away — then the live copy under
the current sid is the identity the cookie must carry, and the snapshot's file
may no longer exist; `_load_session` reloads it without re-selecting the
database. A handler's own rollback clears the binding; a later save binds the
new transaction again.
Database-free requests and saves explicitly bound to another database keep
their immediate persistence path.
Read-only promotion is allowed only before commit, while the original cursor
is open. A postcommit SQL error propagates without replaying the handler.

The filesystem store serializes merge/write and revocation with stable lock
stripes shared by processes; a plain read takes no lock, since every write
replaces a session atomically, and a read that finds a corrupt session discards
it only under the lock and only if the corrupt bytes it read are still there.
A read that fails for any reason but absence (EIO, EACCES) is a
`SessionStorageError` — an `OSError`, the one storage error every backend
raises — never "no such session", which would hand out a fresh anonymous one. A loaded session whose file has disappeared
cannot recreate that file. Saves merge changes against the loaded snapshot,
preserving independent top-level and nested dictionary edits; conflicting
edits to the same scalar or list still use the last writer. Rotation writes the
successor before changing the predecessor, and restores the original in-memory
identity if persistence fails. Filesystem persistence and PostgreSQL commit
remain separate: a filesystem failure after commit cannot undo database work.

Hard rotation revokes the whole session identifier family, including predecessor
cookies retained during soft rotation's grace period. A missing soft-rotation
successor is expired, never reconstructed. Soft rotation merges concurrent edits
before creating its successor; hard authentication transitions start a new family.
Login or logout upgrades an already staged soft rotation to a fresh hard family.
Late predecessor saves follow the live successor chain under the family lock;
adoption rejects a changed database or user rather than mixing authentication
state. A concurrent identity update merged before soft rotation gets a token
for the final user and successor SID. The in-memory integration store uses the
same merge and rotation logic, replacing only the storage operations.

**`ir.http._handle_error`** — absent from the graph; called for unmanaged
exceptions (serialization or read-only) raised inside
`service.transaction.retrying`. Returns an HTTP response wrapping the error.

**`Application._finalize_error_response`** — the error response built above
bypasses the normal dispatch flow, so the entrypoint runs
`Dispatcher.post_dispatch` over it explicitly before handing it to the WSGI
server. Without that step an error response would carry none of what
post-dispatch contributes — CORS headers, the `session_id` cookie and the session
save behind it, CSP — which is why the error path is the *only* place that calls
post_dispatch out of band. A request refused before its session was read (a
rejected method, a NUL in the path, a failing `_post_init`) has no session to
save and no dispatcher state to publish; it gets the security headers alone.

## Module map

`doc/architecture/module.md` groups these modules into `[foundation]`,
`[serving]` and `[features]` tiers; the direction between them is the
`http-features-below-serving` contract, which holds `[foundation]` below
`[serving]` as well, at module scope (a `TYPE_CHECKING` block or a deferred
import does not count); no module of the package reaches `odoo.addons`. Every
serving or feature module owns a `DebugLog`, and a broad `except` that swallows
emits an event or a log line. Review holds all three.

| Module | Tier | Contents |
|---|---|---|
| `__init__.py` | — | Public API: re-exports every symbol of the package |
| `application.py` | serving | `Application`: the WSGI callable, static/nodb/db routing decision, error logging and `_finalize_error_response` |
| `_serve.py` | serving | `_RequestServeMixin`: `_serve_static`, `_serve_nodb`, `_serve_db`, `_serve_aborted`, `_serve_ir_http`, `_serve_ir_http_fallback` |
| `request_class.py` | serving | `Request`, composed from the serve / response / CSRF / session mixins; what is left on the class itself is request identity (`params`, `cookies`, `best_lang`, `update_env`, the profiler hook, `_reset_for_replay`) and the two namespaces other modules keep their state in: `request.scratch` for the whole request (an integration allowance consumed once however often the transaction is replayed) and `request.attempt_scratch` for one transaction attempt, which `_reset_for_replay` replaces (a response's `version`, the ESM page state) |
| `_session_lifecycle.py` | serving | `_RequestSessionMixin`: loading the session and choosing the database (`_load_session`, `_select_dbname`), then staging, persisting, flushing and restoring it around the transaction (`_save_session`, `_persist_session`, `_bind_session_transaction`, `_flush_session`, `_restore_session_snapshot`) and folding the staged headers into the response |
| `_response.py` | serving | `_RequestResponseMixin`: `prepare_response`, `prepare_json_response`, redirects, `render` |
| `_csrf.py` | serving | `_RequestCsrfMixin`: CSRF token generation and validation |
| `_csp.py` | serving | `_RequestCspMixin` and `apply_script_policy`: the request's script nonce (`request.csp_nonce`, drawn on first use), the mode read from `ir.config_parameter` `http.csp_mode` (`enforce`, the default, `report-only` or `off`), `request.csp_unsafe_eval` for a page that compiles no template at run time, `request.nonce_scripts(html)` for trusted HTML that carries its own `<script>`, and the `text/html` policy `Dispatcher.post_dispatch` adds |
| `dispatcher.py` | serving | `Dispatcher` and its three subclasses (`HttpDispatcher`, `JsonRPCDispatcher`, `Json2Dispatcher`), selected by `routing["type"]`, and `is_debugger_handover_required` — the one rule, read by `_serve` and `Application`, for leaving an error to the werkzeug debugger (`debugger_attached` is set by `service._factory` when it wraps the app). `pre_dispatch` also applies the request's statement budget: `@route(statement_timeout=<seconds>)`, or a dispatcher class's `statement_timeout`, is remembered by the request's cursor and armed as `SET LOCAL statement_timeout` before the first statement of every transaction it runs (a mid-request commit or the promotion replay keep it), so a runaway query on that route dies with the statement instead of the worker. A `json2` error body is an RFC 9457 problem document (`type`, `title`, `status`, `detail`, served as `application/problem+json`) followed by Odoo's own `name`, `message`, `arguments`, `context`, `debug` |
| `routing.py` | serving | `route()`, the `route_wrapper` it builds, `LazyCompiledBuilder` / `FasterRule`, `prepare_routing_map` (used by both maps the framework serves from), `_generate_routing_rules` over the assembled controllers, and the routing-parameter registry |
| `controller.py` | serving | `Controller`, the controller registry, and the assembly of one class per top controller from the installed modules' leaves (`_get_controllers`, `_group_controller_trees`) that the routing map is generated from |
| `session.py` | serving | `Session`: the mapping the request carries, its dirty/baseline tracking, login, logout and the hard-rotation demand |
| `_session_store.py` | serving | `SessionStore`, the policy every backend shares — keys, load, save with merge, soft and hard rotation, successor adoption, family revocation, keep-alive — over an eight-method storage surface (`_lock`, `_read`, `_read_payload`, `_write`, `_unlink`, `_touch`, `_sids_in_family`, `vacuum`; `_read_payload` is the raw bytes a corrupt session is compared against before it is discarded). Three backends implement it: `get_live(sid)` follows soft rotations to the live successor for callers outside
the request (the bus websocket). `FilesystemSessionStore` (stripe `flock`s shared across processes, atomic and optionally durable writes, sharded by the sid's first two characters), `PostgresSessionStore` (one `http_session` table in the database `http_session_db` names, `pg_advisory_xact_lock` per stripe, shared by every host; a read outside a lock is one autocommit statement, `Connection.get_rows_autocommit`) and `MemorySessionStore` (one `RLock`, this process only). `http_session_store` picks one; `Application.session_store` builds it |
| `stream.py` | serving | `Stream`: file/attachment streaming and conditional responses |
| `wrappers.py` | serving | `HTTPRequest`, `_Response`, `Headers`, `ResponseCacheControl`, `prepare_no_content_response`, `prepare_content_disposition_header`, `prepare_exception_response` — the werkzeug wrappers; the last is how the package turns an `HTTPException` into a facade `Response` (a status-less one answers 500), so werkzeug itself is no longer patched. **`HTTPRequest.environ` is a filtered copy**: every `werkzeug.*`, `wsgi.*` and `socket*` key is dropped except `wsgi.url_scheme` and `werkzeug.proxy_fix.orig`, so `environ["wsgi.input"]` raises `KeyError` — `raw_environ` is the unfiltered one |
| `_cookies.py` | serving | `FutureResponse` (the headers and cookies staged before a response exists), `get_cookie_identity`, the `set_cookie` defaults (consent, `Secure`, `SameSite`) and the same-identity de-duplication both `_Response` and `FutureResponse` set cookies through. **The cookie value codec**, shared with `web/static/src/core/browser/cookie.js`: `encode_cookie_value` percent-encodes (UTF-8) every character outside RFC 6265 cookie-octet, and `%` itself, so werkzeug never quotes and never drops what Odoo writes; `parse_cookie_header` is the one reader — `HTTPRequest.cookies`, and so `request.cookies`, come from it, not from werkzeug's `parse_cookie` — splitting on every `;` as browsers do, never decoding a name, and decoding a value with `decode_cookie_value`: `decodeURIComponent` semantics (a malformed escape or invalid UTF-8 leaves the value raw, so a legacy value without escapes reads unchanged), except that a whole quoted string is the werkzeug < 3.1.9 octal-escaped form and is unslashed instead |
| `core.py` | serving | `_request_stack` (a werkzeug `LocalStack`), the `request` proxy bound to it, and `borrow_request` |
| `_dbfilter.py` | serving | `get_dbs_served` — the package's one database-listing entry point, cached — `filter_dbs_served` and the `dbfilter` machinery. The request never calls them directly: `Application.get_dbs_served(host)` / `filter_dbs_served(dbs, host)` are the injection point, which is what a test overrides. `Application.get_dbs_listed(host)` is what a visitor may be shown: the same list, refused with `AccessDenied` when `list_db` is off |
| `_cors.py` | serving | `is_cors_preflight`, `resolve_cors_same_host`, and the header staging every dispatcher runs in `pre_dispatch`: `stage_cors_headers` (origin, credentials, methods, exposed headers) and `stage_preflight_headers` (max-age, allowed headers) |
| `_rpc.py` | serving | `dispatch_rpc` — the XML-RPC service dispatcher behind `/xmlrpc/2`, run with the request borrowed off the stack |
| `_error_serialization.py` | serving | `serialize_exception` and the dev-mode rule for what an error body may reveal |
| `_retry.py` | serving | `RequestRetryParticipant`: restores the session and rewinds uploads (`rewind_uploaded_files`) when `retrying()` replays a handler; passed explicitly by the request |
| `openapi.py` | features | `prepare_openapi_document`: an OpenAPI `3.1.0` document generated from the routing map — path and query parameters, JSON bodies with object schemas for dataclass and TypedDict parameters, `enum` / `minimum` / `maximum` / `pattern` from the constraints, `oneOf` with a `discriminator` for a discriminated union, and for `jsonrpc`/`json2` routes the response schema read from the handler's return annotation (`get_response_schema`), or `{}` — any JSON value — when there is none, inside the `{jsonrpc, id, result}` envelope for `jsonrpc` |
| `_params.py` | features | `ParamSpec` and the annotation-driven coercion behind `@route(typed=True)`: primitives, `list[...]`, `X | None`, `Literal[...]` and `Enum` choices, `Annotated[T, Range(ge=, le=)]` and `Annotated[str, Pattern(regex)]` constraints checked after coercion, and `@dataclass` or `TypedDict` types built field by field from a JSON object (unknown or missing required fields are a 400 naming the field; a class with an uncoercible field, or a recursive one, is left uncoerced; a constraint on an object or a list is declined). A union of object types is coerced when `Annotated[A | B, Discriminator("kind")]` names a field each member pins to one `Literal` value; the tag picks the variant and the variant validates the rest. An undiscriminated union stays uncoerced |
| `geoip.py` | features | `GeoIP` lookup exposed on the request (`_GeoIPNull` when unavailable). The readers behind it (`Application.geoip_city_db` / `geoip_country_db`) re-stat their file at most once a minute and reopen it when the path, inode or mtime moved, so a `geoipupdate` refresh or a database added after boot is picked up without a restart |
| `settings.py` | foundation | `HttpSettings`: the frozen snapshot of every option the serving tier reads (`dbfilter`, `db_name`, `dev_mode`, `x_sendfile`, `data_dir`, `server_wide_modules`, the GeoIP paths, `proxy_mode`/`proxy_hops`, `list_db`, `session_store`/`session_db` — validated: an unknown backend, or `postgres` without a database, refuses at the first read), `from_config` to build one, and the slot (`current`, `installed`, `override`) the package reads it through. The slot holds no snapshot in production: `current()` derives one from the live option dict, memoised on `config.generation` — a counter every write to any option layer moves, and one that answers a fresh object while a test has swapped `config.options` for a plain mapping — so a key written after boot still reaches the serving tier at the cost of one derivation, and a test that wants a fixed view installs its own |
| `constants.py` | foundation | Package-wide constants, `prepare_allow_header`, and the session and select-db path registries with their `is_select_db_path` predicate |
| `exceptions.py` | foundation | the HTTP exception vocabulary addon code raises — werkzeug's `NotFound`, `Forbidden`, `BadRequest`, `Unauthorized`, `HTTPException`, `abort` and the rest, re-exported so a controller never imports werkzeug — plus `RegistryError`, `SessionExpiredException`, `is_http_answer` (a 4xx is an answer, never a debugger case), and `get_error_response`/`set_error_response` — the only sanctioned way to read and write the `error_response` an exception carries |
| `_protocols.py` | foundation | `HttpExtension` — the `Protocol` `ir.http` satisfies, pinned by `TestIrHttpImplementsProtocol`; `Endpoint`/`HasRouting`/`RoutedMethod` for the attributes `@route` stuffs onto a handler. `RequestState` alone is `if TYPE_CHECKING:` — it is `object` at runtime |

## Related

- `doc/architecture/module.md` — the framework-wide subsystem map and the
  enforced dependency contracts, including `http-features-below-serving`.
- `doc/architecture/ARCHITECTURE.md` — the front door: context, forces,
  mechanisms, and the index of the views.
- `odoo/service/transaction.py` — `retrying()`, which owns commit and transaction
  retries. `_serve.py` owns read-only → read/write promotion.
