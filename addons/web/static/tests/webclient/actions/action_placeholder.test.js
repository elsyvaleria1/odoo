// @ts-check

import { beforeEach, describe, expect, test } from "@odoo/hoot";
import {
    advanceFrame,
    advanceTime,
    animationFrame,
    Deferred,
    freezeTime,
    microTick,
} from "@odoo/hoot-mock";
import { Component, onWillStart, useProps, xml } from "@odoo/owl";
import {
    defineActions,
    defineModels,
    fields,
    getService,
    makeServerError,
    models,
    mountWebClient,
    onRpc,
    patchWithCleanup,
    webModels,
} from "@web/../tests/web_test_helpers";
import { AppEvent } from "@web/core/events";
import { registry } from "@web/core/registry";
import { redirect } from "@web/core/utils/urls";
import { KanbanController } from "@web/views/kanban/kanban_controller";

describe.current.tags("desktop");

beforeEach(() => freezeTime());

const { ResCompany, ResPartner, ResUsers } = webModels;

class Partner extends models.Model {
    _rec_name = "display_name";
    display_name = fields.Char();
    _records = [
        { id: 1, display_name: "First record" },
        { id: 2, display_name: "Second record" },
    ];
    _views = {
        list: `<list><field name="display_name"/></list>`,
        kanban: `
            <kanban>
                <templates>
                    <t t-name="card">
                        <field name="display_name"/>
                    </t>
                </templates>
            </kanban>`,
        form: `<form><field name="display_name"/></form>`,
        search: `<search/>`,
    };
}

defineModels([Partner, ResCompany, ResPartner, ResUsers]);

defineActions([
    {
        id: 21,
        xml_id: "action_21",
        name: "Partners list",
        res_model: "partner",
        views: [[false, "list"]],
    },
    {
        id: 22,
        xml_id: "action_22",
        name: "Partners kanban",
        res_model: "partner",
        views: [[false, "kanban"]],
    },
    {
        id: 23,
        xml_id: "action_23",
        name: "Partner form",
        res_model: "partner",
        res_id: 1,
        views: [[false, "form"]],
    },
]);

/** @returns {string[]} */
function recordActionManagerStates() {
    const manager = /** @type {HTMLElement} */ (
        document.querySelector(".o_action_manager")
    );
    /** @type {string[]} */
    const states = [];
    const read = () => {
        const state = [
            ...[...manager.querySelectorAll(":scope > .o_action")].map(
                (el) =>
                    [...el.classList].find((name) => name.endsWith("_view")) ??
                    "client",
            ),
            ...(manager.querySelector(".o_skeleton_view") ? ["skeleton"] : []),
        ].join("+");
        if (states.at(-1) !== state) {
            states.push(state);
        }
    };
    read();
    new MutationObserver(read).observe(manager, { childList: true, subtree: true });
    return states;
}

/** @returns {Promise<void>} */
function nextNavigationDispatched() {
    const { bus } = getService("action").env;
    return new Promise((resolve) => {
        /** @param {any} ev */
        const onUpdate = (ev) => {
            if (ev.detail?.placeholder) {
                bus.removeEventListener(AppEvent.ACTION_MANAGER_UPDATE, onUpdate);
                resolve();
            }
        };
        bus.addEventListener(AppEvent.ACTION_MANAGER_UPDATE, onUpdate);
    });
}

/**
 * @param {string} tag
 * @param {Promise<void>} ready
 */
function registerSlowClientAction(tag, ready) {
    class SlowClientAction extends Component {
        static template = xml`<div class="o_slow_client_action"/>`;
        static props = null;
        props = useProps(this.constructor.props);

        setup() {
            onWillStart(() => ready);
        }
    }
    registry.category("actions").add(tag, SlowClientAction);
}

test("a navigation that lands before the loading threshold swaps the views with nothing in between", async () => {
    await mountWebClient();
    const action = getService("action");
    await action.doAction(21);
    const states = recordActionManagerStates();

    await action.doAction(22, { clearBreadcrumbs: true });
    await animationFrame();

    expect(".o_kanban_record:not(.o_kanban_ghost)").toHaveCount(2);
    expect(states).toEqual(["o_list_view", "o_kanban_view"]);
});

