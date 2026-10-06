# View Mount Cost — Records Are Built a Screenful at a Time

Status: **Fixed for the list and kanban views, and for a form's refresh. What
an embedded line costs to build and render once is open.** Date: 2026-10-02.
Scope: what the main thread does between a navigation onto a page of records
and the frame that shows it.

## Why this was opened

`UI_STABILITY.md` made a navigation paint once. Measured under a slowed main
thread, that one paint was still late: a view change onto 80 records is a
single task, and nothing can be painted, or clicked, until it ends.

Readings FROZEN at `d3bd662ddbd2`, on a database of 340 modules, Chrome 154
headless at 1440×900, the main thread slowed with
`Emulation.setCPUThrottlingRate`; milliseconds from the input to the frame that
shows the records, median of 3:

| Navigation | 1× | 4× | 6× |
|---|---|---|---|
| list (80) → kanban (80) | 140 | 574 | 892 |
| kanban (80) → list (80) | 144 | 530 | 799 |
| form → list (80), breadcrumb | 228 | 568 | 859 |
| a grouped kanban of 160 cards, 5 columns | 422 | 1374 | 2108 |

Above 500 ms an interaction is rated poor (INP). A trace of the same task at
1× puts 60–70 % of it in script, and a sampling profile splits the script, for
an 80-row list (profile FROZEN at `d3bd662ddbd2`, taken on that change before
it was rebased):

| What | ms | Per record |
|---|---|---|
| Row templates, `ListRenderer.Rows` → `ListRecordRow` → `Field` | 30–32 | 0.39 |
| Record datapoints, `DynamicRecordList.setData` → `RelationalRecord.setup` | 23–24 | 0.30 |
| Mount and patch of the rows | 19 | 0.24 |
| `focus()`, the first forced style and layout of the new view | 16–17 | — |

Every one of the 80 was rendered, mounted, styled and laid out before the
first could be seen, and about 20 fit the screen.

## The rule

**The commit that puts a page of records on screen builds the records the
screen can show. Each commit after it builds as many again, until the page is
whole.** The DOM ends up holding every record, as before: find-in-page,
printing, selection and the pager's count see the whole page.

`useScreenfulFirst` (`core/utils/screenful_first.js`) holds it, and a renderer
asks it for the leading records of each collection it loops over:

* **A later batch is rendered between two frames.** A commit runs in an
  animation frame; the timer set from it fires once that frame is painted, so
  the next records are built after the paint that shows the first ones, and
  committed in the following frame.
* **What is built is never dropped to be built again.** A new set of records
  keeps every record it shares with the built ones (a reload that reuses its
  datapoints) and starts at one screenful otherwise (a new page).
* **A collection built whole stays whole.** A record added or removed in place
  is an edit of what is on screen, and is rendered in one commit.
* **The edited row is always built**: a list with a record in edition is
  rendered whole.
* **The screenful covers what is scrolled to.** The count is what fills the
  window below the current scroll offset, and on a mount the offset the
  controller is about to restore (`restoredScrollTop`): coming back to a list
  scrolled to its 60th row builds through that row in the first commit.

## How many records a screen shows

Counted at the smallest size a record can have, so that the first batch always
overflows the screen: a record built later lands under the fold and moves
nothing that is visible.

| View | Count | Constant |
|---|---|---|
| List | window height / `SMALLEST_ROW_HEIGHT` (36 px) | `list_renderer.js` |
| Kanban, cards never measured | window height / `SMALLEST_CARD_PITCH` (48 px), × window width / `NARROWEST_CARD_WIDTH` (200 px) when ungrouped | `kanban_renderer.js` |
| Kanban, cards measured | window height / the smallest distance between two rows of cards, × the cards in a row | `measureCards` |

The kanban measures the cards of a model once they are mounted and keeps the
reading for the web client's lifetime, keyed by model and by grouped or not.
The first kanban of a model in a session is therefore counted at 48 px a row,
which is close to the whole page; the ones after it at their real size.

## Where it does not apply

