# State Management — the JS `Store` / `Record` framework

> The `mail` module ships its **own client-side reactive ORM** in
> `static/src/model/`. It is the heart of the Discuss / messaging client: server data is
> upserted into a graph of `Record` instances that OWL components render reactively. This
> doc is the reference for that framework — the mail analogue of web's
> `STATE_MANAGEMENT.md`.

> **See also**: `ARCHITECTURE.md` (where the store sits in the request flow),
> `MODEL_MAP.md` (the Python models these JS records mirror), `ROUTE_MAP.md` (the
> `/mail/data` ↔ `/mail/action` endpoints that feed the store).

## Why a second ORM?

The webclient's `RelationalModel` (`web/static/src/model/`) is view-scoped: one model per
open view, discarded on navigation. Discuss needs a **single long-lived, cross-view graph**
— the same `Message`, `Thread`, `ResPartner` records are shared by the Discuss app, every
chat window, the chatter, and the messaging menu, and are mutated live by bus
notifications. So mail maintains its own store: one `Store` singleton holding a normalized,
reactive, id-keyed record graph.

## The `model/` package

| File | Exports | Role |
|------|---------|------|
| `record.js` | `class Record` | Base class for all models; insert/get/register statics + instance CRUD |
| `store.js` | `class Store extends Record` | The store record; owns the `MAKE_UPDATE` cycle + queue flushing + `insert()` |
| `record_list.js` | `class RecordList extends Array` | A relational field value — an `Array` subclass over a `data: string[]` of localIds; its module-private `RecordListInternal` engine owns inverse maintenance |
| `record_uses.js` | `class RecordUses` | Reverse-relation tracker: `Map<Record, Map<fieldName, count>>` of who points at a record |
| `model_internal.js` | `class ModelInternal` | Per-**Model** field metadata (Maps: Attr/One/Many/Compute/Sort/Inverse/OnAdd/OnDelete/OnUpdate/TargetModel/Type/Default, `idFields`) |
| `record_internal.js` | `class RecordInternal` | Per-**record** engine: `prepareField`, `requestCompute`, `requestSort`, `compute`, `sort`, `onUpdate`, `downgradeProxy` |
| `store_internal.js` | `class StoreInternal extends RecordInternal` | The 8 flush queues + the `UPDATE` counter |
| `make_store.js` | `makeStore(env, {localRegistry})` | Factory: builds reactive Model objects + proxy Classes from `modelRegistry`, wires inverses, bootstraps the Store |
| `misc.js` | `modelRegistry`, `fields`, `AND`, `OR`, type guards | Registry, field factory, id-expression helpers |
| `export.js` | `export *` from `make_store.js`, `record.js`, `store.js` + `{AND, fields, OR}` from `misc.js` | Public entry point (the `*_internal`, `record_list`, `record_uses` modules are imported directly, not re-exported here) |

## Defining a model

Every model is a class `extends Record` with a `static id`, field declarations, and a
trailing `<Class>.register()`. `ARCHITECTURE.md`'s file-count table states how many model
classes there are across `static/src/`. Count them by `.register()` call sites (minus
`Record.register()` for the base class) — **not** by grepping
`extends Record`, which both misses `Attachment extends FileModelMixin(Record)` and falsely
matches `StoreInternal extends RecordInternal`. See the counting note in `ARCHITECTURE.md`.

```javascript
// core/common/message_model.js (shape)
import { Record, fields } from "@mail/core/common/record";

export class Message extends Record {
    static _name = "mail.message";        // python model name (falls back to class name)
    static id = "id";                     // identity field, or AND(...) / OR(...)

    author_id = fields.One("res.partner");
    attachment_ids = fields.Many("ir.attachment", { inverse: "message" });
    reactions = fields.Many("MessageReactions", { inverse: "message" });
    // ...
}
Message.register();                        // adds to modelRegistry (category "discuss.model")
```

