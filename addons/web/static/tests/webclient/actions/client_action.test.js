// @ts-check

import { beforeEach, expect, test } from "@odoo/hoot";
import { queryFirst } from "@odoo/hoot-dom";
import { animationFrame, Deferred, runAllTimers } from "@odoo/hoot-mock";
import { Component, onMounted, useProps, xml } from "@odoo/owl";
import {
    contains,
    defineActions,
    defineModels,
    getService,
    models,
    mountWebClient,
    onRpc,
    patchWithCleanup,
    stepAllNetworkCalls,
    toggleActionMenu,
    toggleMenuItem,
    webModels,
} from "@web/../tests/web_test_helpers";
import { appContextOf } from "@web/core/app_context";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { SupersededError } from "@web/core/utils/concurrency";
import { useServiceProtectMethodHandling } from "@web/core/utils/hooks";
import { redirect } from "@web/core/utils/urls";
import { viewConfigOf } from "@web/core/view_config_hooks";

const { ResCompany, ResPartner, ResUsers } = webModels;
const actionRegistry = registry.category("actions");

class TestClientAction extends Component {
    static template = xml`
        <div class="test_client_action">
            ClientAction_<t t-out="this.props.action.params?.description"/>
        </div>`;
    static props = null;
    props = useProps(this.constructor.props);
    setup() {
        onMounted(() =>
            viewConfigOf(this).setDisplayName(`Client action ${this.props.action.id}`),
        );
    }
}

class Partner extends models.Model {
    _rec_name = "display_name";

    _records = [
        { id: 1, display_name: "First record" },
        { id: 2, display_name: "Second record" },
    ];
    _views = {
        form: `
            <form>
                <group>
                    <field name="display_name"/>
                </group>
            </form>
        `,
        "kanban,1": `
            <kanban>
                <templates>
                    <t t-name="card">
                        <field name="display_name"/>
                    </t>
                </templates>
            </kanban>
        `,
        list: `
            <list>
                <field name="display_name" />
            </list>
        `,
    };
}

defineModels([Partner, ResCompany, ResPartner, ResUsers]);

defineActions([
    {
        id: 1,
        xml_id: "action_1",
        name: "Partners Action 1",
        res_model: "partner",
        views: [[1, "kanban"]],
    },
    {
        id: 3,
        xml_id: "action_3",
        name: "Partners",
        res_model: "partner",
        views: [
            [false, "list"],
            [1, "kanban"],
            [false, "form"],
        ],
    },
]);

beforeEach(() => {
    actionRegistry.add("__test__client__action__", TestClientAction, {
        force: true,
    });
});

test("can display client actions in Dialog", async () => {
    await mountWebClient();
    await getService("action").doAction({
        name: "Dialog Test",
        target: "new",
        tag: "__test__client__action__",
        type: "ir.actions.client",
    });

    expect(".modal .test_client_action").toHaveCount(1);
    expect(".modal-title").toHaveText("Dialog Test");
});

test("can display client actions in Dialog and close the dialog", async () => {
    await mountWebClient();
    await getService("action").doAction({
        name: "Dialog Test",
        target: "new",
        tag: "__test__client__action__",
        type: "ir.actions.client",
    });

    expect(".modal .test_client_action").toHaveCount(1);
    expect(".modal-title").toHaveText("Dialog Test");
    await contains(".modal .btn-close").click();
    expect(".modal .test_client_action").toHaveCount(0);
});

test("can display client actions as main, then in Dialog", async () => {
    await mountWebClient();
    await getService("action").doAction("__test__client__action__");
    expect(".o_action_manager .test_client_action").toHaveCount(1);

    await getService("action").doAction({
        target: "new",
        tag: "__test__client__action__",
        type: "ir.actions.client",
    });
    expect(".o_action_manager .test_client_action").toHaveCount(1);
    expect(".modal .test_client_action").toHaveCount(1);
});

test("can display client actions in Dialog, then as main destroys Dialog", async () => {
    await mountWebClient();
    await getService("action").doAction({
        target: "new",
        tag: "__test__client__action__",
        type: "ir.actions.client",
    });
    expect(".test_client_action").toHaveCount(1);
    expect(".modal .test_client_action").toHaveCount(1);
    await getService("action").doAction("__test__client__action__");

    expect(".test_client_action").toHaveCount(1);
    expect(".modal .test_client_action").toHaveCount(0);
});

