# UI Stability — What a Navigation Paints, and What a Write Restyles

Status: **Investigated and fixed.** Date: 2026-10-02. Scope: what the backend
paints between two views, what a reload does to the results on screen, and how
much of the page a single DOM write restyles.

## Why this was opened

After the design refactor the interface read as rebuilding itself on every
change of view, and the results of a search flashed. Both were reported from
use, not from a profile, so the first step was to make them measurable.

## What was measured, and how

Two instruments, both in real Chrome:

* **What is on screen, frame by frame.** A `requestAnimationFrame` sampler reads
  the action manager once per frame — which view, how many rows or cards, whether
  a skeleton stands in — and collapses equal neighbours into states. A state that
  never makes a frame is one nobody saw; one that makes a single frame is a flash.
* **What a write restyles.** `UpdateLayoutTree` trace events carry
  `elementCount`, the number of elements a style recalculation visited. Summing
  it between two `performance.mark()` calls is the cost of what happened between
  them, in elements, independent of the machine.

Both are what `tests/test_ui_stability.py` runs. The first reading was taken with
a Playwright harness, which is not a dependency of this repository; the tests
take the same readings through `HttpCase.browser_js`, whose `trace_categories`
argument records a trace while its code runs and returns the events.

## The four causes

FROZEN at `f663426ee3ad`, the commit before the fix, on a database with `crm` and
`account` installed and demo data, 43 partners in a list, headless Chrome at
1440×900. Re-derivable only by checking that commit out, so the figures are
pinned to it rather than gated (§1.4) — **do not "correct" them to current
values**.

| # | Symptom | Reading at the base commit |
|---|---|---|
| 1 | A class or style write restyles the whole subtree | toggling a class on the list's `.o_content` restyled **1283 of 1283** elements under it; on `body`, **1390** |
| 2 | A list is styled four times when it mounts | whole-view restyles of **1337, 1287, 1282, 1281** elements, back to back |
| 3 | A view change paints states nobody asked for | list to kanban: an **empty kanban** for ~180 ms; a menu click: a skeleton for **1 to 3 frames**, up to **4** pixel-distinct states |
| 4 | A search flashes | at a 300 ms round trip the results were replaced by a skeleton for **3 to 4 frames**, then by the new results |

### 1. One selector turned every write into a full restyle

The engine decides what to restyle after a mutation from *invalidation sets*:
for each feature a selector names above its subject, the set of descendants to
re-match when that feature changes. Two properties of how those sets are built
combine badly:

* An attribute selector is keyed by the attribute's **name alone**. A rule that
  says `li[style*="color"] …` asks to be re-evaluated whenever *any* element's
  `style` attribute changes; `[class*="…"]` does the same for every class change.
* The set holds one feature of the subject. A class or an id wins; without one,
  a bare attribute selector on the subject replaces the tag. A subject written
  `font[class*="bg-"]` is therefore remembered as "anything with a `class`
  attribute".

`html_editor`'s list rule had both: an attribute selector on `style` and on
`class` above the subject, and a bare `[class*="bg-"]` on it. Every class or
style write, anywhere in the page, restyled every descendant of the element
written to. The rule is the same in upstream 19.0; what the refactor added was
the writes — a measured height published as an inline custom property on every
mount, an accent class on the body, the column-width pass on every list.

Wrapping the subject's attribute test in `:is()` keeps the tag as the feature
without changing what the rule matches or its specificity. A second rule, in
`views/kanban/kanban_controller.scss`, named a Bootstrap column by
`div[class*="col-"]` above a `div` subject and restyled every `div`; it now
names a column by where it sits (`.row > div`), which a survey of every kanban
menu template in the workspace showed to be the same set, with one field in
`product` reached by `> .o_field_widget`.

### 2. A value written after the mount is a second styling of the view

`search/layout.js` measured the control panel after the mount and wrote its
height to `--o-cp-height` on the content region. A custom property is inherited,
so the write restyled everything the view had just been styled with. The height
is now remembered per view type and rendered with the view; the write happens
only when the measurement disagrees.

### 3. Placeholders were shown before they were needed

