import { dropRejectionReason } from "@document/views/helper/document_draggable";
import { describe, expect, test } from "@odoo/hoot";

describe.current.tags("headless");

/**
 * @param {Object} [param0]
 * @param {number[]} [param0.movable]
 * @param {number[]} [param0.nonMovable]
 * @param {number[]} [param0.trashable]
 * @returns {Object}
 */
function makeCtx({ movable = [1], nonMovable = [], trashable } = {}) {
    const all = [...movable, ...nonMovable];
    return {
        draggedRecords: {
            movableRecordIds: movable,
            nonMovableRecordIds: nonMovable,
            trashableRecordIds: trashable ?? all,
            all,
        },
    };
}

const reject = (
    targetFolder,
    { ctx = makeCtx(), isDocumentManager = false, ancestors = [] } = {},
) =>
    dropRejectionReason({
        draggedRecords: ctx.draggedRecords,
        targetFolder,
        userIsDocumentManager: isDocumentManager,
        getFolderAndParents: () => ancestors,
    });

describe("_dropRejectionReason", () => {
    test("accepts a writable real folder", () => {
        expect(reject({ id: 42, user_permission: "edit" })).toBe("");
    });

    test("rejects a real folder the user may only view", () => {
        expect(reject({ id: 42, user_permission: "view" })).not.toBe("");
    });

    test("rejects a real folder with no permission at all", () => {
        expect(reject({ id: 42, user_permission: "none" })).not.toBe("");
    });

    test("rejects the special read-only roots and a missing target", () => {
        expect(reject({ id: "RECENT" })).not.toBe("");
        expect(reject({ id: "SHARED" })).not.toBe("");
        expect(reject(false)).not.toBe("", {
            message: "a drop on a non-folder card resolves to false",
        });
    });

    test("COMPANY keeps its documents-manager exemption", () => {
        expect(reject({ id: "COMPANY", user_permission: "view" })).not.toBe("");
        expect(
            reject(
                { id: "COMPANY", user_permission: "view" },
                { isDocumentManager: true },
            ),
        ).toBe("");
        expect(reject({ id: "COMPANY", user_permission: "edit" })).toBe("");
    });

    test("MY is not permission-checked as a real folder", () => {
        expect(reject({ id: "MY" })).toBe("");
    });

    test("rejects trashing a selection holding an untrashable document", () => {
        const ctx = makeCtx({ movable: [1, 2], trashable: [1] });
        expect(reject({ id: "TRASH" }, { ctx })).not.toBe("");
        expect(reject({ id: "TRASH" }, { ctx: makeCtx() })).toBe("");
    });

    test("trash judges what may be trashed, not what may be moved", () => {
        const ctx = makeCtx({ movable: [], nonMovable: [1], trashable: [1] });
        expect(reject({ id: "TRASH" }, { ctx })).toBe("");
    });

    test("rejects dropping a folder into itself or a descendant", () => {
        const ancestors = [{ id: 7 }, { id: 1 }, { id: "COMPANY" }];
        expect(reject({ id: 7, user_permission: "edit" }, { ancestors })).not.toBe("", {
            message: "dragged folder 1 is an ancestor of the target",
        });
        expect(
            reject(
                { id: 7, user_permission: "edit" },
                { ancestors: [{ id: 7 }, { id: "COMPANY" }] },
            ),
        ).toBe("");
    });
});

describe("targets the dropped documents cannot land in", () => {
    test('rejects "All", which holds nothing of its own', () => {
        expect(reject({ id: false, display_name: "All" })).not.toBe("");
    });

    test("judges a shortcut by the folder it points to", () => {
        expect(
            reject({ id: 42, user_permission: "edit", target_user_permission: "view" }),
        ).not.toBe("");
        expect(
            reject({ id: 42, user_permission: "view", target_user_permission: "edit" }),
        ).toBe("");
    });
});