test("dialog no header", async () => {
    await mountWebClient();
    await getService("action").doAction({
        name: "Dialog Test",
        target: "new",
        tag: "__test__client__action__",
        type: "ir.actions.client",
        context: { header: false },
    });

    expect(".modal .test_client_action").toHaveCount(1);
    expect(".modal-title").toHaveCount(0);
});

test("soft_reload will refresh data", async () => {
    onRpc("web_search_read", () => {
        expect.step("web_search_read");
    });
    await mountWebClient();
    await getService("action").doAction(1);
    expect.verifySteps(["web_search_read"]);

    await getService("action").doAction("soft_reload");
    expect.verifySteps(["web_search_read"]);
});

test("soft_reload a form view", async () => {
    onRpc("web_read", ({ args }) => {
        expect.step(`read ${args[0][0]}`);
    });
    await mountWebClient();
    await getService("action").doAction({
        name: "Partners",
        res_model: "partner",
        views: [
            [false, "list"],
            [false, "form"],
        ],
        type: "ir.actions.act_window",
    });
    await contains(".o_data_row .o_data_cell").click();
    await contains(".o_form_view .o_pager_next").click();
    expect.verifySteps(["read 1", "read 2"]);

    await getService("action").doAction("soft_reload");
    expect.verifySteps(["read 2"]);
});

test("soft_reload when there is no controller", async () => {
    await mountWebClient();
    await getService("action").doAction("soft_reload");
    expect(true).toBe(true, {
        message: "No ControllerNotFoundError when there is no controller to restore",
    });
});

test("can execute client actions from tag name", async () => {
    class ClientAction extends Component {
        static template = xml`<div class="o_client_action_test">Hello World</div>`;
        static props = null;
        props = useProps(this.constructor.props);
    }
    actionRegistry.add("HelloWorldTest", ClientAction);

    stepAllNetworkCalls();
    await mountWebClient();
    await getService("action").doAction("HelloWorldTest");
    expect(".o_control_panel").toHaveCount(0);
    expect(".o_client_action_test").toHaveText("Hello World");
    expect.verifySteps(["/web/webclient/translations", "/web/webclient/load_menus"]);
});

test("async client action (function) returning another action", async () => {
    actionRegistry.add("my_action", async () => {
        await Promise.resolve();
        return 1;
    });
    await mountWebClient();
    await getService("action").doAction("my_action");
    expect(".o_kanban_view").toHaveCount(1);
});

test("cyclic function client action chains hit the recursion limit", async () => {
    let callCount = 0;
    actionRegistry.add("looping_client_action", () => {
        callCount++;
        return { type: "ir.actions.client", tag: "looping_client_action" };
    });
    await mountWebClient();
    await expect(
        getService("action").doAction({
            type: "ir.actions.client",
            tag: "looping_client_action",
        }),
    ).rejects.toThrow("Action recursion limit exceeded (max 20)");
    expect(callCount).toBe(21);
});

test("'CLEAR-UNCOMMITTED-CHANGES' is not triggered for function client actions", async () => {
    actionRegistry.add("my_action", () => {
        expect.step("my_action");
    });

    const webClient = await mountWebClient();
    appContextOf(webClient).bus.addEventListener("CLEAR-UNCOMMITTED-CHANGES", () => {
        expect.step("CLEAR-UNCOMMITTED-CHANGES");
    });

    await getService("action").doAction("my_action");
    expect.verifySteps(["my_action"]);
});

test.tags("desktop");
test("ClientAction receives breadcrumbs and exports title", async () => {
    expect.assertions(4);

    class ClientAction extends Component {
        static template = xml`<div class="my_action" t-on-click="this.onClick">client action</div>`;
        static props = null;
        props = useProps(this.constructor.props);
        setup() {
            this.breadcrumbTitle = "myAction";
            const { breadcrumbs } = viewConfigOf(this);
            expect(breadcrumbs).toHaveLength(2);
            expect(breadcrumbs[0].name).toBe("Partners Action 1");
            onMounted(() => {
                viewConfigOf(this).setDisplayName(this.breadcrumbTitle);
            });
        }
        onClick() {
            this.breadcrumbTitle = "newTitle";
            viewConfigOf(this).setDisplayName(this.breadcrumbTitle);
        }
    }
    actionRegistry.add("SomeClientAction", ClientAction);

    await mountWebClient();
    await getService("action").doAction(1);
    await getService("action").doAction("SomeClientAction");
    expect(".my_action").toHaveCount(1);
    await contains(".my_action").click();
    await getService("action").doAction(3);
    expect(".o_breadcrumb").toHaveText("Partners Action 1\nnewTitle\nPartners");
});

