// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { resize } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { EventBus } from "@odoo/owl";
import {
    contains,
    defineModels,
    fields,
    mockService,
    models,
    mountView,
    patchWithCleanup,
    webModels,
} from "@web/../tests/web_test_helpers";
import { SIZES } from "@web/ui/viewport";
import { ButtonBox } from "@web/views/form/button_box/button_box";

class Partner extends models.Model {
    name = fields.Char();
    _records = [
        { id: 1, name: "first" },
        { id: 2, name: "hide" },
    ];
}

const { ResCompany, ResPartner, ResUsers } = webModels;

defineModels([Partner, ResCompany, ResPartner, ResUsers]);

const NB_BUTTONS = 9;

/** @param {number} size */
function mockUiSize(size) {
    const bus = new EventBus();
    /** @type {any} */ (mockService)("ui", (/** @type {any} */ env) => {
        Object.defineProperty(env, "isSmall", {
            value: size <= SIZES.SM,
        });
        return {
            bus,
            get size() {
                return size;
            },
            get isSmall() {
                return size <= SIZES.SM;
            },
        };
    });
}

async function mountFormWithStatButtons() {
    let buttons = "";
    for (let i = 0; i < NB_BUTTONS; i++) {
        buttons += `<button class="oe_stat_button" id="btn${i}">Button ${i}</button>`;
    }
    await mountView({
        resModel: "partner",
        type: "form",
        arch: `<form><sheet><div name="button_box">${buttons}</div></sheet></form>`,
        resId: 1,
    });
}

describe("visible-button budget per ui.size", () => {
    const EXPECTED = [
        ["XS", SIZES.XS, 0],
        ["SM", SIZES.SM, 0],
        ["MD", SIZES.MD, 3],
        ["LG", SIZES.LG, 4],
        ["XL", SIZES.XL, 6],
        ["XXL", SIZES.XXL, 7],
    ];
    for (const [label, size, expectedVisible] of EXPECTED) {
        test(`${label} shows ${expectedVisible} buttons plus More`, async () => {
            mockUiSize(/** @type {number} */ (size));
            await mountFormWithStatButtons();
            expect(`.o-form-buttonbox > button.oe_stat_button`).toHaveCount(
                /** @type {number} */ (expectedVisible),
            );
            expect(`.o-form-buttonbox .o_button_more`).toHaveCount(1);
        });
    }

    test("XXL shows all buttons without More when within budget", async () => {
        mockUiSize(SIZES.XXL);
        await mountView({
            resModel: "partner",
            type: "form",
            arch: `<form><sheet><div name="button_box">
                <button class="oe_stat_button" id="btn0">B0</button>
                <button class="oe_stat_button" id="btn1">B1</button>
                <button class="oe_stat_button" id="btn2">B2</button>
                <button class="oe_stat_button" id="btn3">B3</button>
                <button class="oe_stat_button" id="btn4">B4</button>
                <button class="oe_stat_button" id="btn5">B5</button>
                <button class="oe_stat_button" id="btn6">B6</button>
                <button class="oe_stat_button" id="btn7">B7</button>
            </div></sheet></form>`,
            resId: 1,
        });
        expect(`.o-form-buttonbox > button.oe_stat_button`).toHaveCount(8);
        expect(`.o-form-buttonbox .o_button_more`).toHaveCount(0);
    });
});

describe("single rendering", () => {
    test("button box outside the sheet renders once", async () => {
        await mountView({
            resModel: "partner",
            type: "form",
            arch: `<form>
                <div name="button_box">
                    <button class="oe_stat_button" id="btn0">B0</button>
                </div>
                <sheet><field name="name"/></sheet>
            </form>`,
            resId: 1,
        });
        expect(`.o-form-buttonbox`).toHaveCount(1);
    });

    test("button box inside the sheet renders once", async () => {
        await mountView({
            resModel: "partner",
            type: "form",
            arch: `<form><sheet>
                <div name="button_box">
                    <button class="oe_stat_button" id="btn0">B0</button>
                </div>
                <field name="name"/>
            </sheet></form>`,
            resId: 1,
        });
        expect(`.o-form-buttonbox`).toHaveCount(1);
    });
});

describe("layout", () => {
    test("each slot's visibility is read once per render", async () => {
        patchWithCleanup(ButtonBox.prototype, {
            isSlotVisible(slot) {
                expect.step("isSlotVisible");
                return super.isSlotVisible(slot);
            },
        });
        await mountView({
            resModel: "partner",
            type: "form",
            arch: `<form><sheet><div name="button_box">
                <button class="oe_stat_button" id="btn0">B0</button>
                <button class="oe_stat_button" id="btn1">B1</button>
            </div></sheet></form>`,
            resId: 1,
        });
        expect(`.o-form-buttonbox > button.oe_stat_button`).toHaveCount(2);
        expect.verifySteps(["isSlotVisible", "isSlotVisible"]);
    });

    test("a button hidden by a record change leaves the box", async () => {
        await mountView({
            resModel: "partner",
            type: "form",
            arch: `<form><sheet>
                <div name="button_box">
                    <button class="oe_stat_button" id="btn0">B0</button>
                    <button class="oe_stat_button" id="btn1" invisible="name == 'hide'">B1</button>
                </div>
                <field name="name"/>
            </sheet></form>`,
            resId: 1,
        });
        expect(`.o-form-buttonbox > button.oe_stat_button`).toHaveCount(2);
        await contains(`.o_field_widget[name=name] input`).edit("hide");
        expect(`.o-form-buttonbox > button.oe_stat_button`).toHaveCount(1);
    });

    test("a shrinking screen moves buttons into More", async () => {
        await resize({ width: 1366, height: 768 });
        await mountFormWithStatButtons();
        const wide = document.querySelectorAll(
            ".o-form-buttonbox > button.oe_stat_button",
        ).length;
        expect(wide).toBeGreaterThan(0);
        await resize({ width: 375, height: 667 });
        await animationFrame();
        expect(`.o-form-buttonbox > button.oe_stat_button`).toHaveCount(0);
        expect(`.o-form-buttonbox .o_button_more`).toHaveCount(1);
    });

    test("the next record's hidden button leaves the box", async () => {
        await mountView({
            resModel: "partner",
            type: "form",
            arch: `<form><sheet>
                <div name="button_box">
                    <button class="oe_stat_button" id="btn0">B0</button>
                    <button class="oe_stat_button" id="btn1" invisible="name == 'hide'">B1</button>
                </div>
                <field name="name"/>
            </sheet></form>`,
            resId: 1,
            resIds: [1, 2],
        });
        expect(`.o-form-buttonbox > button.oe_stat_button`).toHaveCount(2);
        await contains(`.o_pager_next`).click();
        expect(`.o-form-buttonbox > button.oe_stat_button`).toHaveCount(1);
    });
});
