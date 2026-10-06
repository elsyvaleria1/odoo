# First Visit Round Trips — an Action Comes With Its Views

Status: **Fixed for window actions loaded by id, xml id or path.** Date: 2026-10-03.
Scope: the requests between a click on a menu the client has not opened before
and the first data call.

## Why this was opened

A first visit was three round trips, each waiting for the previous answer:
`/web/action/load`, then `get_views` with the views the action names, then the
data call, which needs the view's fields. A cold boot paid the same chain after
its assets. At 100 ms of latency that chain is most of a first visit.

`get_views` waits only for the action: the server knows the action when it
answers it, so it can answer the views in the same response.

## The rule

* **A window action not in the cache is loaded with its views.** On a miss,
  `/web/action/load` is asked with `view_options` (the client's `mobile` and
  `debug`) and `view_context` (the caller's context). It answers
  `{action, views_request, views}`: the action, the `get_views` request the
  client is about to make as `_views_request` reconstructs it from the action
  (`preprocessAction`, `prepareViewInfo`, `view_service.loadViews`), and the
  answer to it. Without `view_options`, or when it cannot build the request
  (another action type, embedded actions, an action context it cannot
  evaluate) or read the views, it answers the action alone, as before.
* **The client uses the views only for an identical request.** The action
  loader offers them to the view service (`offerViews`); `loadViews` takes an
  offer whose request, compared key-order-insensitively, is the one it builds,
  and makes the call otherwise. A wrong reconstruction costs server time, not
  correctness.
* **Each answer is stored as the call it replaces.** A cached RPC can be given
  a `cache.fetch` that answers in the network's place: the action is stored
  under `/web/action/load`'s key, the views under `get_views`', and both are
  read and revalidated afterwards like any other entry.
* **Only a miss asks for the views.** `fetch` is told, at once, whether the
  cache already held a value (`RPCCache.holds`: RAM, or the keys the disk is
  known to hold, read once per table and kept up to date as this tab writes
  and invalidates). A cached action's revalidation asks for the action alone,
  beside the view service's own revalidation of the views. The answer is a
  hint: while the disk's keys are still being read, or after another tab
  wrote one, it says "not held", and the worst case is one revalidation that
  carries views. Waiting for the disk read instead would have put an
  IndexedDB round trip in front of every first load.
* **Nothing stale gets in.** Every offer comes from the server at that moment.
  A view edit clears `get_views`' table and the pending offers with it; it never
  clears `/web/action/load`'s, which is why the views are not kept inside the
  cached action.

## After

Readings FROZEN at `af783e1071ae` (the change uncommitted on top), a server with
four workers, the request-waterfall instrument of the 2026-10-01 measurement day (agromarin-knowledge research), two rounds interleaved, each after a warm-up on
a freshly started server; content on screen, milliseconds:

| First visit, 100 ms of latency | Serial data round trips | Before | After |
|---|---|---|---|
| Customers / Invoices (list) | 3 → 2 | 390–411 | 280–293 |
| Invoicing dashboard (kanban) | 4 → 3 | 499–518 | 401–427 |
| Invoice Analysis (graph) | 3 → 2 | 347–360 | 250–258 |
| Invoicing / Settings (form) | 3 → 2 | 683–706 | 534–659 |
| Contacts (kanban) | 3 → 2 | 510–543 | 396–559 |
| CRM pipeline (server action) | 5 → 5 | 589–655 | 585–601 |

They were taken before a cached action's revalidation stopped asking for the
views; no first visit is a revalidation, so every row takes the path described
above. A server action's window action comes from `/web/action/run`, not the loader,
and kept its `get_views` until the section on server actions below. A cold boot drops the same round trip (6 → 5) and
reads within noise (1586–1745 → 1555–1760 ms at 100 ms of latency): on a server
without workers its data call leaves while the templates bundle is still being
served, and waits for it.

## After the data call: a list's currency rates

The boot's last serial round trip was `res.currency/read`, after the data
call: a list whose arch sums a monetary field held its first render until
the currency rates arrived (`list_aggregates.js`, `onWillStart`), although
rates convert a total only when its rows span several currencies. The
list now waits for them only then; a total in one currency renders at once,
and rows that later come to span several fetch the rates and show the total
when they arrive, as a selection or a reload already did.

Readings FROZEN: before at `e8971b5dabb7`, after at `8898ab07af4f`, which
carries the change (it landed inside `a46e7ff898a0`); same instrument, 100 ms
of latency, Contacts as the landing page:

| Boot | Serial data round trips | Before | After |
|---|---|---|---|
| cold cache | 5 → 4 | menus, translations, action, `web_search_read`, rates | menus, translations, action, `web_search_read` |
| warm cache | rates read gone | menus, translations, rates | menus, translations |

## A server action's window action, and two checks after the data

The CRM pipeline (a server action) and the Invoicing dashboard still waited on
round trips the rule above does not reach:

* **`/web/action/run` answers like `/web/action/load`.** With `view_options`
  and `view_context` (the doAction's `additionalContext`, which the returned
  action is preprocessed with), a window action comes with `views_request` and
  `views`. A run is never cached, so the client says which request it already
  holds: the view service remembers, per server action, the request its last
  answer carried (`rememberRunViews`, kept in localStorage), and while
  `get_views`' cache still holds it (`orm.isCached`, `rpc.cacheHolds`) sends
  it as `views_known`. A request equal to it travels without its views; a
  changed action, a view edit or an evicted entry brings them back, at no
  round trip.
* **The session lists the user's groups** (`group_refs`), so `user.hasGroup`
  answers without a call: the pipeline's column progress bar asked for
  `crm.group_use_recurring_revenues` after `read_progress_bar` had answered.
* **A purchase journal's dashboard data says whether the sample bill is
  offered**, which the bill guide asked `is_sample_action_available` for
  after the journals' data.

Readings FROZEN, one run each of the same instrument at 100 ms of latency,
content on screen in milliseconds; the first column's run had a demo
install loading the machine:

| First visit | at `8898ab07af4f` | groups, `35ff3afcd916` / sample flag, `7a12ad2d4603` | run with views, on `03524b9cddb5` |
|---|---|---|---|
| CRM pipeline | 5 round trips, 609 | 4, 492 | 3, 398 |
| Invoicing dashboard | 3 round trips, 532 | 2, 406 | — |

A repeat run of the pipeline, in the same tab or after a reload, answered
1308 bytes instead of 98622: the views stayed in the cache and were not sent.

## Held by

| Reading | Held by |
|---|---|
| the request reconstructed for list, form-only, dialog, view references, mobile and debug; an unreadable action context and a call without `view_options` answer the action alone | `tests/test_action.py`, `TestLoadActionWithViews` |
| a miss asks for the views and offers them, a cached action asks for nothing, an answer without views is the action, a failed preload falls back to the plain call | `static/tests/webclient/actions/action_loader.test.js` |
| an offer taken for the exact request and kept, refused for another request, dropped by a view change | `static/tests/views/view_service.test.js` |
| `cache.fetch` answers in the network's place and is stored; `holds` answers from RAM, then from the disk's keys, forgets them on invalidation, and works without a disk | `static/tests/core/network/rpc_cache.test.js` |
| a total in one currency renders without the rates; rows that come to span several fetch them and convert | `static/tests/views/list/list_aggregates.test.js` |
| `/web/action/run` with `view_options` answers the views; a request the client says it holds travels without them; a changed one brings them back | `tests/test_action.py`, `TestRunActionWithViews` |
| a first run asks for the views and offers them; a held one sends `views_known` and takes the action alone | `static/tests/webclient/actions/server_executor.test.js` |
| a server action's remembered request is known only while its views are cached | `static/tests/views/view_service.test.js` |
| a session listing the groups answers `hasGroup` without a call | `static/tests/core/user.test.js`; `tests/test_res_users.py` (base) |
| a dashboard card's bill guide reads the sample flag from its data | `account/static/tests/bill_guide.test.js` |