| Case | Why |
|---|---|
| A list or kanban embedded in a form | It does not know what is on screen around it, and what follows it would move as it grows. The renderer builds a screenful first only when its controller hands it `restoredScrollTop`. |
| A list above `VIRTUALIZATION_THRESHOLD` (100 rows) | It is windowed already. |

A list with a column sized from the text of its rows (`listViewWidth:
"content"`, a many2one to `res.company`) was a third case until `MagicColumnWidths`
stopped computing its widths again for every batch: labels that only join the
ones a column was sized for leave it as it is when they all fit. A label that
does not fit, in a row built after the first frame, widens the column once.

## An inserted record restyled every record already there

Building in batches exposed a second cost, which the kanban paid on every
quick-create and every card dropped into a column as well: one card inserted
restyled all the cards of the view.

Readings FROZEN at `d3bd662ddbd2`, 80 cards of 42 elements each in a view of
2410:

| | Elements restyled by inserting one card |
|---|---|
| Before | 2731 |
| After | 130 |

Two Bootstrap rules did it, each one alone:

| Rule | Rewritten as |
|---|---|
| `legend + *` (`_reboot.scss`) | `fieldset > :where(:nth-child(2))` |
| `.table-striped > tbody > tr:nth-of-type(…) > *` (`_tables.scss`) | `… > :where(td, th)` |

A sibling combinator, or a positional pseudo-class, in front of a bare `*`
leaves the engine nothing to find the affected elements by. Blink then marks
the whole subtree of the parent an element is inserted into. The rule never
has to match: a kanban holds neither a `legend` nor a striped table.
`:where()` keeps the specificity upstream has. Both sites carry an `AgroMarin:`
marker.

The list was not affected: an inserted row of 32 elements restyles 31.

## A record read its own fields through a proxy, a few hundred times

With a screenful of rows to render, building the page's record datapoints
became the largest part of the first task, and it is paid for all 80 records
whatever the screen shows. A sampling profile of sixteen page changes put 55 %
of it in the two traps of OWL's proxy, not in the model:

* **Every unobserved read created an atom.** A datapoint is a proxy
  (`SignalStore`), so `this.fields` inside its own setup is a proxy read. OWL
  looked up, and on a first read created, the atom that key's observers
  subscribe to (a `Map` per target, an object and a `Set` per key) before
  asking whether anything was observing. Outside a render nothing is. Fixed in
  OWL since 1d588236 (vendored `cb976f64`, `isObserving()`): a read nobody
  observes creates nothing.
* **The per-field loops went back to the getters for every field.**
  `record.fields[name]` is three proxy reads (`fields`, `config`, `_config`),
  and `parseServerValues`, `setEvalContext`, `_rememberX2ManyPayloads` and
  `fieldNames` did it once or twice per field. They read `fields` and
  `activeFields` once, before the loop.

Readings FROZEN at `01150933d234`, 80 `res.partner` records of 35 fields,
milliseconds per page:

| | Building the page's record datapoints |
|---|---|
| Before | 25.7 |
| With the OWL fix alone | 21.1 |
| With the loops as well | 17.0 |

What is left is spread thin. The largest single site is `setEvalContext`
assigning a record's evaluation context key by key onto a proxied object
(1.9 ms a page).

## A form's refresh built every line a second time

A form opens on the read the client has cached and asks the server again; the
answer is applied when it differs (`_applyBackgroundRefresh`). It went through
`setData(…, { keepChanges: true })`, which rebuilt the record's data and every
embedded list from nothing: 40 lines, 40 record datapoints and 40 rows
rendered, a second time, in a task that starts right after the first paint.

And the answer differs more often than it looks. A draft sale order reads
differently every second: `date_planned`, on the order and on its lines, is
computed from the time of the read. Every open of a quotation paid the rebuild.

Two rules now:

* **A refresh that has no user change to keep is a reload in place.**
  `keepChanges` protects what the user typed between the two reads; with an
  empty change set there is nothing to protect, and `setData` writes only the
  fields that read differently (`_reconcileData`).