test("ClientAction receives arbitrary props from doAction", async () => {
    expect.assertions(1);
    class ClientAction extends Component {
        static template = xml`<div></div>`;
        static props = null;
        props = useProps(this.constructor.props);
        setup() {
            expect(this.props.division).toBe("bell");
        }
    }
    actionRegistry.add("SomeClientAction", ClientAction);
    await mountWebClient();
    await getService("action").doAction("SomeClientAction", {
        props: { division: "bell" },
    });
});

test("ClientAction with extractProps", async () => {
    defineActions([
        {
            id: 128,
            name: "My Client Action",
            tag: "SomeClientAction",
            type: "ir.actions.client",
            params: {
                my_prop: "coucou",
            },
        },
    ]);
    class ClientAction extends Component {
        static template = xml`<div class="my_client_action" t-out="this.props.myProp"/>`;
        static props = null;
        props = useProps(this.constructor.props);
        static extractProps(/** @type {any} */ action) {
            return { myProp: action.params.my_prop };
        }
    }
    actionRegistry.add("SomeClientAction", ClientAction);
    await mountWebClient();
    await getService("action").doAction(128);
    expect(".my_client_action").toHaveText("coucou");
});

test("test display_notification client action", async () => {
    await mountWebClient();
    await getService("action").doAction(1);
    expect(".o_kanban_view").toHaveCount(1);

    await getService("action").doAction({
        type: "ir.actions.client",
        tag: "display_notification",
        params: {
            message: "message",
            sticky: true,
        },
    });
    await animationFrame();
    expect(".o_notification_manager .o_notification").toHaveCount(1);
    expect(
        ".o_notification_manager .o_notification .o_notification_content",
    ).toHaveText("message");
    expect(".o_kanban_view").toHaveCount(1);
    await contains(".o_notification_close").click();
    expect(".o_notification_manager .o_notification").toHaveCount(0);
});

test("test display_notification client action with links", async () => {
    await mountWebClient();
    await getService("action").doAction(1);
    expect(".o_kanban_view").toHaveCount(1);

    await getService("action").doAction({
        type: "ir.actions.client",
        tag: "display_notification",
        params: {
            message: "message %s <R&D>",
            sticky: true,
            links: [
                {
                    label: "test <R&D>",
                    url: "#action={action.id}&id={order.id}&model=purchase.order",
                },
            ],
        },
    });
    await animationFrame();
    expect(".o_notification_manager .o_notification").toHaveCount(1);
    expect(
        ".o_notification_manager .o_notification .o_notification_content",
    ).toHaveText("message test <R&D> <R&D>");
    expect(".o_kanban_view").toHaveCount(1);
    await contains(".o_notification_close").click();
    expect(".o_notification_manager .o_notification").toHaveCount(0);

    await getService("action").doAction({
        type: "ir.actions.client",
        tag: "display_notification",
        params: {
            message: "message %s <R&D>",
            sticky: true,
            links: [
                {
                    label: "test <R&D>",
                    url: "#action={action.id}&id={order.id}&model=purchase.order",
                },
            ],
        },
    });
    await animationFrame();
    expect(".o_notification_manager .o_notification").toHaveCount(1);
    expect(
        ".o_notification_manager .o_notification .o_notification_content",
    ).toHaveText("message test <R&D> <R&D>");
});

test("test next action on display_notification client action", async () => {
    await mountWebClient();
    const options = {
        onClose: function () {
            expect.step("onClose");
        },
    };
    await getService("action").doAction(
        {
            type: "ir.actions.client",
            tag: "display_notification",
            params: {
                title: "title",
                message: "message",
                sticky: true,
                next: {
                    type: "ir.actions.act_window_close",
                },
            },
        },
        options,
    );
    await animationFrame();
    expect(".o_notification_manager .o_notification").toHaveCount(1);
    expect.verifySteps(["onClose"]);
});