- **`static _name`** — the python model name used when routing server data. If omitted,
  `getName()` falls back to the JS class name. **Some registered models omit it**
  (`ChatHub`, `ChatWindow`, `Composer`, `DataResponse`, `DiscussApp`,
  `Failure`, `MessageReactions`, `MessagingMenu`, `MessagingMenuTab`, `MessagingMenuUIState`,
  `Record`, `Rtc`, `Settings`, `Store`, `Thread`, `Volume`; CONVENTIONS.md gotcha 4 has the
  count); the rest declare one. Omitting `_name` is not the same as having no
  server model —
  `Thread` is still reachable from python payloads via `pyToJsModels`, and `Settings` is fed
  by the `res.users.settings` bus type. See CONVENTIONS.md gotcha 4.
- **`static id`** — the identity key. A field name (`"id"`), or a composite/alternate
  expression: `Thread` uses `static id = AND("model", "id")`.
- **`register()`** — `Record.register()` adds the class to `modelRegistry`
  (`registry.category("discuss.model")` in `misc.js`). Distinct from
  `discussComponentRegistry` (`registry.category("discuss.component")` in
  `core/common/discuss_component_registry.js`) used for overridable UI — see ARCHITECTURE.md.

### Subtypes (`static _discriminator`)

A registered model extending a registered model that declares `static _discriminator` (one of
its id fields) is its **subtype**: `make_store.js` `linkSubtypes()` links them, and
`Record.new` creates each record as the subtype its discriminator value names (the subtype's
`_name`). One entity, one record: localIds stay in the root model's namespace, every record
is in each ancestor's `records`, and the subtype's own fields exist only on its records.
Without a discriminator, two registered models related by `extends` only share code.

`Thread` declares `static _discriminator = "model"`, and `DiscussChannel extends Thread`
(`discuss/core/common/discuss_channel_model.js`, `_name = "discuss.channel"`), so every
channel is a `DiscussChannel`:

- `store.Thread.get({ model: "discuss.channel", id })` and `store["discuss.channel"].get(id)`
  return the same object; the subtype fills the discriminator in, so a bare id works in
  `get`/`insert` and in relations targeting `"discuss.channel"`.
- Channel behaviour is `patch(DiscussChannel.prototype, …)`, never `Thread.prototype`: a
  parent patch of a method the subtype defines without `super` never runs for channels.
  `getShadowedPatches()` (`static/tests/patch_audit.js`) reports such patches; each addon
  that patches `Thread` or `DiscussChannel` runs it in its own suite, because a suite's bundle
  only holds its module's patches.
- Code that may hold any thread reaches channel members through `thread.channel` —
  `undefined` on `Thread`, the record itself on `DiscussChannel` — and model-name checks use
  `Model.inherits("Thread")`, not `Model.name === "Thread"`.

### Field factory (`misc.js` `fields`)

| Call | Field kind | Notable options |
|------|-----------|-----------------|
| `fields.Attr(default, {compute, onUpdate, sort, type})` | scalar | `type: "date"｜"datetime"` auto-(de)serializes to `Temporal.ZonedDateTime` |
| `fields.One(TargetModel, {compute, inverse, onAdd, onDelete, onUpdate})` | x2one | stored internally as a single-entry `RecordList` |
| `fields.Many(TargetModel, {compute, inverse, onAdd, onDelete, onUpdate, sort})` | x2many | auto-sorted when `sort` is set |
| `fields.Html(default, {...})` | scalar | markup-aware (`markup()` ↔ `["markup", str]` tuple) |
| `fields.Date({...})` / `fields.Datetime({...})` | scalar | `Temporal.ZonedDateTime` values |
| `AND(...)` / `OR(...)` | id expression | used in `static id` |

`ModelInternal.prepareField` reads these into the per-model metadata Maps. **Relational
writes accept command tuples**: `["ADD", …]`, `["DELETE", …]`, `["ADD.noinv", …]`,
`["DELETE.noinv", …]` (the `.noinv` variants skip inverse maintenance; validated by
`isCommand`).

## Insert / upsert — the idempotent entry point

`Record.insert(data)` (and `Store.insert(dataByModel)`) is an **upsert**: existing record
updated, missing record created, always keyed by `static id`. This is the single write path
for both initial payloads and live bus pushes — calling it twice with the same data is a
no-op beyond the first.

```
Record.insert(data, options)
  → MAKE_UPDATE(...)                         // wrap in the update cycle
    → _insert → preinsert (get() ?? new())   // create just enough for the localId
             → update(data)                  // batched field writes
```

