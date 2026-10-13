// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { INVOICE_LIST, ORDER_FORM, vocabulary } from "@voice_command/../tests/fixtures";
import { interpret, RISK } from "@voice_command/interpreter/interpreter";
import { parseSpokenNumber, spokenDigits } from "@voice_command/interpreter/numbers";
import { rewriteTerms, termPhrases } from "@voice_command/interpreter/terms";
import { toISODate } from "@web/core/l10n/dates";

describe.current.tags("headless");

/**
 * @param {string} text
 * @param {any} [view]
 */
function only(text, view = null) {
    const { proposals, candidates, blocked } = interpret(text, vocabulary(view));
    expect(candidates).toEqual([], { message: `"${text}" asks to pick` });
    expect(blocked).toBe(null, { message: `"${text}" is blocked` });
    expect(proposals).toHaveLength(1, { message: `"${text}" gives one proposal` });
    return proposals[0];
}

describe("parseSpokenNumber", () => {
    test("digits, words, and both languages", () => {
        expect(parseSpokenNumber("12")).toBe(12);
        expect(parseSpokenNumber("2,5")).toBe(2.5);
        expect(parseSpokenNumber("cinco")).toBe(5);
        expect(parseSpokenNumber("treinta y cinco")).toBe(35);
        expect(parseSpokenNumber("veintidós")).toBe(22);
        expect(parseSpokenNumber("ciento treinta")).toBe(130);
        expect(parseSpokenNumber("dos mil quinientos")).toBe(2500);
        expect(parseSpokenNumber("five hundred and twelve")).toBe(512);
        expect(parseSpokenNumber("one thousand two hundred")).toBe(1200);
        expect(parseSpokenNumber("cinco punto cinco")).toBe(5.5);
        expect(parseSpokenNumber("menos tres")).toBe(-3);
        expect(parseSpokenNumber("Acme")).toBe(null);
        expect(
            spokenDigits("L dos mil veintiséis guion cero cero cuarenta y dos"),
        ).toBe("L 2026 guion 0042");
        expect(spokenDigits("cliente Acme y Beta")).toBe("cliente Acme y Beta");
        expect(spokenDigits("cero")).toBe("0");
        expect(spokenDigits("lote treinta y")).toBe("lote 30 y");
        expect(parseSpokenNumber("")).toBe(null);
    });
});

describe("launcher", () => {
    test("an app by its name, a synonym, or a misheard name", () => {
        expect(only("abre ventas").menu.label).toBe("Ventas");
        expect(only("Ventas").menu.label).toBe("Ventas");
        expect(only("open sales").menu.label).toBe("Ventas");
        expect(only("abre inventorio").menu.label).toBe("Inventario");
        expect(only("ve a contabilidad por favor").menu.label).toBe("Contabilidad");
        expect(only("abre ventas").risk).toBe(RISK.NAVIGATE);
    });

    test("a menu by its label", () => {
        const proposal = only("facturas de proveedor");
        expect(proposal.kind).toBe("open_menu");
        expect(proposal.menu.label).toBe("Facturas de proveedor");
    });

    test("a label several apps share asks which one", () => {
        const { proposals, candidates } = interpret("configuración", vocabulary());
        expect(proposals).toEqual([]);
        expect(candidates.map((c) => c.description)).toEqual([
            "Open Configuración (Ventas)",
            "Open Configuración (Inventario)",
        ]);
    });

    test("what follows the menu is kept for the view it opens", () => {
        const proposal = only("abre facturas de cliente sin pagar del mes pasado");
        expect(proposal.menu.label).toBe("Facturas de cliente");
        expect(proposal.then).toBe("sin pagar del mes pasado");
    });

    test("home, help, and nothing understood", () => {
        expect(only("inicio").kind).toBe("open_home");
        expect(only("home screen").kind).toBe("open_home");
        expect(only("¿qué puedo decir?").kind).toBe("help");
        expect(interpret("el perro come croquetas", vocabulary()).proposals).toEqual(
            [],
        );
        expect(interpret("   ", vocabulary()).proposals).toEqual([]);
    });
});