test("test reload client action", async () => {
    redirect("/odoo?test=42");
    browser.location.search = "?test=42";

    patchWithCleanup(browser.history, {
        pushState: (_state, _unused, url) => {
            expect.step(
                `pushState ${String(url).replace(browser.location.origin, "")}`,
            );
        },
        replaceState: (_state, _unused, url) => {
            expect.step(
                `replaceState ${String(url).replace(browser.location.origin, "")}`,
            );
        },
    });
    patchWithCleanup(browser.location, {
        reload: function () {
            expect.step("window_reload");
        },
    });

    await mountWebClient();
    await runAllTimers();

    await getService("action").doAction({
        type: "ir.actions.client",
        tag: "reload",
    });
    await runAllTimers();
    await getService("action").doAction({
        type: "ir.actions.client",
        tag: "reload",
        params: {
            action_id: 2,
        },
    });
    await runAllTimers();
    await getService("action").doAction({
        type: "ir.actions.client",
        tag: "reload",
        params: {
            menu_id: 1,
        },
    });
    await runAllTimers();
    await getService("action").doAction({
        type: "ir.actions.client",
        tag: "reload",
        params: {
            action_id: 1,
            menu_id: 2,
        },
    });
    await runAllTimers();
    expect.verifySteps([
        "pushState /odoo",
        "pushState /odoo",
        "window_reload",
        "pushState /odoo/action-2",
        "window_reload",
        "pushState /odoo?menu_id=1",
        "window_reload",
        "pushState /odoo/action-1?menu_id=2",
        "window_reload",
    ]);
});

test("test home client action", async () => {
    redirect("/odoo");
    browser.location.search = "";

    onRpc("/web/webclient/version_info", () => {
        expect.step("/web/webclient/version_info");
        return true;
    });

    await mountWebClient();
    patchWithCleanup(browser.location, {
        assign: (url) => expect.step(`assign ${url}`),
    });
    await getService("action").doAction({
        type: "ir.actions.client",
        tag: "home",
    });
    await runAllTimers();
    await animationFrame();
    expect.verifySteps(["/web/webclient/version_info", "assign /"]);
});

test("test display_exception client action", async () => {
    expect.errors(1);
    await mountWebClient();
    getService("action").doAction({
        type: "ir.actions.client",
        tag: "display_exception",
        params: {
            code: 0,
            message: "Odoo Server Error",
            data: {
                name: `odoo.exceptions.UserError`,
                debug: "traceback",
                arguments: [],
                context: {},
                message: "This is an error",
            },
        },
    });
    await animationFrame();
    expect(".o_dialog").toHaveCount(1);
    expect("header .modal-title").toHaveText("Invalid Operation");
    expect.verifyErrors([/RPC_ERROR/]);
});

test("a notification link with an unsafe scheme is defused", async () => {
    await mountWebClient();
    await getService("action").doAction({
        type: "ir.actions.client",
        tag: "display_notification",
        params: {
            message: "click %s",
            sticky: true,
            links: [{ label: "here", url: "javascript:alert(1)" }],
        },
    });
    await animationFrame();

    expect(".o_notification_content a").toHaveCount(0);
    expect(".o_notification_content").toHaveText("click here");
});

test("a notification link with a safe url is left alone", async () => {
    await mountWebClient();
    await getService("action").doAction({
        type: "ir.actions.client",
        tag: "display_notification",
        params: {
            message: "go %s",
            sticky: true,
            links: [{ label: "there", url: "/odoo/action-1" }],
        },
    });
    await animationFrame();

    expect(queryFirst(".o_notification_content a").getAttribute("href")).toBe(
        "/odoo/action-1",
    );
});

test("a function client action settles onClose like a close action does", async () => {
    await mountWebClient();

    let closedByNotification = 0;
    await getService("action").doAction(
        {
            type: "ir.actions.client",
            tag: "display_notification",
            params: { message: "done", type: "success" },
        },
        { onClose: () => closedByNotification++ },
    );
    await animationFrame();

    let closedByCloseAction = 0;
    await getService("action").doAction(
        { type: "ir.actions.act_window_close" },
        { onClose: () => closedByCloseAction++ },
    );

    expect(closedByNotification).toBe(1);
    expect(closedByCloseAction).toBe(1);
});

test("a function client action that chains hands onClose to the follow-up", async () => {
    registry.category("actions").add("chaining_probe", () => ({
        type: "ir.actions.client",
        tag: "display_notification",
        params: { message: "chained" },
    }));
    await mountWebClient();

    let closed = 0;
    await getService("action").doAction(
        { type: "ir.actions.client", tag: "chaining_probe" },
        { onClose: () => closed++ },
    );
    await animationFrame();

    expect(closed).toBe(1);
});

