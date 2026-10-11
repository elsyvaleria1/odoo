// @ts-check

import { termPhrases } from "@voice/interpreter/terms";

const SEED = [
    [
        "checa; checar; checalo; checala; checalos; checalas; checame; chequea; chequear",
        "revisa",
        "local",
    ],
    ["resetea; resetear; resetealo; resetealos", "restablece", "local"],
    ["setea; setear; setealo; seteale", "establece", "local"],
    ["salva; salvalo; salvala", "guarda", "local"],
    [
        "dale clic; dale click; dale clic en; dale click en; clickea; cliquea; clickear; clickeale",
        "haz clic en",
        "local",
    ],
    ["postea; postear; postealo", "publica", "local"],
    ["escanea; escanear; scanea; escanealo", "escanea", "local"],
    [
        "delivery; deliveries; deliverys; delivery order; delivery orders",
        "entregas",
        "word",
    ],
    ["shipping; shipment; shipments", "envío", "word"],
    ["status; estatus", "estado", "word"],
    ["stock; stocks", "existencias", "word"],
    ["warehouse", "almacén", "word"],
    ["location; locations", "ubicación", "word"],
    ["receipt; receipts; receiving", "recepciones", "word"],
    ["picking; pickings", "recolección", "word"],
    ["transfer; transfers", "traslados", "word"],
    ["batch; batches", "lote", "word"],
    ["serial; serial number; numero de serial", "número de serie", "word"],
    ["tracking; tracking number", "seguimiento", "word"],
    ["pallet; pallets; palet", "tarimas", "word"],
    ["deadline; dedlain", "fecha límite", "word"],
    ["due date", "fecha de vencimiento", "word"],
    ["scheduled date", "fecha programada", "word"],
    ["tag; tags", "etiquetas", "word"],
    ["quote; quotes", "cotizaciones", "word"],
    ["lead; lid", "leads", "word"],
    ["email; emails; e mail; imeil", "correo", "word"],
    ["meeting; meetings; miting", "reunión", "word"],
    ["call; calls", "llamada", "word"],
    ["follow up; followup; folou", "seguimiento", "word"],
    ["item; items; aitem", "artículo", "word"],
    ["price list; pricelist", "lista de precios", "word"],
    ["discount", "descuento", "word"],
    ["payment; payments", "pago", "word"],
    ["brand", "marca", "word"],
    ["overdue", "vencidas", "word"],
    ["report; reports", "reporte", "word"],
    ["sku; skus", "referencia interna", "acronym"],
    ["po", "órdenes de compra", "acronym"],
    ["uom", "unidad de medida", "acronym"],
    [
        "pedido de compra; pedidos de compra; orden de compra",
        "órdenes de compra",
        "local",
    ],
];

export const SEED_TERMS = SEED.map(([phrases, means, kind]) => ({
    phrases: phrases.split(/\s*;\s*/),
    means,
    kind,
}));

export const SEED_PHRASES = termPhrases(SEED_TERMS);
