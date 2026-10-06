// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { Deferred, tick } from "@odoo/hoot-mock";
import { MultiSelectionButtons } from "@web/views/view_components/multi_selection_buttons";

describe.current.tags("headless");

/**
 * @param {() => any} onDelete
 * @returns {Record<string, any>}
 */
function openDeleteConfirmation(onDelete) {
    /** @type {Record<string, any>[]} */
    const dialogs = [];
    const fakeThis = {
        props: { reactive: { nbSelected: 2, onDelete } },
        dialogService: {
            add: (
                /** @type {any} */ _Dialog,
                /** @type {Record<string, any>} */ props,
            ) => dialogs.push(props),
        },
    };
    MultiSelectionButtons.prototype.onDelete.call(fakeThis);
    expect(dialogs).toHaveLength(1);
    return dialogs[0];
}

test("the delete confirmation waits for the deletion to finish", async () => {
    const def = new Deferred();
    const { confirm } = openDeleteConfirmation(() => def);
    let settled = false;
    confirm().then(() => {
        settled = true;
    });
    await tick();
    expect(settled).toBe(false);
    def.resolve();
    await tick();
    expect(settled).toBe(true);
});

test("a failing deletion reaches the confirmation dialog", async () => {
    const error = new Error("unlink failed");
    const { confirm } = openDeleteConfirmation(() => Promise.reject(error));
    await expect(confirm()).rejects.toThrow("unlink failed");
});
