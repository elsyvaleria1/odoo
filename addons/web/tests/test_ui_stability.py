import logging
import re

import odoo.tests
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tools.misc import file_open

_logger = logging.getLogger(__name__)

APP_CONTEXT = (
    'odoo.loader.modules.get("@web/core/app_context")'
    ".appContextOf(odoo.__WOWL_DEBUG__.root)"
)

TRACE_CATEGORIES = (
    "devtools.timeline,disabled-by-default-devtools.timeline,blink.user_timing"
)
MARK_PREFIX = "ui_stability:"
STYLE_EVENTS = ("UpdateLayoutTree", "RecalculateStyles")

PROBE_ELEMENTS = 600
RESTYLED_PER_WRITE_BUDGET = 8

PARTNERS = 40
MOUNT_RESTYLE_BUDGET = {"list": 1.8, "kanban": 1.4}
SLOW_RPC_MS = 600

with file_open("web/static/src/ui/loading/loading_threshold.js") as threshold_source:
    SHOW_AFTER_DELAY = int(
        re.search(r"SHOW_AFTER_DELAY = (\d+);", threshold_source.read()).group(1)
    )

FRAME_PROBE = """
const framesOf = (() => {
    const read = () => {
        const manager = document.querySelector(".o_action_manager");
        const action = manager?.querySelector(":scope > .o_action");
        const content = action?.querySelector(".o_content");
        // records are built a screenful at a time: what counts is what the
        // screen shows, and the ones built later must land under the fold
        const onScreen = (selector) =>
            [...(action?.querySelectorAll(selector) ?? [])].filter(
                (record) => record.getBoundingClientRect().top < window.innerHeight
            ).length;
        return [
            [...(action?.classList ?? [])].find((name) => name.endsWith("_view")) ?? "none",
            "rows=" + onScreen(".o_data_row"),
            "cards=" + onScreen(".o_kanban_record:not(.o_kanban_ghost)"),
            ...(manager?.querySelector(".o_skeleton_view") ? ["skeleton"] : []),
            ...(content?.classList.contains("o_view_stale") ? ["stale"] : []),
        ].join(" ");
    };
    return async (interaction, settleMs = 400) => {
        const states = [];
        const start = performance.now();
        let running = true;
        const sample = () => {
            const state = read();
            if (states.at(-1)?.[1] !== state) {
                states.push([Math.round(performance.now() - start), state]);
            }
            if (running) {
                requestAnimationFrame(sample);
            }
        };
        sample();
        await interaction();
        await new Promise((resolve) => setTimeout(resolve, settleMs));
        running = false;
        return states;
    };
})();
const settled = (ms = 1500) => new Promise((resolve) => setTimeout(resolve, ms));
const mark = (name) => performance.mark("%(prefix)s" + name);
const threshold = %(threshold)d;
// every state but the first and the last, that began before feedback was due
const heldTooShort = (states) => states.slice(1, -1).filter(([ms]) => ms < threshold);
"""


def _run(body):
    return """
        (async () => {
            try {
                %s
                const appContext = %s;
                const action = appContext.services.action;
                await settled();
                %s
                console.log("test successful");
            } catch (error) {
                console.error("ui stability reading failed: " + (error?.stack ?? error));
            }
        })();
    """ % (
        FRAME_PROBE % {"prefix": MARK_PREFIX, "threshold": SHOW_AFTER_DELAY},
        APP_CONTEXT,
        body,
    )


def _marks(events):
    marks = {}
    for event in events:
        name = event.get("name", "")
        if name.startswith(MARK_PREFIX):
            marks.setdefault(name.removeprefix(MARK_PREFIX), event["ts"])
    return marks


def _restyled(events, start, end):
    marks = _marks(events)
    return [
        event.get("args", {}).get("elementCount", 0)
        for event in events
        if event.get("name") in STYLE_EVENTS
        and event.get("ph") == "X"
        and marks[start] <= event["ts"] <= marks[end]
    ]


def _figure(events, name):
    prefix = f"{name}="
    for mark in _marks(events):
        if mark.startswith(prefix):
            return json_loads(mark.removeprefix(prefix))
    raise AssertionError(f"the page reported no {name!r} figure")