describe("search view", () => {
    test("filters, a period and a group-by in one sentence", () => {
        const proposal = only(
            "facturas sin pagar del mes pasado agrupadas por vendedor",
            INVOICE_LIST,
        );
        expect(proposal.kind).toBe("search");
        expect(proposal.risk).toBe(RISK.SEARCH);
        expect(proposal.spec).toEqual({
            filters: ["unpaid"],
            dateFilters: [{ name: "invoice_date", generatorIds: ["month-1"] }],
            groupBys: ["invoice_user_id"],
            fieldSearches: [],
        });
    });

    test("several group-bys, and a date group-by with its interval", () => {
        expect(
            only("agrupa por cliente y vendedor", INVOICE_LIST).spec.groupBys,
        ).toEqual(["partner_id", "invoice_user_id"]);
        expect(
            only("agrupado por fecha de factura por mes", INVOICE_LIST).spec.groupBys,
        ).toEqual([{ fieldName: "invoice_date", interval: "month" }]);
        expect(
            interpret("group by customer", vocabulary(INVOICE_LIST)).proposals,
        ).toEqual([]);
    });

    test("a field search keeps what was said, as it was written", () => {
        expect(only("cliente Acme Corp", INVOICE_LIST).spec.fieldSearches).toEqual([
            { fieldName: "partner_id", value: "Acme Corp" },
        ]);
        expect(only("busca INV/2019/0001", INVOICE_LIST).spec.fieldSearches).toEqual([
            { fieldName: "name", value: "INV/2019/0001" },
        ]);
        expect(only("cliente Acme sin pagar", INVOICE_LIST).spec).toEqual({
            filters: ["unpaid"],
            dateFilters: [],
            groupBys: [],
            fieldSearches: [{ fieldName: "partner_id", value: "Acme" }],
        });
    });

    test("a month by name is this year's", () => {
        expect(only("de julio", INVOICE_LIST).spec.dateFilters).toEqual([
            { name: "invoice_date", generatorIds: ["month"] },
        ]);
        expect(
            only("fecha de factura de junio", INVOICE_LIST).spec.dateFilters,
        ).toEqual([{ name: "invoice_date", generatorIds: ["month-1"] }]);
    });

    test("a partial label is not a filter", () => {
        const { proposals } = interpret("facturas", vocabulary(INVOICE_LIST));
        expect(proposals.map((p) => p.kind)).not.toInclude("search");
    });

    test("view, pager, records and clearing", () => {
        expect(only("vista kanban", INVOICE_LIST)).toEqual({
            kind: "switch_view",
            risk: RISK.NAVIGATE,
            viewType: "kanban",
            description: "Show the kanban view",
        });
        expect(only("ver como tabla dinámica", INVOICE_LIST).viewType).toBe("pivot");
        expect(
            interpret("vista calendario", vocabulary(INVOICE_LIST)).proposals,
        ).toEqual([]);
        expect(only("siguiente", INVOICE_LIST).direction).toBe("next");
        expect(only("abre la tercera", INVOICE_LIST)).toMatchObject({
            kind: "open_record",
            index: 2,
        });
        expect(interpret("abre el décimo", vocabulary(INVOICE_LIST)).proposals).toEqual(
            [],
        );
        expect(only("quita los filtros", INVOICE_LIST).kind).toBe("clear_search");
        expect(only("nuevo", INVOICE_LIST).kind).toBe("new_record");
    });

    test("a command in scope, by its name", () => {
        const proposal = only("asignarme", INVOICE_LIST);
        expect(proposal.kind).toBe("run_command");
        expect(proposal.risk).toBe(RISK.COMMIT);
        expect(only("comando mostrar vista de lista", INVOICE_LIST).risk).toBe(
            RISK.NAVIGATE,
        );
    });
});

describe("other languages", () => {
    test("a term answers to its label in the user's other languages", () => {
        const view = {
            ...INVOICE_LIST,
            filters: [{ name: "draft", label: "Borrador", alternates: ["Draft"] }],
        };
        expect(only("filtra por draft", view)).toMatchObject({
            kind: "search",
            description: "Borrador",
        });
        expect(only("borrador", view).description).toBe("Borrador");
    });
});

describe("print, export, send", () => {
    const ORDER = {
        ...ORDER_FORM,
        form: {
            ...ORDER_FORM.form,
            buttons: [
                ...ORDER_FORM.form.buttons,
                {
                    label: "Enviar",
                    spoken: [],
                    clickParams: { name: "action_send_quotation", type: "object" },
                },
            ],
        },
        reports: [
            { id: 1, name: "Cotización en PDF" },
            { id: 2, name: "Factura PROFORMA" },
        ],
    };

    test("a print asks which report, unless the sentence names one", () => {
        const { candidates } = interpret("imprime la cotización", vocabulary(ORDER));
        expect(candidates.map((c) => c.report.name)).toEqual([
            "Cotización en PDF",
            "Factura PROFORMA",
        ]);
        expect(only("imprime la factura proforma", ORDER)).toMatchObject({
            kind: "print_report",
            risk: RISK.COMMIT,
            report: { id: 2 },
        });
        expect(interpret("imprime", vocabulary(ORDER_FORM)).proposals).toEqual([]);
    });

    test("a send presses the record's send button, and waits to be confirmed", () => {
        expect(only("manda la cotización al cliente", ORDER)).toMatchObject({
            kind: "click_button",
            risk: RISK.COMMIT,
            button: { label: "Enviar" },
        });
        expect(interpret("envia", vocabulary(ORDER_FORM)).proposals).toEqual([]);
    });

    test("an export opens the dialog of the records in view, from a list only", () => {
        const list = { ...INVOICE_LIST, canExport: true };
        expect(only("exporta las facturas", list)).toMatchObject({
            kind: "export_records",
            risk: RISK.NAVIGATE,
        });
        expect(interpret("exporta", vocabulary(ORDER)).proposals).toEqual([]);
    });
});

