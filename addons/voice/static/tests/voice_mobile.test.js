// @ts-check

import { beforeEach, describe, expect, getFixture, test } from "@odoo/hoot";
import { click, queryRect, waitFor } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    contains,
    defineActions,
    defineMenus,
    defineModels,
    fields,
    getService,
    models,
    mountWebClient,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

describe.current.tags("mobile");

class Order extends models.Model {
    _name = "sale.order";
    name = fields.Char({ string: "Referencia" });
    quantity = fields.Float({ string: "Cantidad" });
    _records = [{ id: 7, name: "S00042", quantity: 1 }];
    _views = {
        form: `
            <form>
                <header>
                    <button name="action_confirm" type="object" string="Confirmar"/>
                </header>
                <sheet>
                    <field name="name"/>
                    <field name="quantity"/>
                </sheet>
            </form>`,
    };
}

defineModels([Order]);

defineActions([
    {
        id: 20,
        xml_id: "order",
        name: "Pedido",
        res_model: "sale.order",
        res_id: 7,
        views: [[false, "form"]],
    },
]);

defineMenus([{ id: 2, name: "Ventas", appID: 2, actionID: 20 }]);

beforeEach(() => {
    user.updateUserSettings("voice_notice_acknowledged", true);
    patchWithCleanup(browser, {
        SpeechRecognition: undefined,
        webkitSpeechRecognition: undefined,
    });
});

async function openOrder() {
    await mountWebClient();
    await getService("menu").selectMenu(2);
    await waitFor(".o_form_view");
}

/** @param {string} selector */
function expectWithinScreen(selector) {
    const screen = queryRect(getFixture());
    const rect = queryRect(selector);
    expect(rect.left).toBeGreaterThan(screen.left - 1);
    expect(rect.right).toBeLessThan(screen.right + 1);
}

test("on a phone the microphone is in the navbar, and what a server engine hears is staged", async () => {
    const engines = registry.category("voice_engines");
    engines.add(
        "server_stand_in",
        {
            available: async () => true,
            listen: async () => "cantidad cinco",
            privacy: () => "",
        },
        { sequence: 1 },
    );
    onRpc("web_save", () => expect.step("web_save"));
    await openOrder();
    expect(".o_voice_systray").toBeVisible();
    await contains(".o_voice_systray").click();
    await waitFor(".o_voice_done_item");
    expect(".o_field_widget[name=quantity] input").toHaveValue("5.00");
    expectWithinScreen(".o_voice_hud");
    expect.verifySteps([]);
    engines.remove("server");
});

test("on a phone a button's confirmation fits the screen and is pressed by touch", async () => {
    onRpc("sale.order", "action_confirm", () => {
        expect.step("action_confirm");
        return true;
    });
    await openOrder();
    await getService("voice").submit("confirmar");
    await animationFrame();
    expect(".o_voice_confirm_label").toHaveText("Confirmar on S00042");
    expectWithinScreen(".o_voice_hud");
    expectWithinScreen(".o_voice_confirm_button");
    expect.verifySteps([]);
    await click(".o_voice_confirm_button");
    await animationFrame();
    expect.verifySteps(["action_confirm"]);
});