- `Record.get(data)` — lookup by id-data → `this.records[localId]` (or `undefined`).
- `Record.localId(data)` / `_localId` — computes the `"<Model>,<id>"` localId string.
- `record.update(data)` — batched field write via `store._.updateFields`.
- `record.delete()` — enqueues a soft delete → hard delete.
- `record.eq/notEq/in/notIn` — identity comparison on `_raw`.
- `record.toData()` — serialize the record graph back to store-insertable data.

## The reactivity triad

Every record and every `RecordList` exists as three linked objects (`store.js` header,
`make_store.js`):

| Layer | What | Reactive? |
|-------|------|-----------|
| `_raw` | plain instance, raw values | No — internal work |
| `_proxyInternal` | `Proxy` implementing field get/set semantics + commands | writes notify, reads don't subscribe |
| `_proxy` | `reactive(_proxyInternal)` (OWL `reactive`) | Yes — handed to components/business code |

Getters **downgrade** a `_proxy` receiver back to `_proxyInternal`
(`RecordInternal.downgradeProxy` / `RecordListInternal.downgradeProxy`) so internal reads
stay subscription-free while component reads (through `_proxy`) subscribe normally.

### The `MAKE_UPDATE` cycle

All mutations funnel through `Store.MAKE_UPDATE(fn)`, which increments `_.UPDATE` and — only
at the **outermost** call — flushes 8 queues in a fixed order, repeated to a fixpoint
(iteration cap 1000):

```
FC  computes    →  FS  sorts       →  FA  onAdd      →  FD  onDelete
→  FU  onUpdate  →  RO  onChange    →  RD  record deletes  →  RHD  hard deletes
```

Errors are collected in `_.ERRORS` and **always** rethrown at flush end — the first one, with
the rest discarded. `store.logErrors` (default `true`) decides only whether they are *also*
printed; it never decides whether they throw. Set it to `false` in a test that asserts a throw
so the assertion does not also assert the console noise. (It was named `warnErrors` until
2026-08-17, when the name was the last thing still claiming it could swallow an error: it could
not, because `handleError` only reaches its non-collecting branch outside an update, and every
mutation path runs inside one.)

Consequently **`store.insert()` is best-effort, not atomic**: a payload can be partly applied
*and* throw. One model's rows failing no longer aborts the models after it — that error is
collected like any other and surfaces at flush end. The same holds one level down: an array `Record.insert` isolates
each row, so a failing row is recorded and skipped while the rows after it still land, and each
flush queue drains item by item (`_drainIsolated`), so one failing compute, sort or `onChange`
no longer strands the queued work behind it.

**Computes and sorts are always eager** — queued at record creation and on any
dependency change, observed or not; there is no per-field `eager` opt-in and no `markEager`
symbol. `store.env` holds the `OdooEnv`.

### `RecordUses` and `RecordList`

- **`RecordUses`** (`record._.uses`) — reverse-relation bookkeeping: `Map<Record, Map<field,
  count>>` keyed **by reference** (not localId, to survive delete+reinsert aliasing).
  `add`/`delete` adjust the count for a list's `owner` + `name`; the `RD` flush uses it to
  detach a deleted record from everyone pointing at it.
- **`RecordList`** (`extends Array`) — backing store is `data: string[]` (localIds). Every
  read method of `Array.prototype` (`map/filter/find/some/forEach/reduce/slice/at/includes/
  keys/values/entries/join/lastIndexOf/…`) is reimplemented over `data` +
  `store.recordByLocalId`; the array-returning ones (`toSorted/toReversed/toSpliced/with/flat/
  flatMap`) materialize once through `slice()`, and an `Array.prototype` method with no
  reimplementation throws rather than silently copying the list. Mutators
  (`push/pop/splice/sort/add/delete/clear/…`) run inside `MAKE_UPDATE`, maintain inverses +
  `uses`, and queue `onAdd`/`onDelete`; `RecordListInternal.insert` is the one place that
  writes the inverse side (as an `ADD.noinv`/`DELETE.noinv` command on the target), so each
  membership change reaches the inverse exactly once. `reverse`/`fill`/`copyWithin` throw
  (in-place reorder unsupported).

