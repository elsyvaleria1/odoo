// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import {
    mexicanRendering,
    otherNumber,
    pronunciations,
    saidInLanguage,
    spelledOut,
} from "@voice_command/interpreter/pronunciation";
import { rewriteTerms, termPhrases } from "@voice_command/interpreter/terms";

describe.current.tags("headless");

test("English words as a Mexican speaker says them", () => {
    const said = Object.fromEntries(
        [
            "status",
            "stock",
            "scan",
            "dashboard",
            "delivery",
            "update",
            "Walmart",
            "draft",
            "save",
            "price",
            "location",
            "email",
            "ticket",
            "pipeline",
            "Journal",
            "follow up",
        ].map((word) => [word, mexicanRendering(word)]),
    );
    expect(said).toEqual({
        status: "estatus",
        stock: "estok",
        scan: "escan",
        dashboard: "dashbor",
        delivery: "deliveri",
        update: "apdeit",
        Walmart: "gualmar",
        draft: "draf",
        save: "seiv",
        price: "prais",
        location: "locashon",
        email: "emeil",
        ticket: "tiket",
        pipeline: "pipelain",
        Journal: "yournal",
        "follow up": "folow up",
    });
    expect(mexicanRendering("invoice")).toBe("invoise");
    expect(mexicanRendering("customer")).toBe(null);
});

test("acronyms by their Spanish letter names", () => {
    expect(spelledOut("PDF")).toBe("pe de efe");
    expect(spelledOut("SKU")).toBe("ese ka u");
    expect(spelledOut("PO")).toBe("pe o");
    expect(spelledOut("4x4")).toBe(null);
    expect(pronunciations("RFC", "acronym")).toEqual(["erre efe ce"]);
    expect(pronunciations("checa", "local")).toEqual([]);
});

test("an English label is heard in either number", () => {
    expect(
        [
            "Draft",
            "Customer Invoices",
            "Tax",
            "Taxes",
            "Delivery",
            "Deliveries",
            "Status",
            "Address",
            "Us",
        ].map(otherNumber),
    ).toEqual([
        "Drafts",
        "Customer Invoice",
        "Taxes",
        "Tax",
        "Deliveries",
        "Delivery",
        null,
        null,
        null,
    ]);
});

test("only English labels are said the English way", () => {
    expect(saidInLanguage("es_MX", ["Llamada", "Clave"])).toEqual(["Llamada", "Clave"]);
    expect(saidInLanguage("en_US", ["Status", "Customer"])).toEqual([
        "Status",
        "estatus",
        "Customer",
        "Customers",
    ]);
});

test("a term is reached as it is said", () => {
    const phrases = termPhrases([
        { phrases: ["status"], means: "estado", kind: "word" },
        { phrases: ["po"], means: "pedido de compra", kind: "acronym" },
        { phrases: ["chequea"], means: "muestra", kind: "local" },
    ]);
    expect(rewriteTerms("el estatus de la pe o", phrases)).toBe(
        "el estado de la pedido de compra",
    );
    expect(rewriteTerms("chequi", phrases)).toBe(null);
});