Three mechanisms each painted a state between the view left and the view
reached:

* A menu click mounted `SkeletonView` as the action before starting the real
  one, so every such navigation showed a skeleton however fast it was.
* A lazy model let its view paint the control panel with no records, and filled
  them in when they arrived — the latency bet `OBSERVABILITY.md` describes, lost
  on every load fast enough to arrive a few frames later.
* The reload skeleton replaced the results after the loading threshold, with no
  minimum time on screen, so a load slightly slower than the threshold showed it
  for a few frames.

## The rule that replaced them

One deadline per navigation, carried on the view config as `feedbackAt`. When a
controller is on screen it is `SHOW_AFTER_DELAY` (250 ms) after the dispatch;
when nothing is — the first action of a session — it is the dispatch itself,
because there is no frame to hold and the first paint should come as early as
it can. A view mounted outside the action service has no deadline and paints as
it did before: control panel first, records when they arrive.

1. **Before the deadline the frame on screen is held.** A lazy model that has its
   data by then paints once, with it (`loadOrDeadline` in `model/model.js`). The
   outgoing controller stays mounted until the incoming one is.
2. **Past the deadline, what exists is kept and what does not is drawn.** A reload
   never replaces its results: the region is marked `o_view_stale` and fades. A
   view that painted before its first data shows its skeleton in the content
   region. A controller still not on screen is covered by its skeleton
   (`webclient/actions/action_placeholder.js`), and made `inert` under it: what
   is out of sight takes no hotkey, focus or click.
3. **A placeholder eases in on the slow-starting curve** (`o-placeholder-onset`),
   so one replaced a few frames after it appears has barely been drawn.

A view that paints its own chrome first tells the action service so
(`claimLoadingFeedback`), and the action placeholder stands down for it — once,
for one more `SHOW_AFTER_DELAY`: the claim is made before the view's libraries
and children are known to be ready, and a view that has still not painted by
then is covered after all.

A load that *fails* before anything was painted fails the mount, as a non-lazy
one does, and the user stays on the view they were on. One that fails after the
view was painted goes back, as before.

## What it costs

The rule trades an early answer for a stable one, and the trade is not free.
FROZEN at `f663426ee3ad` — the base column is that commit, the other is that
commit with this change applied — same database and browser as above, each
state painted by a navigation that clears the breadcrumbs, to a list whose
action is already loaded (a menu item whose action is not adds that load to
every figure, in both columns), and when:

| Round trip | Base commit | With the rule |
|---|---|---|
| local | skeleton at 28 ms, empty list at 94 ms, rows at 110 ms | rows at 134 ms |
| 150 ms | skeleton at 41 ms, empty list at 215 ms, rows at 365 ms | list with its skeleton easing in at 288 ms, rows at 348 ms |
| 400 ms | skeleton at 24 ms, empty list at 441 ms, rows at 860 ms | placeholder easing in at 277 ms, list at 448 ms, rows at 843 ms |

* **The records arrive when they did.** Nothing here makes a load slower or faster.
* **The first change of what is on screen comes later** whenever the load takes
  more than a few frames: up to the 250 ms of the hold, plus the placeholder's
  onset, where the base commit answered within two frames. The loading indicator
  in the navbar appears at the same threshold. The click itself is answered at
  once, by the cue below.
* **A load that lands just past the deadline still paints an intermediate
  state** — the incoming view without its records, for as long as the load
  outlasts the deadline (60 ms in the 150 ms row). The base commit painted one
  on every navigation; the rule confines it to loads slower than the deadline.

The threshold is the constant the loading indicator already used. It sits above
what a local or LAN load takes here (a first kanban load measured 170 to 190 ms),
which is the band where the base commit's intermediate states read as flashes.

### The answer that does not wait

What the hold takes away is the sign that a click registered, so that sign is
given by something that is not content. From the moment a navigation starts
(`ACTION_MANAGER:STARTED`, or the dispatch of a view switch or a breadcrumb)
until it is over, the action manager carries `aria-busy` and the pointer shows
progress (`showProgressCursor` in `webclient/actions/action_container.js`).