test("a slow navigation holds the outgoing view, then covers it with the incoming one's skeleton", async () => {
    const ready = new Deferred();
    registerSlowClientAction("slow_client_action", ready);
    await mountWebClient();
    const action = getService("action");
    await action.doAction(21);

    const dispatched = nextNavigationDispatched();
    const landing = action.doAction("slow_client_action", { clearBreadcrumbs: true });
    await dispatched;
    await advanceTime(200);
    expect(".o_list_view .o_data_row").toHaveCount(2);
    expect(".o_action_placeholder").toHaveCount(0);

    await advanceTime(60);
    await advanceFrame(1);
    await animationFrame();
    expect(".o_action_placeholder .o_skeleton_generic").toHaveCount(1);
    expect(".o_list_view").toHaveCount(1, {
        message: "the outgoing view is covered, not torn down",
    });
    expect(".o_list_view").toHaveAttribute("inert", "", {
        message: "what is out of sight is out of reach",
    });

    ready.resolve();
    await landing;
    await animationFrame();
    expect(".o_slow_client_action").toHaveCount(1);
    expect(".o_list_view").toHaveCount(0);
    expect(".o_action_placeholder").toHaveCount(0);
});

test("a slow form shows the form skeleton with its control panel", async () => {
    const pending = new Deferred();
    onRpc("web_read", async () => {
        await pending;
    });
    await mountWebClient();
    const action = getService("action");
    await action.doAction(21);

    const dispatched = nextNavigationDispatched();
    const landing = action.doAction(23, { clearBreadcrumbs: true });
    await dispatched;
    await advanceTime(260);
    await advanceFrame(1);
    await animationFrame();
    expect(".o_action_placeholder .o_skeleton_form").toHaveCount(1);
    expect(".o_action_placeholder .o_skeleton_cp").toHaveCount(1);

    pending.resolve();
    await landing;
    await animationFrame();
    expect(".o_form_view").toHaveCount(1);
    expect(".o_action_placeholder").toHaveCount(0);
});

test("a view that paints its own chrome first stands in for the placeholder", async () => {
    const pending = new Deferred();
    const requested = new Deferred();
    onRpc("web_search_read", async () => {
        requested.resolve();
        await pending;
    });
    await mountWebClient();
    const action = getService("action");
    await action.doAction(23);

    const landing = action.doAction(22, { clearBreadcrumbs: true });
    await requested;
    await advanceTime(260);
    await landing;
    await animationFrame();
    expect(".o_action_placeholder").toHaveCount(0);
    expect(".o_kanban_view .o_control_panel").toHaveCount(1);
    expect(".o_kanban_view .o_content").toHaveClass("o_view_loading");
    expect(".o_kanban_view .o_view_busy .o_skeleton_kanban").toHaveCount(1);

    pending.resolve();
    await animationFrame();
    await animationFrame();
    expect(".o_kanban_view .o_content").not.toHaveClass("o_view_loading");
    expect(".o_kanban_record:not(.o_kanban_ghost)").toHaveCount(2);
});

test("a superseded navigation takes its placeholder with it", async () => {
    const ready = new Deferred();
    registerSlowClientAction("slow_client_action", ready);
    await mountWebClient();
    const action = getService("action");
    await action.doAction(21);

    const dispatched = nextNavigationDispatched();
    action.doAction("slow_client_action", { clearBreadcrumbs: true });
    await dispatched;
    await advanceTime(260);
    await advanceFrame(1);
    await animationFrame();
    expect(".o_action_placeholder").toHaveCount(1);

    await action.doAction(22, { clearBreadcrumbs: true });
    await animationFrame();
    expect(".o_kanban_view").toHaveCount(1);
    expect(".o_action_placeholder").toHaveCount(0);
});

test("a slow navigation that fails gives the outgoing view back, in reach again", async () => {
    const ready = new Deferred();
    registerSlowClientAction("slow_client_action", ready);
    await mountWebClient();
    const action = getService("action");
    await action.doAction(21);

    const dispatched = nextNavigationDispatched();
    const failure = action
        .doAction("slow_client_action", { clearBreadcrumbs: true })
        .then(
            () => null,
            (error) => error,
        );
    await dispatched;
    await advanceTime(260);
    await advanceFrame(1);
    await animationFrame();
    expect(".o_action_placeholder").toHaveCount(1);
    expect(".o_list_view").toHaveAttribute("inert");

    ready.reject(new Error("the action could not start"));
    expect((await failure)?.message).toBe("the action could not start");
    await animationFrame();
    await animationFrame();
    expect(".o_action_placeholder").toHaveCount(0);
    expect(".o_list_view").toHaveCount(1);
    expect(".o_list_view").not.toHaveAttribute("inert");
});

