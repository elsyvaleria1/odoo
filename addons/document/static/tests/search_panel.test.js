import { DocumentsSearchPanel } from "@document/views/search/document_search_panel";
import { describe, expect, test } from "@odoo/hoot";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { _resetMediaQueryLists } from "@web/ui/viewport";

describe.current.tags("desktop");

function makePanel(folders) {
    const values = new Map(folders.map((folder) => [folder.id, folder]));
    const panel = Object.create(DocumentsSearchPanel.prototype);
    Object.defineProperty(panel, "sections", { value: [{ id: 1 }] });
    panel.state = { expanded: { 1: {} } };
    panel.searchModel = {
        getFolderById: (id) => values.get(id) || false,
        getFolderAndParents(folder) {
            const chain = [];
            while (folder) {
                chain.push(folder);
                folder = values.get(folder.folder_id || folder.user_folder_id);
            }
            return chain;
        },
    };
    return panel;
}

const COMPANY_TREE = [
    { id: "COMPANY", rootId: "COMPANY" },
    { id: 1, folder_id: "COMPANY", rootId: "COMPANY" },
    { id: 2, folder_id: 1, rootId: "COMPANY" },
];

describe("_expandFolder", () => {
    test("unfolds the whole chain up to an expanded root", () => {
        const panel = makePanel(COMPANY_TREE);
        panel.state.expanded[1].COMPANY = true;
        panel._expandFolder({ folderId: 2 });
        expect(panel.state.expanded[1]).toEqual({ COMPANY: true, 1: true, 2: true });
    });

    test("does nothing when the chain's root is still folded", () => {
        const panel = makePanel(COMPANY_TREE);
        panel._expandFolder({ folderId: 2 });
        expect(panel.state.expanded[1]).toEqual({});
    });

    test("an id the panel does not hold is a no-op, not a crash", () => {
        const panel = makePanel(COMPANY_TREE);
        panel.state.expanded[1].COMPANY = true;
        let thrown = null;
        try {
            panel._expandFolder({ folderId: 987654 });
        } catch (error) {
            thrown = error;
        }
        expect(thrown).toBe(null);
        expect(panel.state.expanded[1]).toEqual({ COMPANY: true });
    });
});

test("the template follows the viewport instead of freezing at import", () => {
    /** @param {number} width */
    const atWidth = (width) =>
        patchWithCleanup(browser, {
            matchMedia: (/** @type {string} */ query) => {
                const min = Number(/min-width:\s*(\d+)/.exec(query)?.[1] ?? 0);
                return /** @type {any} */ ({
                    matches: width >= min,
                    addEventListener() {},
                    removeEventListener() {},
                });
            },
        });

    atWidth(1400);
    _resetMediaQueryLists();
    expect(DocumentsSearchPanel.template).toBe("document.SearchPanel");
    expect(DocumentsSearchPanel.subTemplates.category).toBe(
        "document.SearchPanel.Category",
    );

    atWidth(400);
    _resetMediaQueryLists();
    expect(DocumentsSearchPanel.template).toBe("document.SearchPanel.Small");
    expect(DocumentsSearchPanel.subTemplates.category).toBe(
        "document.SearchPanel.Category",
        { message: "one category template: nothing differs on a small screen" },
    );
});

describe("onFolderDrop", () => {
    /**
     * @param {{isManager?: boolean}} [options]
     * @returns {{panel: Object, steps: Array}}
     */
    function makeDropPanel({ isManager = false } = {}) {
        const steps = [];
        const panel = makePanel([
            { id: "COMPANY", rootId: "COMPANY", display_name: "Company" },
            { id: "MY", rootId: "MY", display_name: "My Drive" },
            { id: 1, folder_id: "COMPANY", rootId: "COMPANY", display_name: "Shared" },
            { id: 2, folder_id: 1, rootId: "COMPANY", display_name: "Sub" },
            { id: 3, user_folder_id: "MY", rootId: "MY", display_name: "Mine" },
        ]);
        panel.searchModel._reloadSearchModel = async () => steps.push("reload");
        panel.notification = {
            add: (message) => steps.push(["notify", String(message)]),
        };
        panel.orm = {
            call: async (model, method, args, kwargs) => {
                steps.push([method, args, kwargs?.location_user_folder_id]);
            },
        };
        panel.documentService = {
            userIsDocumentManager: isManager,
            moveConfirmingAccess: async (move) => {
                await move({});
                return true;
            },
        };
        return { panel, steps };
    }
    const li = (valueId) => ({ dataset: { valueId: String(valueId) } });

    test("a non-manager moves a folder under a company folder they may edit", async () => {
        const { panel, steps } = makeDropPanel();
        await panel.onFolderDrop({ element: li(3), parent: li(1), next: li(2) });
        expect(steps).toEqual([
            ["action_move_folder", [[3], "1", 2], undefined],
            "reload",
        ]);
    });

    test("the company root itself is said to be the managers'", async () => {
        const { panel, steps } = makeDropPanel();
        await panel.onFolderDrop({ element: li(3), parent: li("COMPANY") });
        expect(steps.length).toBe(1);
        expect(steps[0][0]).toBe("notify", {
            message: "refused aloud, not dropped in silence",
        });

        const manager = makeDropPanel({ isManager: true });
        await manager.panel.onFolderDrop({ element: li(3), parent: li("COMPANY") });
        expect(manager.steps).toEqual([
            ["action_move_folder", [[3], "COMPANY", false], undefined],
            "reload",
        ]);
    });

    test("into My Drive from the company tree, a folder is linked, not moved", async () => {
        const { panel, steps } = makeDropPanel();
        await panel.onFolderDrop({ element: li(2), parent: li("MY") });
        expect(steps).toEqual([["action_create_shortcut", [2], "MY"], "reload"]);
    });

    test("a root entry after the drop place is no sibling to sort against", async () => {
        const { panel, steps } = makeDropPanel({ isManager: true });
        await panel.onFolderDrop({ element: li(3), parent: li(1), next: li("MY") });
        expect(steps[0]).toEqual(["action_move_folder", [[3], "1", false], undefined]);
    });
});
