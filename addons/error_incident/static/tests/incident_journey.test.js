import {
    IncidentJourney,
    JOURNEY_NOTIFICATION,
} from "@error_incident/incident_journey";
import { beforeEach, describe, destroy, expect, test } from "@odoo/hoot";
import { click, queryAllTexts } from "@odoo/hoot-dom";
import { advanceTime, animationFrame } from "@odoo/hoot-mock";
import {
    makeDialogMockEnv,
    mockService,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { ClientErrorDialog, ErrorDialog } from "@web/components/errors/error_dialogs";
import { browser } from "@web/core/browser/browser";
import { user } from "@web/core/user";

describe.current.tags("desktop");

const STEPS = ["recorded", "acknowledged", "resolved"];
const OCCURRENCE = "0123456789abcdef0123456789abcdef";

/* The journey's own notifications, delivered by the test; every other type
 * goes through the real bus, which the mail and bus services rely on. */
let bus;

beforeEach(() => {
    const listeners = new Set();
    bus = {
        push(payload) {
            for (const callback of listeners) {
                callback(payload);
            }
        },
        get size() {
            return listeners.size;
        },
    };
    mockService("bus_service", {
        subscribe(type, callback) {
            if (type !== JOURNEY_NOTIFICATION) {
                return super.subscribe(type, callback);
            }
            listeners.add(callback);
            return () => listeners.delete(callback);
        },
    });
    patchWithCleanup(user, { isInternalUser: true, isSystem: false });
});

const journey = (step, extra = {}) => ({
    incident: 7,
    steps: STEPS,
    step,
    outcome: null,
    details: { count: 1, regressed: false },
    ...extra,
});

function route(answer) {
    const calls = [];
    onRpc("/error_incident/journey", async (request) => {
        const { params } = await request.json();
        calls.push(params);
        return typeof answer === "function" ? answer(calls.length) : answer;
    });
    return calls;
}

async function mountDialog(context = { error_incident: { occurrence: OCCURRENCE } }) {
    const env = await makeDialogMockEnv();
    const dialog = await mountWithCleanup(ErrorDialog, {
        env,
        props: {
            name: "RPC_ERROR",
            exceptionName: "builtins.ValueError",
            message: "boom",
            traceback: "tb",
            data: { name: "builtins.ValueError", context },
            close() {},
        },
    });
    await animationFrame();
    return dialog;
}

test("the dialog follows the incident the server named on the error", async () => {
    const calls = route({ state: "found", ...journey("acknowledged") });
    await mountDialog();
    expect(calls).toEqual([{ occurrence: OCCURRENCE }]);
    expect(".o_error_incident_head").toHaveText("A developer is working on this error");
    expect(".o_error_incident_step").toHaveCount(3);
    expect(".o_error_incident_done").toHaveCount(1);
    expect(".o_error_incident_active").toHaveAttribute("aria-current", "step");
    expect(".o_error_incident_active .o_error_incident_label").toHaveText(
        "A developer is on it",
    );
});

test("an error the server did not name asks nothing and shows nothing", async () => {
    const calls = route({ state: "found", ...journey("recorded") });
    await mountDialog({});
    expect(calls).toEqual([]);
    expect(".o_error_incident").toHaveCount(0);
    expect(bus.size).toBe(0);
});

test("a portal user asks nothing", async () => {
    patchWithCleanup(user, { isInternalUser: false });
    const calls = route({ state: "found", ...journey("recorded") });
    await mountDialog();
    expect(calls).toEqual([]);
    expect(".o_error_incident").toHaveCount(0);
});

test("an occurrence not written yet is picked up from the bus", async () => {
    const calls = route({ state: "pending" });
    await mountDialog();
    expect(".o_error_incident").toHaveCount(0);
    bus.push(journey("recorded", { occurrence: "someone-else" }));
    await animationFrame();
    expect(".o_error_incident").toHaveCount(0);
    bus.push(journey("recorded", { occurrence: OCCURRENCE }));
    await animationFrame();
    expect(".o_error_incident_head").toHaveText("This error was recorded");
    // The bus answered: the retries it stood in for are not sent.
    await advanceTime(IncidentJourney.RETRY_MS.reduce((a, b) => a + b));
    expect(calls).toHaveLength(1);
});

test("without the bus, it is asked again a few times, then given up", async () => {
    const calls = route({ state: "pending" });
    await mountDialog();
    for (const delay of IncidentJourney.RETRY_MS) {
        await advanceTime(delay);
    }
    expect(calls).toHaveLength(IncidentJourney.RETRY_MS.length + 1);
    await advanceTime(60000);
    expect(calls).toHaveLength(IncidentJourney.RETRY_MS.length + 1);
    expect(".o_error_incident").toHaveCount(0);
});

test("a retry finds it once it is written", async () => {
    route((n) =>
        n < 2 ? { state: "pending" } : { state: "found", ...journey("recorded") },
    );
    await mountDialog();
    await advanceTime(IncidentJourney.RETRY_MS[0]);
    await animationFrame();
    expect(".o_error_incident_head").toHaveText("This error was recorded");
});

test("a change of the incident is shown as it happens, without asking", async () => {
    const calls = route({ state: "found", ...journey("recorded") });
    await mountDialog();
    bus.push(journey("resolved", { incident: 8 }));
    await animationFrame();
    expect(".o_error_incident_head").toHaveText("This error was recorded");
    bus.push(journey("resolved"));
    await animationFrame();
    expect(".o_error_incident_head").toHaveText("This error is fixed");
    expect(".o_error_incident_done").toHaveCount(3);
    expect(".o_error_incident_dot_done").toHaveCount(1);
    expect(calls).toHaveLength(1);
});

test("set aside stops at the step reached and says why", async () => {
    route({ state: "found", ...journey("recorded", { outcome: "set_aside" }) });
    await mountDialog();
    expect(".o_error_incident_head").toHaveText("Set aside");
    expect(".o_error_incident_stopped").toHaveCount(1);
    expect(".o_error_incident_active").toHaveCount(0);
    expect(queryAllTexts(".o_error_incident_msg")).toEqual([
        "A developer decided not to fix it for now.",
    ]);
});

test("a regression and a count are told; a single occurrence is not", async () => {
    route({
        state: "found",
        ...journey("recorded", { details: { count: 4, regressed: true } }),
    });
    await mountDialog();
    expect(".o_error_incident_head").toHaveText("This error came back after a fix");
    expect(queryAllTexts(".o_error_incident_msg")).toEqual([
        "It is back in the developers' queue.",
        "It has happened 4 times.",
    ]);
});

test("an administrator can open the incident from the dialog", async () => {
    patchWithCleanup(user, { isSystem: true });
    route({ state: "found", ...journey("recorded") });
    const actions = [];
    mockService("action", {
        doAction(action) {
            actions.push(action);
        },
    });
    await mountDialog();
    await click(".o_error_incident_open");
    expect(actions).toEqual([
        {
            type: "ir.actions.act_window",
            res_model: "error.incident",
            res_id: 7,
            views: [[false, "form"]],
        },
    ]);
});

test("nobody else is offered the link", async () => {
    route({ state: "found", ...journey("recorded") });
    await mountDialog();
    expect(".o_error_incident_open").toHaveCount(0);
});

test("a failed lookup leaves the dialog as it was", async () => {
    onRpc("/error_incident/journey", () => {
        throw new Error("network");
    });
    await mountDialog();
    expect(".o_error_dialog").toHaveCount(1);
    expect(".o_error_incident").toHaveCount(0);
});

test("a closed dialog stops listening", async () => {
    route({ state: "pending" });
    const env = await makeDialogMockEnv();
    const dialog = await mountWithCleanup(ErrorDialog, {
        env,
        props: {
            message: "boom",
            data: { context: { error_incident: { occurrence: OCCURRENCE } } },
            close() {},
        },
    });
    expect(bus.size).toBe(1);
    destroy(dialog);
    expect(bus.size).toBe(0);
});

const STACK =
    "TypeError: boom\n    at Probe.onClick (http://h/web/assets/esm/1/web.assets_web.esm.js:1:150)";

function reportRoute(answer) {
    const calls = [];
    onRpc("/error_incident/report", async (request) => {
        const { params } = await request.json();
        calls.push(params);
        return answer;
    });
    return calls;
}

async function mountClientDialog(props = {}) {
    const env = await makeDialogMockEnv();
    await mountWithCleanup(ClientErrorDialog, {
        env,
        props: {
            name: "UncaughtClientError > TypeError",
            message: "Uncaught Javascript Error > boom",
            traceback: STACK,
            close() {},
            ...props,
        },
    });
    await animationFrame();
}

test("an error the browser raised on its own is reported and followed", async () => {
    const calls = reportRoute({
        state: "found",
        occurrence: "client-1",
        ...journey("recorded"),
    });
    const asks = route({ state: "found", ...journey("recorded") });
    await mountClientDialog();
    expect(calls).toEqual([{ stack: STACK, location: browser.location.pathname }]);
    expect(asks).toEqual([]);
    expect(".o_error_incident_head").toHaveText("This error was recorded");
    bus.push(journey("acknowledged", { incident: 7 }));
    await animationFrame();
    expect(".o_error_incident_head").toHaveText("A developer is working on this error");
});

test("a browser error without a stack is not reported", async () => {
    const calls = reportRoute({
        state: "found",
        occurrence: "client-1",
        ...journey("recorded"),
    });
    await mountClientDialog({ traceback: null });
    expect(calls).toEqual([]);
    expect(".o_error_incident").toHaveCount(0);
});

test("a server error the server did not name is not reported as a browser one", async () => {
    const calls = reportRoute({
        state: "found",
        occurrence: "client-1",
        ...journey("recorded"),
    });
    await mountDialog({});
    expect(calls).toEqual([]);
});

test("a report the server refuses leaves the dialog as it was", async () => {
    reportRoute({ state: "limited" });
    await mountClientDialog();
    expect(".o_error_incident").toHaveCount(0);
});

test("a portal user reports nothing", async () => {
    patchWithCleanup(user, { isInternalUser: false });
    const calls = reportRoute({
        state: "found",
        occurrence: "client-1",
        ...journey("recorded"),
    });
    await mountClientDialog();
    expect(calls).toEqual([]);
});
