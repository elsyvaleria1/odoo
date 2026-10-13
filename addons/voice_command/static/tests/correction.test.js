// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { INVOICE_LIST, ORDER_FORM, vocabulary } from "@voice_command/../tests/fixtures";
import {
    correctionCandidates,
    correctionInventory,
    recordSearchWords,
    recordsSoundingLike,
    soundCollisions,
    soundDistance,
    soundKey,
    understandCorrected,
} from "@voice_command/interpreter/correction";
import { interpret } from "@voice_command/interpreter/interpreter";

describe.current.tags("headless");

/** @param {any} view */
function correctOn(view) {
    const words = vocabulary(view);
    words.extensions = ["dictate", "log_note", "compose_message"];
    const inventory = correctionInventory(words);
    /** @param {string} text */
    const understood = (text) =>
        understandCorrected(text, inventory, (t) => interpret(t, words));
    return understood;
}

test("a phrase is keyed by how it sounds, word boundaries ignored", () => {
    expect(soundKey("ve a")).toBe(soundKey("Vea"));
    expect(soundKey("haz")).toBe(soundKey("Aás"));
    expect(soundKey("valida")).toBe(soundKey("baliDA"));
    expect(soundKey("de escapar")).toBe("deskapar");
    expect(soundKey("calle")).toBe("kaye");
    expect(soundKey("cerca")).toBe("serka");
    expect(soundDistance(soundKey("Visadelista"), soundKey("vista de lista"))).toBe(1);
    expect(soundDistance(soundKey("Tose"), soundKey("doce"))).toBe(0.5);
    expect(soundDistance(soundKey("Aglupa"), soundKey("agrupa"))).toBe(0.5);
});

test("only the head is corrected, and what follows is kept byte for byte", () => {
    const inventory = correctionInventory(vocabulary(ORDER_FORM));
    const [first] = correctionCandidates(
        "Pone la cantidad en 185,50 «urgente».",
        inventory,
    );
    expect(first.text.endsWith("la cantidad en 185,50 «urgente».")).toBe(true);
    expect(correctionCandidates("12 Descarpar", inventory)).toEqual([]);
    expect(
        correctionCandidates("y Descarpar", inventory).every((c) => c.heard !== "y"),
    ).toBe(true);
});

test("a misheard command is read against what the screen offers", () => {
    const onForm = correctOn(ORDER_FORM);
    expect(onForm("Descarpar")?.interpretation.proposals[0].kind).toBe("discard");
    expect(onForm("Descarpar")?.correction).toMatchObject({ heard: "Descarpar" });
    expect(onForm("Confirmal")?.interpretation.proposals[0]).toMatchObject({
        kind: "click_button",
    });
    expect(onForm("Vícta notas")?.interpretation.proposals[0]).toMatchObject({
        kind: "dictate",
        fieldName: "note",
    });
    const onList = correctOn(INVOICE_LIST);
    expect(onList("Aglupa por vendedor")?.interpretation.proposals[0]).toMatchObject({
        kind: "search",
    });
    expect(onList("el perro come croquetas")).toBe(null);
});

test("the grammar decides, and two equally near readings become a choice", () => {
    const inventory = [
        { phrase: "pata", meaning: "leg" },
        { phrase: "palo", meaning: "stick" },
    ];
    /** @param {string} text */
    const understand = (text) => ({
        text,
        proposals: ["pata", "palo"].includes(text)
            ? [{ kind: text, risk: 0, description: text }]
            : [],
        candidates: [],
        blocked: null,
    });
    const tie = understandCorrected("pato", inventory, understand);
    expect(tie?.interpretation.proposals).toEqual([]);
    expect(tie?.interpretation.candidates.map((c) => c.kind).sort()).toEqual([
        "palo",
        "pata",
    ]);
    expect(
        tie?.interpretation.candidates
            .map((c) => c.corrected)
            .sort((a, b) => a.as.localeCompare(b.as)),
    ).toEqual([
        { heard: "pato", as: "palo" },
        { heard: "pato", as: "pata" },
    ]);
    const nearest = understandCorrected("palto", inventory, understand);
    expect(nearest?.interpretation.proposals[0].kind).toBe("palo");
});

test("a value is read against the records it can name, never guessed", () => {
    /** @param {string[]} names */
    const records = (...names) =>
        names.map((display_name, id) => ({ id, display_name }));
    expect(recordSearchWords("distribuidor a López")).toEqual([
        "distribuidor",
        "López",
    ]);
    expect(
        recordsSoundingLike(
            "distribuidor a López",
            records("Distribuciones Norte", "Distribuidora López S.A. de C.V."),
        ).map((r) => r.display_name),
    ).toEqual(["Distribuidora López S.A. de C.V."]);
    expect(
        recordsSoundingLike("Juan Perez", records("Juana Paz", "Juan Pérez")).map(
            (r) => r.display_name,
        ),
    ).toEqual(["Juan Pérez"]);
    expect(
        recordsSoundingLike(
            "L2026 guion 0042",
            records("L-2026-0024", "L-2026-0042"),
        ).map((r) => r.display_name),
    ).toEqual(["L-2026-0042"]);
    expect(recordsSoundingLike("Cree", records("Urea", "Sulfato"))).toEqual([]);
    const lot = "L dos mil veintiséis guion cero cero cuarenta y dos";
    expect(recordSearchWords(lot)).toEqual(["2026", "0042"]);
    expect(
        recordsSoundingLike(lot, records("L-2026-0024", "L-2026-0042")).map(
            (r) => r.display_name,
        ),
    ).toEqual(["L-2026-0042"]);
});

test("phrases that mean different things but sound alike are named", () => {
    expect(
        soundCollisions([
            { phrase: "nuevo", meaning: "command:new_record" },
            { phrase: "nueve", meaning: "number_word" },
            { phrase: "nueva", meaning: "command:new_record" },
            { phrase: "lista", meaning: "view:list" },
            { phrase: "Listo", meaning: "filter:ready" },
            { phrase: "guardar", meaning: "command:save" },
        ]),
    ).toEqual([
        { a: "nuevo", b: "nueve", distance: 1 },
        { a: "nueve", b: "nueva", distance: 1 },
        { a: "lista", b: "listo", distance: 1 },
    ]);
});