describe("company terms", () => {
    const TERMS = termPhrases([
        { phrases: ["salva", "salvalo"], means: "guarda", kind: "word" },
        { phrases: ["status", "estatus"], means: "estado", kind: "word" },
        { phrases: ["dale clic", "dale clic en"], means: "haz clic en", kind: "word" },
        { phrases: ["nuevo"], means: "borra", kind: "word" },
    ]);

    test("a term is replaced by what it means, the rest kept as said", () => {
        expect(rewriteTerms("¿Sálvalo, por favor?", TERMS)).toBe("¿guarda, por favor?");
        expect(rewriteTerms("dale clic en Confirmar", TERMS)).toBe(
            "haz clic en Confirmar",
        );
        expect(rewriteTerms("el Estatus  de S00042.", TERMS)).toBe(
            "el estado  de S00042.",
        );
        expect(rewriteTerms("guarda", TERMS)).toBe(null);
    });

    test("the grammar reads a term as what it means, and a sentence it understands as said wins", () => {
        const withTerms = { ...vocabulary(ORDER_FORM), terms: TERMS };
        const save = interpret("salvalo", withTerms);
        expect(save.text).toBe("salvalo");
        expect(save.proposals.map((p) => p.kind)).toEqual(["save"]);
        expect(interpret("nuevo", withTerms).proposals.map((p) => p.kind)).toEqual([
            "new_record",
        ]);
        expect(interpret("salvalo", vocabulary(ORDER_FORM)).proposals).toEqual([]);
    });
});

describe("form view", () => {
    test("a button is pressed by a spoken phrase declared for it", () => {
        const view = {
            ...ORDER_FORM,
            form: {
                ...ORDER_FORM.form,
                buttons: [
                    {
                        label: "Validar",
                        spoken: ["termina la entrega"],
                        clickParams: { name: "button_validate", type: "object" },
                    },
                ],
            },
        };
        expect(only("termina la entrega", view)).toMatchObject({
            kind: "click_button",
            risk: RISK.COMMIT,
        });
        expect(only("validar", view).kind).toBe("click_button");
    });

    test("what a recogniser writes around a value is not part of it", () => {
        expect(only("cantidad 12.5.", ORDER_FORM).value).toBe(12.5);
        expect(only("Cantidad 12,5", ORDER_FORM).value).toBe(12.5);
        expect(only("cliente Acme.", ORDER_FORM).query).toBe("Acme");
        expect(only("Notas: «llamar mañana».", ORDER_FORM).value).toBe("llamar mañana");
        expect(parseSpokenNumber("12.5.")).toBe(12.5);
        expect(parseSpokenNumber("3,200")).toBe(3200);
        expect(parseSpokenNumber("1,500,000")).toBe(1500000);
        expect(parseSpokenNumber("3,200.5")).toBe(3200.5);
        expect(parseSpokenNumber("12,5")).toBe(12.5);
        expect(parseSpokenNumber("dos y")).toBe(null);
        expect(parseSpokenNumber("treinta y")).toBe(null);
        expect(parseSpokenNumber("treinta y ocho")).toBe(38);
        expect(only("Cantidad, 3,200.", ORDER_FORM).value).toBe(3200);
    });

    test("a value is staged in a field named by its label", () => {
        expect(only("cantidad cinco", ORDER_FORM)).toMatchObject({
            kind: "set_field",
            risk: RISK.STAGE,
            fieldName: "quantity",
            value: 5,
        });
        expect(only("pon la cantidad en 2.5", ORDER_FORM).value).toBe(2.5);
        expect(only("notas: llamar al cliente mañana", ORDER_FORM)).toMatchObject({
            fieldName: "note",
            value: "llamar al cliente mañana",
        });
        expect(only("prioridad urgente", ORDER_FORM).value).toBe("1");
        expect(only("es regalo sí", ORDER_FORM).value).toBe(true);
        expect(toISODate(only("fecha de entrega mañana", ORDER_FORM).value)).toBe(
            "2019-08-01",
        );
    });

    test("a relation is left to be resolved by name", () => {
        expect(only("cliente Acme", ORDER_FORM)).toMatchObject({
            fieldName: "partner_id",
            relation: "res.partner",
            query: "Acme",
        });
    });

    test("a value the field cannot hold is not a proposal", () => {
        expect(interpret("cantidad mucha", vocabulary(ORDER_FORM)).proposals).toEqual(
            [],
        );
        expect(
            interpret("prioridad altísima", vocabulary(ORDER_FORM)).proposals,
        ).toEqual([]);
    });

    test("a button waits for confirmation, naming the record", () => {
        for (const said of ["confirmar", "confirma el pedido", "pulsa confirmar"]) {
            expect(only(said, ORDER_FORM)).toMatchObject({
                kind: "click_button",
                risk: RISK.COMMIT,
                description: "Confirmar on S00042",
            });
        }
        expect(only("cancelar", ORDER_FORM).button.clickParams.name).toBe(
            "action_cancel",
        );
    });

    test("a negation never presses a button", () => {
        const { proposals, blocked } = interpret(
            "no confirmar",
            vocabulary(ORDER_FORM),
        );
        expect(proposals).toEqual([]);
        expect(blocked?.button.clickParams.name).toBe("action_confirm");
    });

    test("save and discard", () => {
        expect(only("guardar", ORDER_FORM)).toMatchObject({
            kind: "save",
            risk: RISK.STAGE,
        });
        expect(only("descartar cambios", ORDER_FORM).kind).toBe("discard");
    });
});