test("the action manager says it is busy from the call to the landing", async () => {
    const ready = new Deferred();
    registerSlowClientAction("slow_client_action", ready);
    await mountWebClient();
    const action = getService("action");
    await action.doAction(21);
    expect(".o_action_manager").not.toHaveAttribute("aria-busy");

    const landing = action.doAction("slow_client_action", { clearBreadcrumbs: true });
    expect(".o_action_manager").toHaveAttribute("aria-busy", "true", {
        message: "the click is answered at once, before the action is even loaded",
    });
    await animationFrame();
    expect(".o_list_view").toHaveCount(1, {
        message: "while the frame on screen is still held",
    });
    expect(".o_action_manager").toHaveAttribute("aria-busy", "true");

    ready.resolve();
    await landing;
    await animationFrame();
    expect(".o_action_manager").not.toHaveAttribute("aria-busy");
});

test("a view switch and a failed action are answered and released the same way", async () => {
    await mountWebClient();
    const action = getService("action");
    await action.doAction({
        type: "ir.actions.act_window",
        res_model: "partner",
        views: [
            [false, "list"],
            [false, "kanban"],
        ],
    });

    const switching = action.switchView("kanban");
    await microTick();
    await animationFrame();
    await switching;
    await animationFrame();
    expect(".o_kanban_view").toHaveCount(1);
    expect(".o_action_manager").not.toHaveAttribute("aria-busy");

    const failure = action.doAction("an_action_nobody_registered").then(
        () => null,
        (error) => error,
    );
    expect(".o_action_manager").toHaveAttribute("aria-busy", "true");
    expect(await failure).not.toBe(null);
    await animationFrame();
    expect(".o_action_manager").not.toHaveAttribute("aria-busy");
});

test("noEmptyTransition asks for no placeholder at all", async () => {
    const ready = new Deferred();
    registerSlowClientAction("slow_client_action", ready);
    await mountWebClient();
    const action = getService("action");
    await action.doAction(21);

    const landing = action.doAction("slow_client_action", {
        clearBreadcrumbs: true,
        noEmptyTransition: true,
    });
    await animationFrame();
    await advanceTime(400);
    await animationFrame();
    expect(".o_action_placeholder").toHaveCount(0);
    expect(".o_list_view").toHaveCount(1);

    ready.resolve();
    await landing;
    await animationFrame();
    expect(".o_slow_client_action").toHaveCount(1);
});

test("the first action of a session is not held: there is no frame on screen to hold", async () => {
    const pending = new Deferred();
    onRpc("web_search_read", async () => {
        await pending;
    });
    redirect("/odoo/action-22");
    await mountWebClient();

    expect(".o_kanban_view .o_control_panel").toHaveCount(1, {
        message: "the control panel is painted without waiting for the threshold",
    });
    expect(".o_kanban_view .o_content").toHaveClass("o_view_loading");

    pending.resolve();
    await animationFrame();
    await animationFrame();
    expect(".o_kanban_record:not(.o_kanban_ghost)").toHaveCount(2);
});

test("a view that claims its own feedback and still does not paint is covered in the end", async () => {
    const ready = new Deferred();
    patchWithCleanup(KanbanController.prototype, {
        setup() {
            super.setup();
            onWillStart(() => ready);
        },
    });
    await mountWebClient();
    const action = getService("action");
    await action.doAction(21);

    const dispatched = nextNavigationDispatched();
    const landing = action.doAction(22, { clearBreadcrumbs: true });
    await dispatched;
    await advanceTime(260);
    await advanceFrame(1);
    await animationFrame();
    expect(".o_action_placeholder").toHaveCount(0, {
        message:
            "the view said it would paint its own chrome, and is given the time to",
    });
    expect(".o_list_view").toHaveCount(1);

    await advanceTime(260);
    await advanceFrame(1);
    await animationFrame();
    expect(".o_action_placeholder .o_skeleton_kanban").toHaveCount(1);

    ready.resolve();
    await landing;
    await animationFrame();
    await animationFrame();
    expect(".o_kanban_view").toHaveCount(1);
    expect(".o_action_placeholder").toHaveCount(0);
});

test("a first load that fails after the view was painted goes back to the view it came from", async () => {
    expect.errors(1);
    const pending = new Deferred();
    const requested = new Deferred();
    await mountWebClient();
    const action = getService("action");
    await action.doAction(23);
    onRpc("web_search_read", async () => {
        requested.resolve();
        await pending;
        throw makeServerError({ message: "Oups" });
    });

    action.doAction(22);
    await requested;
    await advanceTime(260);
    await animationFrame();
    await animationFrame();
    expect(".o_kanban_view .o_control_panel").toHaveCount(1);
    expect(".o_form_view").toHaveCount(0);

    pending.resolve();
    await expect.waitForErrors(["Oups"]);
    await animationFrame();
    await animationFrame();
    expect(".o_form_view").toHaveCount(1);
    expect(".o_kanban_view").toHaveCount(0);
});