## The `store` service and server-data flow

`core/common/store_service.js` defines `class Store extends BaseStore` (the `model/store.js`
`Store`), calls `Store.register()`, and registers the service:

```javascript
export const storeService = {
    dependencies: ["bus_service", "im_status", "ui", "popover"],
    start(env, services) { /* makeStore(env) → seed → subscribe → onStarted */ },
};
registry.category("services").add("mail.store", storeService);
```

`start()` runs `makeStore(env)`, seeds with `store.insert(session.storeData)`, sets
`self_guest`/`settings` defaults, subscribes to `BUS:RECONNECT`, and calls `store.onStarted()`.
The `init_messaging` fetch (`initialize()`) is **not** eager — it is fired by the WebClient
patch (backend) or the public-page boot. Components read the store with
`this.store = useService("mail.store")` — the returned `_proxy` is already reactive, so no
extra `useState` wrapping is needed.

### Fetching server data

| Method (`store_service.js`) | Role |
|------|------|
| `fetchStoreData(name, params, {readonly, …})` | Queue a fetch param + a `DataResponse` request record (debounced) |
| `_fetchStoreDataDebounced()` | Batch queued params → `_fetchStoreDataRpc` → `this.insert(data)` → resolve each `DataResponse` |
| `_fetchStoreDataRpc(fetchParams)` | `rpc(readonly ? "/mail/data" : "/mail/action", { fetch_params, context })` |
| `initialize()` | `await fetchStoreData("init_messaging")` |
| `Store.insert(dataByModelName)` (`model/store.js`) | Iterate model → rows, map py→js model name, handle per-row `_DELETE`, then `store[modelName].insert(rows)` |

Python → JS model-name mapping lives in the module-private `pyToJsModels`
(`{"discuss.channel": "Thread", "mixin.mail.thread": "Thread"}`) and `addFieldsByPyModel`
(`{"discuss.channel": {model: "discuss.channel"}}`), consumed by three overridable
`Store` methods that `Store.insert` calls (declared neutral in `model/store.js`,
overridden in `core/common/store_service.js`):

| Method | Role |
|--------|------|
| `_makeInsertContext()` | per-`insert()` context, computed once |
| `_insertModelName(ctx, pyOrJsModelName)` | payload key → JS model that ingests it |
| `_insertExtraFields(pyOrJsModelName)` | field values merged into every row of that key |

These used to live on a module-level `storeInsertFns` object patched from
`store_service.js`; because one singleton served every `Store` class on the page, each
function had to re-check `store instanceof Store` and delegate to `super`. As methods,
the override applies to exactly the class that declares it and the guards are gone.
There is **no** function literally named `insertModelData`; ingestion is
`Store.insert` → per-model `Record.insert`. Initial payloads: `session.storeData` (backend
HTML) and `odoo.discuss_data` (public-page boot).

### The messaging menu

Three record types, all in `core/public_web/messaging_menu/`:

| Record | Instance(s) | Holds |
|--------|-------------|-------|
| `MessagingMenu` | `store.messagingMenu` (singleton) | `allTabs` / `visibleTabs`, `initializeCountersFetcher` |
| `MessagingMenuTab` | one per tab, `static id = "id"`: `notification`, `bookmark` (`core/web/`), `chat`, `channel` (`discuss/core/public_web/`), plus addon tabs | `recordType` (`mail.message` or `discuss.channel`), `filters`, `actions`, `emptyState`, `messages` / `channels`, `counter`, load status per filter key |
| `MessagingMenuUIState` | one per mounting: `store.messagingMenuSystrayState` (`"mail.systray"`), `store.discuss.sidebarState` (`"discuss.sidebar"`: the Discuss sidebar, whose tab and filter a `discuss.tab_<id>` active id restores — the legacy `mail.box_inbox` / `mail.box_history` / `mail.box_starred` map to Notifications on Unread, Notifications on All, and Bookmarks) | `activeTab`, `selectedFilter`, `pluginFilters`, `searchTerm` |