test.tags("desktop");
test("a button whose method returns a notification reloads its view", async () => {
    Partner._views.form = `
        <form>
            <header>
                <button name="do_it" type="object" string="Do it"/>
            </header>
            <group><field name="display_name"/></group>
        </form>`;
    onRpc("web_read", () => expect.step("web_read"));
    onRpc("/web/dataset/call_button/*", () => ({
        type: "ir.actions.client",
        tag: "display_notification",
        params: { message: "written", type: "success" },
    }));

    await mountWebClient();
    await getService("action").doAction({
        type: "ir.actions.act_window",
        res_model: "partner",
        res_id: 1,
        views: [[false, "form"]],
    });
    await animationFrame();
    expect.verifySteps(["web_read"]);

    await contains("button[name='do_it']").click();
    await animationFrame();

    expect(".o_notification").toHaveCount(1);
    expect.verifySteps(["web_read"]);
});

test("a delayed returned action cannot replace newer navigation", async () => {
    const pending = new Deferred();
    const entered = new Deferred();
    actionRegistry.add("delayed_return", () => {
        entered.resolve();
        return pending;
    });
    await mountWebClient();
    const action = getService("action");
    const old = action.doAction({ type: "ir.actions.client", tag: "delayed_return" });
    await entered;
    await action.doAction(1);
    const controller = action.currentController;
    pending.resolve({ type: "ir.actions.client", tag: "menu" });
    await expect(old).rejects.toThrow(SupersededError);
    expect(action.currentController).toBe(controller);
});

test("a function can deliberately perform nested navigation", async () => {
    actionRegistry.add("nested_navigation", async (env) => {
        await env.services.action.doAction(1);
    });
    await mountWebClient();
    await getService("action").doAction({
        type: "ir.actions.client",
        tag: "nested_navigation",
    });
    expect(getService("action").currentController.action.id).toBe(1);
});

test("a function client action that navigates by itself drops the caller's onClose", async () => {
    actionRegistry.add("navigating_probe", async (env) => {
        await env.services.action.doAction(3);
    });
    await mountWebClient();
    await getService("action").doAction(1);

    let closed = 0;
    await getService("action").doAction(
        { type: "ir.actions.client", tag: "navigating_probe" },
        { onClose: () => closed++ },
    );
    await animationFrame();

    expect(".o_list_view").toHaveCount(1);
    expect(closed).toBe(0);
});

test("a function client action that hands onClose to its dialog settles it on close", async () => {
    actionRegistry.add("dialog_probe", (env, _action, options) =>
        env.services.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "partner",
                res_id: 1,
                views: [[false, "form"]],
                target: "new",
            },
            { onClose: options.onClose },
        ),
    );
    await mountWebClient();

    let closed = 0;
    await getService("action").doAction(
        { type: "ir.actions.client", tag: "dialog_probe" },
        { onClose: () => closed++ },
    );
    await animationFrame();
    expect(".o_dialog .o_form_view").toHaveCount(1);
    expect(closed).toBe(0);

    await contains(".o_dialog .btn-close").click();
    expect(".o_dialog").toHaveCount(0);
    expect(closed).toBe(1);
});

test.tags("desktop");
test("soft_reload run from the action menu reloads no form it replaced", async () => {
    patchWithCleanup(useServiceProtectMethodHandling, {
        fn() {
            expect.step("service call from a destroyed component");
            return super.fn();
        },
    });
    const softReload = { id: 88, name: "Soft reload", type: "ir.actions.server" };
    defineActions([softReload]);
    Partner._toolbar = { action: [softReload], print: [] };
    onRpc("/web/action/run", () => ({ type: "ir.actions.client", tag: "soft_reload" }));
    onRpc("web_read", () => expect.step("web_read"));

    await mountWebClient();
    await getService("action").doAction({
        type: "ir.actions.act_window",
        res_model: "partner",
        res_id: 1,
        views: [[false, "form"]],
    });
    expect.verifySteps(["web_read"]);

    await toggleActionMenu();
    await toggleMenuItem("Soft reload");
    await animationFrame();

    expect(".o_form_view").toHaveCount(1);
    expect.verifySteps(["web_read"]);
});