* **An embedded list that reads the same rows keeps its records.**
  `_unchangedX2Manys` kept a list only when the server sent the very payload
  it was built from. `StaticList.reconcileRows` also keeps it when the rows
  are the same records in the same order: a row that reads as it did is left
  alone, another one takes the new values in place, and only the components
  that show a changed field render again. The list is rebuilt, as before, when
  the rows differ in number, identity or order, when a value it is sorted on
  changed, when a record was extended with the fields of its form, and when
  something local is staged.

Readings FROZEN at `ff94c8236fb9`, without and with this change, the same
database, a draft order of 8 lines and one of 40; milliseconds, median of 4,
two rounds each, interleaved. Long tasks are those the page records from the
click until it is idle:

| | Long tasks | Of them, after the rows are shown | Idle at |
|---|---|---|---|
| 40 lines, 1× | 210–211 → 144–148 | 70 → 0 | 371–375 → 169–171 |
| 40 lines, 4× | 944–976 → 608–615 | 388–408 → 28 | 1075–1113 → 691–706 |
| 8 lines, 4× | 350 → 280–284 | 69–70 → 0 | 459 → 324 |

The rows themselves are shown when they were (150 ms at 1×), or slightly
later at 4× (517–522 → 551–554 ms for 40 lines).

Held by `model/relational_model/record_reload_reconcile.test.js`: the row
written in place and the records kept, the rebuild when the rows are not the
ones held, the refresh in place and the one that keeps a typed value, the
sorted list.

### A line that read differently was parsed whole

The row `reconcileRows` gave to a record went through `setData`, which parses
every field of it, rewrites the evaluation context, and evaluates the context
of each of the line's own x2many fields again: 0.3 ms a row whatever changed,
10 ms for the 32 lines of that order whose `date_planned` moved.

A row now says which fields read differently (`refreshableFields`) and only
those are written (`refreshFields`): parsed, their entries of the evaluation
context replaced, and the context of an x2many recomputed only when its
expression names one of them. The row takes `setData`, as before, when a field
that changed is an x2many or a property, or is not shown, or when the record
holds a change of its own.

