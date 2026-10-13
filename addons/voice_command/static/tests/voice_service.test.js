// @ts-check

import { after, beforeEach, describe, expect, test } from "@odoo/hoot";
import { click, queryAllTexts, waitFor } from "@odoo/hoot-dom";
import { advanceTime, animationFrame } from "@odoo/hoot-mock";
import { AVAILABILITY_TIMEOUT_MS } from "@voice_command/engines/voice_engines";
import {
    contains,
    defineActions,
    defineMenus,
    defineModels,
    fields,
    getFacetTexts,
    getService,
    models,
    mountWebClient,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

describe.current.tags("desktop");

class Partner extends models.Model {
    _name = "res.partner";
    name = fields.Char();
    _records = [
        { id: 1, name: "Acme" },
        { id: 2, name: "Acme Corp" },
        { id: 3, name: "Beta" },
        { id: 4, name: "Distribuidora López" },
    ];
}

class Invoice extends models.Model {
    _name = "account.move";
    name = fields.Char({ string: "Número" });
    partner_id = fields.Many2one({ string: "Cliente", relation: "res.partner" });
    paid = fields.Boolean({ string: "Pagada" });
    _records = [
        { id: 1, name: "INV/1", partner_id: 1, paid: false },
        { id: 2, name: "INV/2", partner_id: 3, paid: true },
    ];
    _views = {
        list: `<list><field name="name"/><field name="partner_id"/></list>`,
        search: `
            <search>
                <field name="name"/>
                <field name="partner_id"/>
                <filter name="unpaid" string="Sin pagar" domain="[('paid', '=', False)]"/>
            </search>`,
    };
}

class Order extends models.Model {
    _name = "sale.order";
    name = fields.Char({ string: "Referencia" });
    partner_id = fields.Many2one({ string: "Cliente", relation: "res.partner" });
    quantity = fields.Float({ string: "Cantidad" });
    note = fields.Text({ string: "Notas" });
    _records = [{ id: 7, name: "S00042", quantity: 1 }];
    _toolbar = {
        action: [],
        print: [{ id: 91, name: "Cotización en PDF", type: "ir.actions.report" }],
    };
    _views = {
        form: `
            <form>
                <header>
                    <button name="action_confirm" type="object" string="Confirmar" spoken="cierra el pedido; confirma el pedido"/>
                </header>
                <sheet>
                    <field name="name"/>
                    <field name="partner_id"/>
                    <field name="quantity"/>
                    <field name="note"/>
                </sheet>
            </form>`,
    };
}

defineModels([Partner, Invoice, Order]);

defineActions([
    {
        id: 10,
        xml_id: "invoices",
        name: "Facturas",
        res_model: "account.move",
        views: [[false, "list"]],
    },
    {
        id: 20,
        xml_id: "order",
        name: "Pedido",
        res_model: "sale.order",
        res_id: 7,
        views: [[false, "form"]],
    },
]);

defineMenus([
    {
        id: 1,
        name: "Contabilidad",
        appID: 1,
        actionID: 10,
        children: [{ id: 11, name: "Facturas de cliente", appID: 1, actionID: 10 }],
    },
    { id: 2, name: "Ventas", appID: 2, actionID: 20 },
]);

/** @param {boolean} acknowledged */
function setNoticeAcknowledged(acknowledged) {
    user.updateUserSettings("voice_notice_acknowledged", acknowledged);
    after(() => user.updateUserSettings("voice_notice_acknowledged", false));
}

beforeEach(() => {
    setNoticeAcknowledged(true);
    patchWithCleanup(browser, {
        SpeechRecognition: undefined,
        webkitSpeechRecognition: undefined,
    });
});

/** @param {string} text */
async function say(text) {
    await getService("voice").submit(text);
    await animationFrame();
}

async function openInvoices() {
    await mountWebClient();
    await getService("menu").selectMenu(1);
    await waitFor(".o_list_view");
}

async function openOrder() {
    await mountWebClient();
    await getService("menu").selectMenu(2);
    await waitFor(".o_form_view");
}

test("an app is opened by name, from anywhere", async () => {
    await mountWebClient();
    await say("abre contabilidad");
    await waitFor(".o_list_view");
    expect(".o_menu_brand").toHaveText("Contabilidad");
    expect(".o_voice_done_item").toHaveText("Open Contabilidad");
});

test("a sentence becomes facets, and undo takes them off", async () => {
    await openInvoices();
    await say("sin pagar");
    expect(getFacetTexts()).toEqual(["Sin pagar"]);
    await say("cliente Acme");
    expect(getFacetTexts()).toEqual(["Sin pagar", "Cliente\nAcme"]);
    await click(".o_voice_undo");
    await animationFrame();
    expect(getFacetTexts()).toEqual(["Sin pagar"]);
});

test("what follows a menu is applied to the view it opens", async () => {
    await mountWebClient();
    await say("abre facturas de cliente sin pagar");
    await waitFor(".o_list_view");
    await animationFrame();
    expect(getFacetTexts()).toEqual(["Sin pagar"]);
});

test("a spoken value is staged in the form, not saved", async () => {
    onRpc("web_save", () => expect.step("web_save"));
    await openOrder();
    await say("cantidad cinco");
    expect(".o_field_widget[name=quantity] input").toHaveValue("5.00");
    expect(".o_form_status_indicator_buttons").not.toHaveClass("invisible");
    expect.verifySteps([]);
});

test("a relation is resolved by name, and several matches ask which one", async () => {
    await openOrder();
    await say("cliente Acme");
    expect(".o_field_widget[name=partner_id] input").toHaveValue("Acme");
    await say("cliente Be");
    expect(".o_field_widget[name=partner_id] input").toHaveValue("Beta");
    await say("cliente Ac");
    expect(queryAllTexts(".o_voice_candidate")).toEqual([
        "Cliente: Acme",
        "Cliente: Acme Corp",
    ]);
    await click(".o_voice_candidate:eq(1)");
    await animationFrame();
    expect(".o_field_widget[name=partner_id] input").toHaveValue("Acme Corp");
});

test("a button waits for an explicit confirmation", async () => {
    onRpc("sale.order", "action_confirm", () => {
        expect.step("action_confirm");
        return true;
    });
    await openOrder();
    await say("confirmar");
    expect(".o_voice_confirm_label").toHaveText("Confirmar on S00042");
    expect.verifySteps([]);
    await click(".o_voice_confirm_button");
    await animationFrame();
    expect.verifySteps(["action_confirm"]);
});

test("a negation never presses a button", async () => {
    onRpc("sale.order", "action_confirm", () => expect.step("action_confirm"));
    await openOrder();
    await say("no confirmar");
    expect(".o_voice_confirm").toHaveCount(0);
    expect(".o_voice_message").toHaveText(
        "That sounded like a “no”: Confirmar on S00042 was not done.",
    );
    expect.verifySteps([]);
});

test("what is not understood shows what can be said here", async () => {
    await openInvoices();
    await say("el perro come croquetas");
    expect(".o_voice_message").toHaveText(
        "I did not understand “el perro come croquetas”.",
    );
    expect(queryAllTexts(".o_voice_example")).toInclude("Sin pagar");
});

test("the palette takes a sentence after “>”", async () => {
    await openInvoices();
    await getService("command").openMainPalette({ searchValue: ">sin pagar" });
    await waitFor(".o_command");
    expect(".o_command").toHaveText("Sin pagar");
    await click(".o_command");
    await animationFrame();
    expect(getFacetTexts()).toEqual(["Sin pagar"]);
});

test("the microphone says so when no engine can listen", async () => {
    await openInvoices();
    await click(".o_voice_systray");
    await animationFrame();
    expect(".o_voice_message").toHaveText(
        "No speech engine is available here. You can still type what you would say in the command palette, after “>”.",
    );
});

test("the first time, the microphone says where the audio goes before listening", async () => {
    setNoticeAcknowledged(false);
    onRpc("res.users.settings", "set_res_users_settings", ({ kwargs }) => {
        expect.step(Object.keys(kwargs.new_settings).join());
        return { voice_notice_acknowledged: true };
    });
    registry.category("voice_engines").add(
        "test",
        {
            available: async () => true,
            listen: async (/** @type {any} */ { onInterim }) => {
                onInterim("sin");
                return "sin pagar";
            },
            privacy: () => "Heard by a test engine.",
        },
        { sequence: 1 },
    );
    await openInvoices();
    await contains(".o_voice_systray").click();
    await waitFor(".o_voice_notice");
    expect(".o_voice_notice p:first").toHaveText("Heard by a test engine.");
    expect(getFacetTexts()).toEqual([]);
    await click(".o_voice_notice_accept");
    await animationFrame();
    await animationFrame();
    expect(getFacetTexts()).toEqual(["Sin pagar"]);
    expect.verifySteps(["voice_notice_acknowledged"]);
    registry.category("voice_engines").remove("test");
});

test("the browser engine listens on the device only, biased to what is on screen", async () => {
    /** @type {any[]} */
    const created = [];
    class FakeRecognition {
        static available = async (/** @type {any} */ options) => {
            expect.step(`available:${options.processLocally}`);
            return "available";
        };
        constructor() {
            created.push(this);
        }
        start() {
            queueMicrotask(() => {
                const result = Object.assign([{ transcript: "sin pagar" }], {
                    isFinal: true,
                });
                /** @type {any} */ (this).onresult({ results: [result] });
                /** @type {any} */ (this).onend();
            });
        }
        stop() {}
    }
    patchWithCleanup(browser, { SpeechRecognition: FakeRecognition });
    await openInvoices();
    await click(".o_voice_systray");
    await waitFor(".o_voice_done_item");
    await animationFrame();
    expect(getFacetTexts()).toEqual(["Sin pagar"]);
    expect(created[0].processLocally).toBe(true);
    expect(created[0].interimResults).toBe(true);
    expect.verifySteps(["available:true"]);
});

test("numbers are drawn on what can be clicked, and a number clicks it", async () => {
    onRpc("sale.order", "action_confirm", () => {
        expect.step("action_confirm");
        return true;
    });
    await openOrder();
    await say("muestra números");
    const voice = getService("voice");
    expect(".o_voice_number").toHaveCount(voice.targets.length);
    const confirm = voice.targets.findIndex((target) => target.label === "Confirmar");
    expect(confirm).toBeGreaterThan(-1);
    await say(String(confirm + 1));
    expect(".o_voice_confirm_label").toHaveText(`${confirm + 1}: Confirmar`);
    expect(".o_voice_number").toHaveCount(voice.targets.length, {
        message: "the numbers stay while the choice waits",
    });
    expect.verifySteps([]);
    await click(".o_voice_confirm_button");
    await animationFrame();
    expect.verifySteps(["action_confirm"]);
    expect(".o_voice_number").toHaveCount(0);
});

test("a label on screen is clicked by name", async () => {
    await openInvoices();
    await say("haz clic en New");
    await waitFor(".o_form_view");
    expect(".o_form_view .o_form_editable").toHaveCount(1);
});

test("an engine that never says whether it can listen is passed over", async () => {
    const engines = registry.category("voice_engines");
    engines.add(
        "silent",
        {
            available: () => new Promise(() => {}),
            listen: async () => "never",
            privacy: () => "",
        },
        { sequence: 1 },
    );
    engines.add(
        "answering",
        {
            available: async () => true,
            listen: async () => "sin pagar",
            privacy: () => "",
        },
        { sequence: 2 },
    );
    await openInvoices();
    await click(".o_voice_systray");
    await advanceTime(AVAILABILITY_TIMEOUT_MS);
    await waitFor(".o_voice_done_item");
    await animationFrame();
    expect(getFacetTexts()).toEqual(["Sin pagar"]);
    engines.remove("silent");
    engines.remove("answering");
});

test("nothing said is shared unless the user chose to", async () => {
    onRpc("voice.sentence", "record", () => expect.step("record"));
    await openInvoices();
    await say("sin pagar");
    await say("el perro come croquetas");
    expect.verifySteps([]);
});

test("a shared sentence carries its words only when the grammar missed", async () => {
    user.updateUserSettings("voice_share_sentences", true);
    after(() => user.updateUserSettings("voice_share_sentences", false));
    onRpc("voice.sentence", "record", ({ args, kwargs }) => {
        expect.step([...args, kwargs.spoken, kwargs.res_model, kwargs.view_type]);
        return true;
    });
    await openInvoices();
    await say("sin pagar");
    await say("el perro come croquetas");
    expect.verifySteps([
        ["grammar", "sin pagar", false, "account.move", "list"],
        ["none", "el perro come croquetas", false, "account.move", "list"],
    ]);
});

test("the notice and the help panel both offer sharing", async () => {
    setNoticeAcknowledged(false);
    onRpc("res.users.settings", "set_res_users_settings", ({ kwargs }) => {
        expect.step(kwargs.new_settings);
        return kwargs.new_settings;
    });
    onRpc("voice.sentence", "record", ({ args, kwargs }) => {
        expect.step(`${args[0]}, spoken: ${kwargs.spoken}`);
        return true;
    });
    registry.category("voice_engines").add(
        "test",
        {
            available: async () => true,
            listen: async () => "el perro come croquetas",
            privacy: () => "Heard by a test engine.",
        },
        { sequence: 1 },
    );
    after(() => {
        registry.category("voice_engines").remove("test");
        user.updateUserSettings("voice_share_sentences", false);
    });
    await openInvoices();
    await contains(".o_voice_systray").click();
    await waitFor(".o_voice_notice");
    expect(".o_voice_notice .o_voice_share_input").not.toBeChecked();
    await click(".o_voice_notice .o_voice_share_input");
    await click(".o_voice_notice_accept");
    await waitFor(".o_voice_help");
    await animationFrame();
    expect.verifySteps([
        { voice_share_sentences: true },
        { voice_notice_acknowledged: true },
        "none, spoken: true",
    ]);
    expect(".o_voice_help .o_voice_share_input").toBeChecked();
    await click(".o_voice_help .o_voice_share_input");
    await animationFrame();
    expect.verifySteps([{ voice_share_sentences: false }]);
});

test("a misheard command is read against the screen, and says so", async () => {
    user.updateUserSettings("voice_share_sentences", true);
    after(() => user.updateUserSettings("voice_share_sentences", false));
    onRpc("voice.sentence", "record", ({ args }) => {
        expect.step(args.slice(0, 2));
        return true;
    });
    await openOrder();
    await say("Descarpar.");
    expect(".o_voice_correction").toHaveText(
        "Understood “descartar” (heard “Descarpar”)",
    );
    expect(".o_voice_done_item").toHaveText("Discard changes");
    expect.verifySteps([["correction", "Descarpar."]]);
    await say("el perro come croquetas");
    expect(".o_voice_correction").toHaveCount(0);
    expect.verifySteps([["none", "el perro come croquetas"]]);
});

test("a name heard wrong offers the records that sound like it, and takes none unasked", async () => {
    await openOrder();
    await say("cliente distribuidor a López");
    expect(queryAllTexts(".o_voice_candidate")).toEqual([
        "Cliente: Distribuidora López",
    ]);
    expect(".o_field_widget[name=partner_id] input").toHaveValue("");
    await click(".o_voice_candidate");
    await animationFrame();
    expect(".o_field_widget[name=partner_id] input").toHaveValue("Distribuidora López");
    await say("cliente Zzyzx");
    expect(".o_voice_message").toHaveText("Nothing matches “Zzyzx”.");
});

test("a button answers to the phrases declared beside its label", async () => {
    onRpc("sale.order", "action_confirm", () => {
        expect.step("action_confirm");
        return true;
    });
    await openOrder();
    await say("cierra el pedido");
    expect(".o_voice_confirm_label").toHaveText("Confirmar on S00042");
    await click(".o_voice_confirm_button");
    await animationFrame();
    expect.verifySteps(["action_confirm"]);
    await say("el perro come croquetas");
    expect(queryAllTexts(".o_voice_example")).toInclude("cierra el pedido");
});

test("a search by a name heard wrong offers the records that sound like it", async () => {
    await openInvoices();
    await say("cliente distribuidor a López");
    expect(queryAllTexts(".o_voice_candidate")).toEqual([
        "Cliente: Distribuidora López",
    ]);
    expect(getFacetTexts()).toEqual([]);
    await click(".o_voice_candidate");
    await animationFrame();
    expect(getFacetTexts()).toEqual(["Cliente\nDistribuidora López"]);
});

test("a word in the user's other language reaches the term it names", async () => {
    onRpc("voice.labels", "menu_labels", () => ({ en_US: { 1: "Accounting" } }));
    onRpc("voice.labels", "view_labels", () => ({
        en_US: {
            filters: { unpaid: "Unpaid" },
            date_filters: {},
            group_bys: {},
            search_fields: { partner_id: "Customer" },
            form_fields: {},
            buttons: {},
            fields: { partner_id: "Customer" },
        },
    }));
    await openInvoices();
    await say("unpaid");
    expect(getFacetTexts()).toEqual(["Sin pagar"]);
    await say("customer Acme");
    expect(getFacetTexts()).toEqual(["Sin pagar", "Cliente\nAcme"]);
    await say("home");
    await say("open accounting");
    await waitFor(".o_list_view");
    expect(".o_menu_brand").toHaveText("Contabilidad");
});

test("a spoken command nothing understood is heard again in English, and says so", async () => {
    user.updateUserSettings("voice_share_sentences", true);
    after(() => user.updateUserSettings("voice_share_sentences", false));
    patchWithCleanup(user, { lang: "es_MX" });
    onRpc("voice.sentence", "record", ({ args }) => {
        expect.step(args.slice(0, 2));
        return true;
    });
    await openInvoices();
    const again = async (/** @type {string} */ language) => {
        expect.step(`again in ${language}`);
        return "show numbers";
    };
    const voice = getService("voice");
    await voice.submit("el perro come croquetas", { spoken: true, again });
    await animationFrame();
    expect(".o_voice_correction").toHaveText(
        "Understood “show numbers” (heard “el perro come croquetas”)",
    );
    expect.verifySteps(["again in en", ["english", "el perro come croquetas"]]);
    await voice.submit("sin pagar", { spoken: true, again });
    await animationFrame();
    expect(getFacetTexts()).toEqual(["Sin pagar"]);
    expect.verifySteps([["grammar", "sin pagar"]]);
});

test("a session in English is never heard again in English", async () => {
    patchWithCleanup(user, { lang: "en_US" });
    await openInvoices();
    const again = async () => {
        expect.step("again");
        return "show numbers";
    };
    await getService("voice").submit("el perro come croquetas", {
        spoken: true,
        again,
    });
    expect.verifySteps([]);
});

test("a reading chosen among several is kept for an administrator to approve", async () => {
    onRpc("speech.vocabulary.form", "learn", ({ args }) => {
        expect.step(args);
        return true;
    });
    await openInvoices();
    const voice = getService("voice");
    const choose = async () => {
        const [proposal] = voice.interpret("sin pagar").proposals;
        voice.state.candidates = [
            { ...proposal, corrected: { heard: "sin pagal", as: "sin pagar" } },
        ];
        await voice.pick(0);
        await animationFrame();
    };
    await choose();
    expect(getFacetTexts()).toEqual(["Sin pagar"]);
    expect.verifySteps([]);
    user.updateUserSettings("voice_share_sentences", true);
    after(() => user.updateUserSettings("voice_share_sentences", false));
    await choose();
    expect.verifySteps([["sin pagal", "sin pagar"]]);
});

test("a spoken print runs the record's report once confirmed", async () => {
    await openOrder();
    const voice = getService("voice");
    /** @type {any[]} */
    const printed = [];
    patchWithCleanup(getService("action"), {
        doAction: async (/** @type {any} */ id, /** @type {any} */ options) => {
            printed.push([id, options.additionalContext.active_ids]);
        },
    });
    await say("imprime la cotización");
    expect(voice.state.pending?.description).toBe("Print Cotización en PDF of S00042");
    expect(printed).toEqual([]);
    await voice.confirm();
    expect(printed).toEqual([[91, [7]]]);
});

test("a spoken export opens the export dialog of the list", async () => {
    onRpc("/web/export/formats", () => [{ tag: "xlsx", label: "XLSX" }]);
    onRpc("/web/export/get_fields", () => []);
    onRpc("ir.exports", "search_read", () => []);
    await openInvoices();
    await say("exporta las facturas");
    await waitFor(".o_export_data_dialog");
    expect(".o_export_data_dialog").toHaveCount(1);
});