The cursor is put on the element under the pointer, not on the region, and
follows the pointer while the navigation is in flight: a menu item is gone a
frame after it is clicked, and what the pointer then rests on takes it. Measured
on the 43-row list: `aria-busy` on the action manager restyles nothing; a cursor
on the action manager is inherited and restyles 553 elements, and still does not
show, because the cell or the button under the pointer sets its own; a cursor on
that one element restyles 7 to 9. Starting the cue at the dispatch instead of at
the start of the action was tried first and measured: on a 300 ms round trip a
menu click was answered 290 ms late, since the action is loaded before it is
dispatched.

A touch screen has no pointer, so there the cue is `aria-busy` alone.

## After

| # | Reading | Held by |
|---|---|---|
| 1 | a class or style write on a 600-element container restyles the container | `test_a_class_or_style_write_restyles_what_it_names` (budget: 8) |
| 2 | a list and a kanban style each of their elements once when they mount | `test_a_list_is_styled_once_when_it_mounts`, `test_a_kanban_is_styled_once_when_it_mounts` (budget: 1.8 × the list's elements, 1.4 × the kanban's) |
| 3 | before the deadline a view change paints nothing between the view left and the view reached | `test_a_view_change_paints_no_intermediate_state` |
| 4 | a search slower than the threshold keeps its rows, marked stale no earlier than the threshold | `test_a_slow_search_keeps_its_results_on_screen` |

Each of the four fails on the base commit, with the defect it names: 601 of 600
elements restyled, three whole-view restyles, an empty view 19 ms after the
click, a skeleton over the results at 277 ms.

Readings 2 and 3 were reworded on 2026-10-02, when a page of records came to be
built a screenful at a time (`VIEW_MOUNT_COST.md`). Reading 2 was a count of
whole-view restyles; it is the elements styled over the mount, against the
elements the view ends up with, and it covers the kanban, where one inserted
card restyled every other. Reading 3 counts the records the screen shows, not
the ones in the DOM: the records built after the first frame must land under
the fold, and a state that differs by them is not one the user saw.

The render side is held in HOOT: `views/control_panel_render_budget.test.js`
(two passes with no deadline, one when a held frame's load beats it),
`views/view_busy.test.js` and `webclient/actions/action_placeholder.test.js`
(the first action is not held; a claim is trusted once; a covered view is inert
and is given back if the navigation fails).

## Taking a reading

```bash
odoo-bin -d <db> --test-enable --test-tags /web:TestUiStability \
    --http-port <free port> --stop-after-init
```

Each test logs its reading on a line starting `UI_STABILITY`.

## Two things that cost time to find

**A component cannot render while an ancestor's render is in flight.** OWL
queues it (`delayedRenders`) until the ancestor completes, and a `Portal`'s
content yields the same way. The action placeholder was first a child of the
action container, whose pending render is the very thing it stands in for: its
state changed and nothing was drawn. It is a child of the web client, portaled
into the action manager.

**Under HOOT the deadline counts from the dispatch, not from the call.**
`doAction` reaches its dispatch after the action's own load, by which time a
test that advanced the clock straight away has already jumped it. Wait for the
dispatch — or for the request the controller's setup sends — then advance.

**"Nothing between two views" is only true below the deadline.** The first
version of this work held every lazy view, the first action of a session
included, and asserted exactly two states per navigation. Measured against the
base commit, a page load then painted its control panel up to 250 ms later than
before, and the assertion was one a slow machine would fail. The rule is about
time, so the tests are: they read when each state began.

## Not pursued

* `html_editor`'s formatting rules reach links and buttons through a `font` or
  `span` ancestor's `style` or `class`. Their subject is a tag or a class, so a
  write restyles the links and buttons under it and nothing else — 49 elements
  in the list above. The attribute cannot be dropped: it is how the editor's
  markup carries the format.
* The list's column-width pass toggles a class on the table twice, and each
  toggle restyles the `div`s in it — two partial restyles of about a third of
  the view.
* `ActionContainer` hosts other than the web client (project sharing, the POS
  action screen) mount no placeholder: a slow navigation there keeps the
  outgoing view until the incoming one is ready.
