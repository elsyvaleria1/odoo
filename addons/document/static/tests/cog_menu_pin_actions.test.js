import { DocumentCogMenuPinAction } from "@document/views/cog_menu/document_cog_menu_pin_actions";
import { describe, destroy, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { mockService, mountWithCleanup } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");

/**
 * @param {number|string} folderId
 * @returns {Object}
 */
function makeComponentEnv(folderId) {
    return {
        searchModel: {
            getSelectedFolderId: () => folderId,
            _reloadSearchModel: () => expect.step("reload"),
        },
    };
}

test("the pin-actions cog menu reads the actions through the document service", async () => {
    mockService("document.document", () => ({
        getActions(folderId) {
            expect.step(`getActions:${folderId}`);
            return Promise.resolve([
                { id: 7, name: "Do the thing", is_embedded: false },
            ]);
        },
        enableAction() {},
        goToServerActionsView() {},
    }));

    const component = await mountWithCleanup(DocumentCogMenuPinAction, {
        componentEnv: makeComponentEnv(42),
    });
    await animationFrame();

    expect.verifySteps(["getActions:42"]);
    expect(component.documentsState.isLoading).toBe(false);
    expect(component.documentsState.actions).toHaveLength(1);
});

test("pinning an action goes through the document service", async () => {
    mockService("document.document", () => ({
        getActions() {
            return Promise.resolve([
                { id: 7, name: "Do the thing", is_embedded: false },
            ]);
        },
        enableAction(folderId, actionId) {
            expect.step(`enableAction:${folderId}:${actionId}`);
            return Promise.resolve();
        },
        goToServerActionsView() {},
    }));

    const component = await mountWithCleanup(DocumentCogMenuPinAction, {
        componentEnv: makeComponentEnv(42),
    });
    await animationFrame();

    await component.onEnableAction(7);

    expect.verifySteps(["enableAction:42:7"]);
    expect(component.documentsState.actions[0].is_embedded).toBe(true);
    destroy(component);
    expect.verifySteps(["reload"]);
});

test("closing the menu right after pinning still shows the pinned action", async () => {
    mockService("document.document", () => ({
        getActions: () =>
            Promise.resolve([{ id: 7, name: "Do it", is_embedded: false }]),
        enableAction: () => Promise.resolve(),
        goToServerActionsView() {},
    }));
    const component = await mountWithCleanup(DocumentCogMenuPinAction, {
        componentEnv: makeComponentEnv(42),
    });
    await animationFrame();
    await component.onEnableAction(7);
    destroy(component);
    expect.verifySteps(["reload"]);
});

test("a failed pin is reverted, reported, and reloads nothing", async () => {
    mockService("document.document", () => ({
        getActions: () =>
            Promise.resolve([{ id: 7, name: "Do it", is_embedded: false }]),
        enableAction: () => Promise.reject(new Error("no access")),
        goToServerActionsView() {},
    }));
    const component = await mountWithCleanup(DocumentCogMenuPinAction, {
        componentEnv: makeComponentEnv(42),
    });
    await animationFrame();
    await component.onEnableAction(7);
    destroy(component);
    await animationFrame();
    expect(component.documentsState.actions[0].is_embedded).toBe(false);
    expect(".o_notification:contains(no access)").toHaveCount(1);
    expect.verifySteps([]);
});

test("actions that fail to load stop the spinner", async () => {
    mockService("document.document", () => ({
        getActions: () => Promise.reject(new Error("boom")),
        enableAction() {},
        goToServerActionsView() {},
    }));
    const component = await mountWithCleanup(DocumentCogMenuPinAction, {
        componentEnv: makeComponentEnv(42),
    });
    await animationFrame();
    expect(component.documentsState.isLoading).toBe(false);
    expect(".o_notification:contains(boom)").toHaveCount(1);
});