@odoo.tests.tagged("-at_install", "post_install", "web_ui_stability")
class TestUiStability(odoo.tests.HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.partner"].create(
            [
                {
                    "name": f"Stability partner {index:02d}",
                    "email": f"p{index}@example.com",
                }
                for index in range(PARTNERS)
            ]
        )

    def _read(self, body, **kwargs):
        return self.browser_js(
            "/odoo", _run(body), "odoo.isReady === true", login="admin", **kwargs
        )

    def test_a_class_or_style_write_restyles_what_it_names(self):
        events = self._read(
            """
            const probe = document.createElement("div");
            probe.style.cssText = "position: absolute; visibility: hidden;";
            for (let index = 0; index < %(rows)d; index++) {
                probe.insertAdjacentHTML(
                    "beforeend",
                    `<div class="o_probe_row"><span class="o_probe_cell text-muted">` +
                        `<b class="o_probe_strong"><i class="o_probe_icon"></i></b>` +
                        `</span><label class="o_probe_label"></label><em class="o_probe_note"></em></div>`,
                );
            }
            const flush = () => getComputedStyle(probe.lastElementChild).color;
            mark("insert:start");
            document.body.append(probe);
            flush();
            mark("insert:end");
            mark("elements=" + probe.querySelectorAll("*").length);
            const writes = {
                class: () => probe.classList.toggle("o_probe_flag"),
                style: () => (probe.style.zIndex = probe.style.zIndex ? "" : "auto"),
            };
            for (const [name, write] of Object.entries(writes)) {
                mark(name + ":start");
                write();
                flush();
                mark(name + ":end");
            }
            probe.remove();
            """
            % {"rows": PROBE_ELEMENTS // 6},
            trace_categories=TRACE_CATEGORIES,
        )
        self.assertEqual(_figure(events, "elements"), PROBE_ELEMENTS)
        self.assertGreaterEqual(
            sum(_restyled(events, "insert:start", "insert:end")),
            PROBE_ELEMENTS,
            "styling the probe itself was not seen in the trace, so a write"
            " that restyles nothing proves nothing: the trace events this"
            " test reads are no longer the ones the browser emits.",
        )
        reading = {
            write: sum(_restyled(events, f"{write}:start", f"{write}:end"))
            for write in ("class", "style")
        }
        _logger.info("UI_STABILITY restyled per write %s", json_dumps(reading))
        for write, restyled in reading.items():
            self.assertLessEqual(
                restyled,
                RESTYLED_PER_WRITE_BUDGET,
                f"a {write} write on a container of {PROBE_ELEMENTS} elements"
                f" restyled {restyled}. A selector in the page carries an"
                " attribute selector on class or style above its subject, so"
                " every such write re-matches the subtree; give its subject a"
                " class, or wrap the attribute test in :is().",
            )

    def _mount_restyles(self, view, other):
        events = self._read(
            """
            await action.doAction({
                type: "ir.actions.act_window",
                res_model: "res.partner",
                views: [[false, "%(other)s"], [false, "%(view)s"]],
            });
            await settled();
            // the first view of a session measures its control panel: every
            // later one is rendered with that height in place
            await action.switchView("%(view)s");
            await settled();
            await action.switchView("%(other)s");
            await settled();
            mark("mount:start");
            await action.switchView("%(view)s");
            await settled(900);
            mark("mount:end");
            mark("content=" + document.querySelectorAll(".o_action_manager .o_action *").length);
            mark("records=" + document.querySelectorAll(
                ".o_action_manager .o_data_row, .o_action_manager .o_kanban_record:not(.o_kanban_ghost)"
            ).length);
            """
            % {"view": view, "other": other},
            trace_categories=TRACE_CATEGORIES,
        )
        content = _figure(events, "content")
        self.assertGreaterEqual(_figure(events, "records"), PARTNERS)
        restyled = sum(_restyled(events, "mount:start", "mount:end"))
        _logger.info(
            "UI_STABILITY %s mount %s",
            view,
            json_dumps({"content": content, "restyled": restyled}),
        )
        self.assertGreaterEqual(
            restyled,
            content,
            f"mounting a {view} of {content} elements was seen to style"
            f" {restyled}: the trace events this test reads are no longer the"
            " ones the browser emits.",
        )
        self.assertLessEqual(
            restyled,
            MOUNT_RESTYLE_BUDGET[view] * content,
            f"mounting a {view} of {content} elements styled {restyled}."
            " Its records are built a screenful at a time, and each element"
            " is to be styled when it is built: more than that is a write"
            " made after the mount that every element inherits or is"
            " re-matched for, or a selector that restyles the records already"
            " there whenever one is inserted.",
        )

    def test_a_list_is_styled_once_when_it_mounts(self):
        self._mount_restyles("list", "kanban")

    def test_a_kanban_is_styled_once_when_it_mounts(self):
        self._mount_restyles("kanban", "list")

    def test_a_view_change_paints_no_intermediate_state(self):
        self._read(
            """
            const openPartners = (options) => action.doAction({
                type: "ir.actions.act_window",
                res_model: "res.partner",
                views: [[false, "list"], [false, "kanban"], [false, "form"]],
            }, options);
            await openPartners();
            await settled();
            const readings = {
                "list to kanban": await framesOf(() => action.switchView("kanban")),
                "kanban to list": await framesOf(() => action.switchView("list")),
                "list to form": await framesOf(
                    () => document.querySelector(".o_data_row .o_data_cell").click()
                ),
                "form to list": await framesOf(() => action.switchView("list")),
            };
            await action.doAction({
                type: "ir.actions.act_window",
                res_model: "res.users",
                views: [[false, "list"]],
            }, { clearBreadcrumbs: true });
            await settled();
            readings["another action"] = await framesOf(
                () => openPartners({ clearBreadcrumbs: true })
            );
            console.log("UI_STABILITY view changes " + JSON.stringify(readings));
            const flashes = Object.entries(readings).filter(
                ([, states]) => heldTooShort(states).length
            );
            if (flashes.length) {
                throw new Error(
                    "before the loading threshold (" + threshold + " ms) a view change " +
                    "painted something between the view it left and the one it reached: " +
                    JSON.stringify(Object.fromEntries(flashes))
                );
            }
            const unfinished = Object.entries(readings).filter(([, states]) => {
                const reached = states.at(-1)[1];
                return reached.includes("skeleton") ||
                    !(/rows=[1-9]|cards=[1-9]|form_view/.test(reached));
            });
            if (unfinished.length) {
                throw new Error(
                    "a view change did not end on a view with its records: " +
                    JSON.stringify(Object.fromEntries(unfinished))
                );
            }
            """
        )

    def test_a_slow_search_keeps_its_results_on_screen(self):
        self._read(
            """
            await action.doAction({
                type: "ir.actions.act_window",
                res_model: "res.partner",
                views: [[false, "list"]],
            });
            await settled();
            const { browser } = odoo.loader.modules.get("@web/core/browser/browser");
            const fetch = browser.fetch;
            browser.fetch = async (url, ...args) => {
                if (String(url).includes("web_search_read")) {
                    await new Promise((resolve) => setTimeout(resolve, %(slow)d));
                }
                return fetch(url, ...args);
            };
            const rowsBefore = document.querySelectorAll(".o_data_row").length;
            document.querySelector(".o_searchview_dropdown_toggler").click();
            await settled(300);
            const states = await framesOf(
                () => document.querySelector(".o_filter_menu .o-dropdown-item").click(),
                %(slow)d + 800
            );
            browser.fetch = fetch;
            console.log("UI_STABILITY slow search " + JSON.stringify(states));
            const rowsAfter = document.querySelectorAll(".o_data_row").length;
            if (rowsAfter === rowsBefore || rowsAfter === 0) {
                throw new Error("the search did not narrow the list: " + rowsBefore + " -> " + rowsAfter);
            }
            if (states.some(([, state]) => state.includes("skeleton") || state.includes("rows=0"))) {
                throw new Error("the results left the screen while their replacement loaded: " + JSON.stringify(states));
            }
            const stale = states.find(([, state]) => state.includes("stale"));
            if (!stale) {
                throw new Error("a search slower than the loading threshold gave no sign of it: " + JSON.stringify(states));
            }
            if (stale[0] < threshold) {
                throw new Error("the results were marked stale before the loading threshold: " + JSON.stringify(states));
            }
            if (states.at(-1)[1].includes("stale")) {
                throw new Error("the new results are still marked stale: " + JSON.stringify(states));
            }
            """
            % {"slow": SLOW_RPC_MS}
        )