describe("anything on screen", () => {
    const targets = [
        { label: "Filtros", risk: RISK.NAVIGATE },
        { label: "Confirmar", risk: RISK.COMMIT },
        { label: "", risk: RISK.NAVIGATE },
    ];
    /** @param {boolean} numbersShown */
    const withTargets = (numbersShown) => ({
        ...vocabulary(INVOICE_LIST),
        targets,
        numbersShown,
    });

    test("numbers are shown and hidden by sentence", () => {
        expect(only("muestra los números").kind).toBe("show_numbers");
        expect(only("show numbers").kind).toBe("show_numbers");
        expect(only("oculta números").kind).toBe("hide_numbers");
    });

    test("a number picks what it is drawn on, with that element's risk", () => {
        const pick = (/** @type {string} */ text) => interpret(text, withTargets(true));
        expect(pick("uno").proposals[0]).toMatchObject({
            kind: "click_target",
            index: 0,
            risk: RISK.NAVIGATE,
            description: "1: Filtros",
        });
        expect(pick("número dos").proposals[0]).toMatchObject({
            index: 1,
            risk: RISK.COMMIT,
        });
        expect(pick("clic en 3").proposals[0].description).toBe("3");
        expect(pick("cuatro").proposals).toEqual([]);
        expect(pick("no dos").blocked?.index).toBe(1);
        expect(interpret("uno", withTargets(false)).proposals).toEqual([]);
    });

    test("a label is clicked only when asked to click", () => {
        const click = (/** @type {string} */ text) =>
            interpret(text, withTargets(false));
        expect(click("haz clic en filtros").proposals[0]).toMatchObject({
            kind: "click_target",
            index: 0,
        });
        expect(click("filtros").proposals.map((p) => p.kind)).not.toInclude(
            "click_target",
        );
    });
});

describe("dictation", () => {
    const withDictation = { ...vocabulary(ORDER_FORM), extensions: ["dictate"] };

    test("a field is dictated into by its label, or the long-text one", () => {
        expect(interpret("dicta notas", withDictation).proposals[0]).toMatchObject({
            kind: "dictate",
            risk: RISK.STAGE,
            fieldName: "note",
            description: "Dictating into Notas",
        });
        expect(interpret("dictar", withDictation).proposals[0].fieldName).toBe("note");
        expect(interpret("dicta cantidad", withDictation).proposals).toEqual([]);
    });

    test("nothing is dictated where no engine can take it", () => {
        expect(
            interpret("dicta notas", vocabulary(ORDER_FORM)).proposals.map(
                (p) => p.kind,
            ),
        ).not.toInclude("dictate");
    });
});

describe("chatter", () => {
    const withChatter = {
        ...vocabulary(ORDER_FORM),
        extensions: ["log_note", "compose_message"],
    };

    test("a note or a message takes the words that follow, as said", () => {
        expect(
            interpret("nota: Llamó el cliente, quiere factura", withChatter)
                .proposals[0],
        ).toMatchObject({
            kind: "log_note",
            risk: RISK.STAGE,
            text: "Llamó el cliente, quiere factura",
        });
        expect(
            interpret("send message Your order is ready", withChatter).proposals[0],
        ).toMatchObject({
            kind: "compose_message",
            text: "Your order is ready",
        });
    });

    test("a field named Notas is still a field, and nothing is noted without a chatter", () => {
        expect(interpret("notas llamar mañana", withChatter).proposals[0].kind).toBe(
            "set_field",
        );
        expect(
            interpret("nota hola", vocabulary(ORDER_FORM)).proposals.map((p) => p.kind),
        ).not.toInclude("log_note");
        expect(
            interpret("nota", withChatter).proposals.map((p) => p.kind),
        ).not.toInclude("log_note");
    });
});