Readings FROZEN at `409ed11d0240` (begun on `1885085dcdb3`, which differs only
in the clickbot's timeout message), the order of 40 lines, without and with
this change, three rounds interleaved, the server restarted for each so the
bundle served is the one measured; median of 4:

| | Long tasks | Of them, after the rows are shown | Idle at |
|---|---|---|---|
| 40 lines, 1× | 154–180 → 141–164 | 0 → 0 | 179–216 → 182–183 |
| 40 lines, 4× | 642–877 → 582–851 | 64–72 → 0 | 802–1082 → 618–916 |

One 1× round with the change (529 ms) ran beside another session's browser
suites and is left out. A sampling profile of eight opens: 200 → 174 ms of
script per open, `setEvalContext` 14.5 → 8.7 ms, `setData` 38 → 28 ms.

Held by `record_reload_reconcile.test.js`: a line whose name moved is written
alone, its evaluation context follows, the x2many whose context names the
field is given a new one and the other is not.

## After

Readings FROZEN at `d3bd662ddbd2` with this change applied, same set-up as above:

| Navigation | 1× | 4× | 6× |
|---|---|---|---|
| list (80) → kanban (80) | 83 | 325 | 469 |
| kanban (80) → list (80) | 85 | 328 | 520 |
| form → list (80), breadcrumb | 77 | 310 | 568 |
| a grouped kanban of 160 cards, 5 columns | 208 | 491 | 789 |

The first commit builds 25 of the 80 rows, 24 of the 80 cards, 28 of the 160
grouped ones. No view change in the table is rated poor at 4× any more; none
is rated good either (under 200 ms), see *Not pursued*.

## What it costs

* **The page is whole later.** Coming back to an 80-row list at 4×, the last
  row is in the DOM at 600 ms instead of 451 ms, in four commits instead of
  one. The longest task goes from 301 ms to 208 ms, and the ones after it are
  50 to 85 ms each.
* **More work in total**: 15 to 20 % more main-thread time at 1×, the renderer
  rendering once per batch and the browser painting once per batch.
* **For a few frames the page is not whole.** Find-in-page, a keyboard move
  past the built rows and a print issued in that window see the rows built so
  far.
* **Column widths are measured on the first batch.** They were measured on the
  first page and kept for the next ones; they are now measured on the first
  screenful of the first page.

## Held by

| Reading | Held by |
|---|---|
| the first commit builds one screenful, each later one another, nothing is destroyed | `core/utils/screenful_first.test.js` |
| the list: page, pager, restored scroll, opened group, content-sized column (no width is computed again while the page is built; a label that does not fit widens it), embedded list | `views/list/list_screenful_first.test.js` |
| the kanban: never measured, per column, measured, restored scroll | `views/kanban/kanban_screenful_first.test.js` |
| what the screen shows does not change while the rest is built | `test_a_view_change_paints_no_intermediate_state`, which counts the records on screen |
| a list and a kanban style each element once when they mount (budget: 1.8 × the list's elements, 1.4 × the kanban's) | `test_a_list_is_styled_once_when_it_mounts`, `test_a_kanban_is_styled_once_when_it_mounts` |

The kanban's budget has teeth at the suite's size: on its 40 partners the mount
reads 1.19 × the view's elements, and 1.68 with the two Bootstrap rules as
upstream writes them.

## Technique

**Which rules make an insertion restyle its siblings.** Chrome's invalidation
tracking (`disabled-by-default-devtools.timeline.invalidationTracking`) names
the element whose subtree is invalidated and the reason, but attributes it to
every rule that shares the engine's "whole subtree" invalidation set, which is
not the list of culprits. What finds them is elimination on a still copy of the
page: the live page's `body` and stylesheets in a blank document, a fresh
`body` per probe (the flags a match leaves on an element outlive the rule), one
element inserted, and the `elementCount` of the `UpdateLayoutTree` events that
follow. Neutering a rule is `rule.selectorText = ".x"`; 30 000 rules bisect in
a few minutes. On the live page a probe needs a view change, and a search over
the same rules does not finish.

**An `@import`-ed partial does not rebuild the bundle.** Bootstrap's partials
are not listed in the bundle, so the old stylesheet is served across a restart
until the asset attachments are deleted. Read `document.styleSheets` for the
selector that was changed before believing a reading.

**A paint is not the next animation frame.** A probe that reads the DOM in
`requestAnimationFrame` sees the commit one frame late, and here the task that
builds the second batch sits between the two. The commit is seen in a
`MutationObserver`, and the frame that paints it has ended when a task posted
from there with `scheduler.postTask` at `user-blocking` priority runs.

## Not pursued

* **Record datapoints are still built for the whole page**, 0.21 ms each, in
  the task that ends with the first paint. Building them lazily changes what
  `list.records` is for every reader of it (selection, export, the pager), not
  a renderer.
* **Lists embedded in a form.** A sale order of 40 lines opens in 150 ms at 1×
  and 550 ms at 4×, against 85 and 290 ms for one of 8 lines: about 2 ms a
  line. A screenful counted at the smallest row is 25 rows, so only the last
  15 of a 40-line page would be built later, and forty-odd renderers embed a
  list in a form. In a sampling profile of that open, a line costs 0.5 ms as a
  record datapoint and 0.75 ms as a row, most of the row in its `Field`
  components. `setEvalContext` is 9 ms of an open since a refreshed line is
  written field by field (15 ms before): when a line is built it still computes
  the context of each of its own x2many fields whether or not anything reads
  it.
* **`.o-form-buttonbox:not(.o-form-buttonbox-small) > * + *`** is of the same
  family as the two Bootstrap rules. Alone it restyles about ten cards per
  insertion, not the view.
* **One batch per frame, of constant size.** Larger later batches would end
  sooner and block longer; the size of the first commit is the size the user
  has already waited for once.