A tab is a computed `fields.One("MessagingMenuTab")` that a patch adds to `MessagingMenu`
(`notificationTab`, `bookmarkTab`, `chatTab`, `channelTab`); returning nothing hides it for
that user. Membership is computed from the record side: `Message.messagingMenuTabsAsMessages`
and `DiscussChannel.messagingMenuTabs` test each tab's `includesMessage` / `includesChannel`,
and `DiscussChannel.messagingMenuTabsWithCounter` feeds the channel tabs' counters.

Server traffic is `/mail/data` fetch names, not routes (`ROUTE_MAP.md`):

- `Store.initialize` fetches `/mail/messaging_menu/initialize_counters` in the same batch as
  `init_messaging` (a tab created later fetches its own), which seeds each tab's
  `init_counter_ids` — except the tabs with a `storeCounter` — and answers `has_records` for
  the `hideWhenEmpty` tabs; a tab's `counter` is its loaded countable records plus the seeded
  ids whose channel is not fetched, while Notifications and Bookmarks present a store counter
  instead (below). A seeded channel that shows up unfetched (a bus payload touched it: read
  elsewhere, muted, unpinned, left, deleted) is fetched, then counted from its own state and
  dropped from `init_counter_ids`;
- `MessagingMenuTab.loadMore()` fetches `/mail/messaging_menu/<recordType>/load_more` with
  the tab, its filters, the ids already loaded and a search term, a page of
  `MessagingMenuTab.LOAD_MORE_LIMIT`; `MessagingMenuUIState` triggers the first page when
  the active tab or filter changes while displayed;
- the empty Channels tab fetches `/mail/messaging_menu/get_most_popular_channels`.

The Notifications and Bookmarks counters are store fields, not tab state:
`needaction_counter` and `starred_counter`, each fenced by a `<field>_bus_id`
(`core/web/store_service_patch.js`). `_init_messaging` sends both as store globals with the bus
id they were computed at, and `Store.update` hands each pair to `applyCounterAbsolute`
(`utils/common/counters.js`), which replays the deltas of later bus notifications on top. Bus
deltas — `mail.message/needaction`, `mail.message/mark_as_read` (`needaction_delta`),
`mail.message/toggle_star`, `mail.message/delete` — go through `applyCounterDelta` with their
notification id; the optimistic edits (`Message.setDone`, `Thread.markAllMessagesAsRead`,
`Message.toggleStar`, `Store.unstarAll`) snapshot the counter and restore it when the call
fails. The tab counters (`MessagingMenuTab.storeCounter`) and the inbox home tile read them;
the global badge (`computeGlobalCounter`, also the home-menu badge and the app badge) is the
sum of the app-wide important tabs' counters. What the two
tabs list comes from message flags — `needaction` / `needaction_done` and `starred` — through
each tab's `includesMessage`; a star on a message this browser never loaded marks the
Bookmarks tab stale (`MessagingMenuTab.markStale`) so its next display loads it.

### Bus notifications → store

Services subscribe with `this.busService.subscribe(type, cb)` in `setup()`. The generic
server-push channel is **`mail.record/insert`** → `this.store.insert(payload)`.

| Service | File | Subscribed notification types |
|---------|------|-------------------------------|
| `mail.core.common` | `core/common/mail_core_common_service.js` | `mail.record/insert`, `mail.message/delete`, `mail.message/toggle_star`, `ir.attachment/delete`, `res.users.settings` |
| `discuss.core.common` | `discuss/core/common/discuss_core_common_service.js` | `discuss.channel/new_message`, `discuss.channel/delete`, `discuss.channel/transient_message`, `discuss.channel.member/fetched`, … |

Python emits these via `record._bus_send("<model>/<verb>", payload)` (see CONVENTIONS.md on
the bus convention).

## Model registries — two, don't confuse them

| Registry (export name) | Category string | Holds | Populated by |
|------------------------|-----------------|-------|--------------|
| `modelRegistry` | `discuss.model` | Model **classes** (`Record` subclasses) | `Record.register()` at each model file's end |
| `discussComponentRegistry` | `discuss.component` | Overridable **OWL components** (message actions, action lists, avatar cards, call dropdowns) | explicit `.add()` in the component files |

`makeStore` reads `modelRegistry`, builds a reactive Model object + proxy Class per entry,
and wires inverse relations before returning the bootstrapped `Store` proxy.
