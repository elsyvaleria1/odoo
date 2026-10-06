// @ts-check

import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { click, queryAllTexts, waitFor } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { Component, proxy, xml } from "@odoo/owl";
import { RISK } from "@voice/interpreter/interpreter";
import { parseSpokenNumber } from "@voice/interpreter/numbers";
import { useVoiceScreen } from "@voice/screens";
import {
    defineActions,
    defineMenus,
    defineModels,
    fields,
    getService,
    models,
    mountWebClient,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

describe.current.tags("desktop");

class Counter extends Component {
    static template = xml`<div class="o_test_counter">count <span class="o_count" t-out="this.state.count"/></div>`;
    static props = null;

    setup() {
        this.state = proxy({ count: 0 });
        useVoiceScreen({
            name: "counter",
            parse: (text) => {
                const words = text.trim().toLowerCase();
                if (words === "reinicia" || words === "no reinicia") {
                    return [{ kind: "reset", risk: RISK.COMMIT, description: "Reset" }];
                }
                const match = /^cuenta (.+)$/.exec(words);
                const count = match && parseSpokenNumber(match[1]);
                if (count === null || count === undefined) {
                    return null;
                }
                return [
                    {
                        kind: "count",
                        risk: RISK.STAGE,
                        count,
                        description: `Count ${count}`,
                    },
                ];
            },
            execute: async (proposal) => {
                const before = this.state.count;
                this.state.count = proposal.kind === "reset" ? 0 : proposal.count;
                return () => {
                    this.state.count = before;
                };
            },
            examples: () => ["cuenta cinco"],
            phrases: () => ["cuenta"],
        });
    }
}

class Note extends models.Model {
    _name = "x.note";
    name = fields.Char();
    _records = [{ id: 1, name: "one" }];
    _views = { list: `<list><field name="name"/></list>` };
}

defineModels([Note]);
defineActions([
    {
        id: 10,
        xml_id: "notes",
        name: "Notas",
        res_model: "x.note",
        views: [[false, "list"]],
    },
    {
        id: 20,
        xml_id: "counter",
        name: "Contador",
        type: "ir.actions.client",
        tag: "test_voice_counter",
    },
]);
defineMenus([
    { id: 1, name: "Notas", appID: 1, actionID: 10 },
    { id: 2, name: "Contador", appID: 2, actionID: 20 },
]);

beforeEach(() => {
    registry.category("actions").add("test_voice_counter", Counter, { force: true });
    user.updateUserSettings("voice_notice_acknowledged", true);
});

/** @param {string} text */
async function say(text) {
    await getService("voice").submit(text);
    await animationFrame();
}

async function openCounter() {
    await mountWebClient();
    await getService("menu").selectMenu(2);
    await waitFor(".o_test_counter");
}

test("a screen's own sentences are understood while it is shown, and undone", async () => {
    await openCounter();
    await say("cuenta treinta y dos");
    expect(".o_count").toHaveText("32");
    expect(".o_voice_done_item").toHaveText(/^Count 32/);
    await click(".o_voice_undo");
    await animationFrame();
    expect(".o_count").toHaveText("0");
    await say("abre notas");
    await waitFor(".o_list_view");
    await say("cuenta cinco");
    expect(".o_voice_message").toHaveText("I did not understand “cuenta cinco”.");
});

test("a screen's commit waits for confirmation, and a negation never runs it", async () => {
    await openCounter();
    await say("cuenta siete");
    await say("reinicia");
    expect(".o_count").toHaveText("7");
    expect(".o_voice_confirm_label").toHaveText("Reset");
    await click(".o_voice_confirm_button");
    await animationFrame();
    expect(".o_count").toHaveText("0");
    await say("cuenta siete");
    await say("no reinicia");
    expect(".o_count").toHaveText("7");
    expect(".o_voice_confirm").toHaveCount(0);
});

test("what a screen can hear is offered in the help and to the recogniser", async () => {
    await openCounter();
    await say("el perro come croquetas");
    expect(queryAllTexts(".o_voice_example")).toInclude("cuenta cinco");
    expect(getService("voice").phrases()[0]).toBe("cuenta");
});

test("something is said aloud on this device only when it has a voice", async () => {
    /** @type {any[]} */
    const said = [];
    class FakeUtterance {
        /** @param {string} text */
        constructor(text) {
            this.text = text;
            this.lang = "";
        }
    }
    patchWithCleanup(/** @type {any} */ (browser), {
        speechSynthesis: {
            cancel: () => said.push("cancel"),
            speak: (/** @type {any} */ utterance) =>
                said.push([utterance.text, utterance.lang]),
        },
        SpeechSynthesisUtterance: FakeUtterance,
    });
    await mountWebClient();
    const voice = getService("voice");
    expect(voice.speak("doce de cuarenta")).toBe(true);
    expect(said).toEqual(["cancel", ["doce de cuarenta", user.lang.replace("_", "-")]]);
    patchWithCleanup(/** @type {any} */ (browser), { speechSynthesis: undefined });
    expect(voice.speak("otra vez")).toBe(false);
});
