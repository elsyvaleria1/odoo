// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { queryOne } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { Component, useProps, xml } from "@odoo/owl";
import {
    Country,
    Partner,
    Player,
    Product,
    Stage,
    Team,
} from "@web/../tests/components/tree_editor/condition_tree_editor_test_helpers";
import {
    contains,
    defineModels,
    makeDialogMockEnv,
    makeServerError,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { DomainSelectorDialog } from "@web/components/domain_selector_dialog/domain_selector_dialog";

describe.current.tags("desktop");

async function makeDomainSelectorDialog(params = {}) {
    const props = { ...params };

    class Parent extends Component {
        static components = { DomainSelectorDialog };
        static template = xml`<DomainSelectorDialog t-props="this.domainSelectorProps"/>`;
        static props = null;
        props = useProps(this.constructor.props);
        setup() {
            this.domainSelectorProps = {
                readonly: false,
                domain: "[]",
                close: () => {},
                onConfirm: () => {},
                ...props,
                resModel: "partner",
            };
        }
    }

    const env = await makeDialogMockEnv();
    return mountWithCleanup(Parent, { env, props });
}

defineModels([Partner, Product, Team, Player, Country, Stage]);

test("a domain with a user context dynamic part is valid", async () => {
    await makeDomainSelectorDialog({
        domain: "[('foo', '=', uid)]",
        onConfirm(/** @type {any} */ domain) {
            expect(domain).toBe("[('foo', '=', uid)]");
            expect.step("confirmed");
        },
    });
    onRpc("/web/domain/validate", () => {
        expect.step("validation");
        return true;
    });
    await contains(".o_dialog footer button").click();
    expect.verifySteps(["validation", "confirmed"]);
});

test("can extend eval context", async () => {
    await makeDomainSelectorDialog({
        domain: "['&', ('foo', '=', uid), ('bar', '=', var)]",
        context: { uid: 99, var: "true" },
        onConfirm(/** @type {any} */ domain) {
            expect(domain).toBe("['&', ('foo', '=', uid), ('bar', '=', var)]");
            expect.step("confirmed");
        },
    });
    onRpc("/web/domain/validate", () => {
        expect.step("validation");
        return true;
    });
    await contains(".o_dialog footer button").click();
    expect.verifySteps(["validation", "confirmed"]);
});

test("a domain with an unknown expression is not valid", async () => {
    await makeDomainSelectorDialog({
        domain: "[('foo', '=', unknown)]",
        onConfirm() {
            expect.step("confirmed");
        },
    });
    onRpc("/web/domain/validate", () => {
        expect.step("validation");
        return true;
    });
    await contains(".o_dialog footer button").click();
    expect.verifySteps([]);
});

test("model_field_selector should close on dialog drag", async () => {
    await makeDomainSelectorDialog({
        domain: "[('foo', '=', unknown)]",
    });

    expect(".o_model_field_selector_popover").toHaveCount(0);
    await contains(".o_model_field_selector_value").click();
    expect(".o_model_field_selector_popover").toHaveCount(1);

    const header = queryOne(".modal-header");
    const headerRect = header.getBoundingClientRect();
    await contains(header).dragAndDrop(document.body, {
        position: {
            x: headerRect.x + headerRect.width / 2 + 20,
            y: headerRect.y + headerRect.height / 2 + 50,
        },
    });
    await animationFrame();
    expect(".o_model_field_selector_popover").toHaveCount(0);
});

describe("validation failures", () => {
    /** @returns {Promise<any>} */
    async function mountAndCapture() {
        /** @type {any} */
        let dialog;
        patchWithCleanup(DomainSelectorDialog.prototype, {
            setup() {
                super.setup();
                dialog = this;
            },
        });
        await makeDomainSelectorDialog({ domain: "[('foo', '=', 1)]" });
        return dialog;
    }

    test("a ValidationError from the server means the domain is invalid", async () => {
        const dialog = await mountAndCapture();
        onRpc("/web/domain/validate", () => {
            throw makeServerError({
                type: "ValidationError",
                message: "Invalid model",
            });
        });
        await expect(dialog.isValueValid()).resolves.toBe(false);
    });

    test("an access failure surfaces instead of calling the domain invalid", async () => {
        const dialog = await mountAndCapture();
        onRpc("/web/domain/validate", () => {
            throw makeServerError({
                type: "AccessError",
                message: "This endpoint is reserved to internal users.",
            });
        });
        await expect(dialog.isValueValid()).rejects.toThrow(
            /reserved to internal users/,
        );
    });
});
