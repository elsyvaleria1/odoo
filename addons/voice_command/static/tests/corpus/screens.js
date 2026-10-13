// @ts-check

import { SEED_PHRASES } from "@voice_command/../tests/corpus/terms";
import { app, COMMANDS, item } from "@voice_command/../tests/fixtures";
import { saidInLanguage } from "@voice_command/interpreter/pronunciation";
import { parseISO } from "@web/core/l10n/dates";

/**
 * @param {any} term
 * @param {string[]} english its en_US label, as Odoo stores it beside es_MX
 */
function inEnglish(term, ...english) {
    return { ...term, phrases: [...term.phrases, ...saidInLanguage("en_US", english)] };
}

/**
 * A menu under a parent section, told apart from a namesake elsewhere
 * ("Facturas" under Clientes and under Proveedores).
 *
 * @param {any} term
 * @param {string} parent
 */
function under(term, parent) {
    return {
        ...term,
        menu: { ...term.menu, id: `${parent}/${term.menu.id}` },
        section: parent,
    };
}

const MENUS = [
    app("Ventas", ["Sales", "sale"]),
    app("Compras", ["Purchase"]),
    app("Inventario", ["Inventory", "stock"]),
    app("Contabilidad", ["Accounting", "Invoicing"]),
    app("Tableros", ["Dashboards"]),
    inEnglish(item("Órdenes", "Ventas"), "Orders"),
    inEnglish(item("Órdenes de compra", "Compras"), "Purchase Orders"),
    inEnglish(item("Recepciones", "Inventario"), "Receipts"),
    inEnglish(item("Entregas", "Inventario"), "Deliveries"),
    under(
        inEnglish(item("Facturas", "Contabilidad", "Clientes"), "Invoices"),
        "Clientes",
    ),
    under(
        inEnglish(item("Facturas", "Contabilidad", "Proveedores"), "Bills"),
        "Proveedores",
    ),
];

const MONTHS = ["month", "month-1", "month-2", "quarter", "year", "year-1"];

const SALES = {
    viewType: "list",
    resModel: "sale.order",
    viewTypes: ["list", "kanban", "form", "pivot"],
    filters: [
        { name: "my_quotation", label: "Mis pedidos", alternates: ["My Orders"] },
        { name: "draft", label: "Presupuestos", alternates: ["Quotations"] },
        { name: "to_invoice", label: "A facturar", alternates: ["To Invoice"] },
    ],
    dateFilters: [
        {
            name: "order_date",
            label: "Fecha de pedido",
            fieldName: "date_order",
            generatorIds: MONTHS,
        },
    ],
    groupBys: [
        {
            fieldName: "partner_id",
            label: "Cliente",
            isDate: false,
            alternates: ["Customer"],
        },
        {
            fieldName: "user_id",
            label: "Vendedor",
            isDate: false,
            alternates: ["Salesperson"],
        },
        {
            fieldName: "team_id",
            label: "Equipo de ventas",
            isDate: false,
            alternates: ["Sales Team"],
        },
        {
            fieldName: "date_order",
            label: "Fecha de pedido",
            isDate: true,
            alternates: ["Order Date"],
        },
    ],
    searchFields: [
        {
            fieldName: "partner_id",
            label: "Cliente",
            fieldType: "many2one",
            alternates: ["Customer"],
        },
        {
            fieldName: "product_id",
            label: "Producto",
            fieldType: "many2one",
            alternates: ["Product"],
        },
        {
            fieldName: "user_id",
            label: "Vendedor",
            fieldType: "many2one",
            alternates: ["Salesperson"],
        },
    ],
    recordCount: 12,
    form: null,
};

const INVOICES = {
    ...SALES,
    resModel: "account.move",
    filters: [
        { name: "unpaid", label: "Sin pagar", alternates: ["Unpaid"] },
        { name: "draft", label: "Borrador", alternates: ["Draft"] },
        { name: "overdue", label: "Vencidas", alternates: ["Overdue"] },
    ],
    dateFilters: [
        {
            name: "invoice_date",
            label: "Fecha de factura",
            fieldName: "invoice_date",
            generatorIds: MONTHS,
        },
    ],
    groupBys: [
        {
            fieldName: "partner_id",
            label: "Cliente",
            isDate: false,
            alternates: ["Customer"],
        },
        {
            fieldName: "invoice_user_id",
            label: "Vendedor",
            isDate: false,
            alternates: ["Salesperson"],
        },
        {
            fieldName: "invoice_date",
            label: "Fecha de factura",
            isDate: true,
            alternates: ["Invoice Date"],
        },
    ],
    searchFields: [
        {
            fieldName: "name",
            label: "Número",
            fieldType: "char",
            alternates: ["Number"],
        },
        {
            fieldName: "partner_id",
            label: "Cliente",
            fieldType: "many2one",
            alternates: ["Customer"],
        },
    ],
};

const BILLS = {
    ...INVOICES,
    groupBys: [
        {
            fieldName: "partner_id",
            label: "Proveedor",
            isDate: false,
            alternates: ["Vendor"],
        },
        {
            fieldName: "invoice_date",
            label: "Fecha de factura",
            isDate: true,
            alternates: ["Invoice Date"],
        },
    ],
    searchFields: [
        {
            fieldName: "name",
            label: "Número",
            fieldType: "char",
            alternates: ["Number"],
        },
        {
            fieldName: "partner_id",
            label: "Proveedor",
            fieldType: "many2one",
            alternates: ["Vendor"],
        },
    ],
};

const PICKINGS = {
    ...SALES,
    resModel: "stock.picking",
    filters: [
        { name: "ready", label: "Listo", alternates: ["Ready"] },
        { name: "waiting", label: "En espera", alternates: ["Waiting"] },
        { name: "late", label: "Retrasado", alternates: ["Late"] },
    ],
    dateFilters: [
        {
            name: "scheduled_date",
            label: "Fecha programada",
            fieldName: "scheduled_date",
            generatorIds: MONTHS,
        },
    ],
    groupBys: [
        {
            fieldName: "partner_id",
            label: "Contacto",
            isDate: false,
            alternates: ["Contact"],
        },
        {
            fieldName: "scheduled_date",
            label: "Fecha programada",
            isDate: true,
            alternates: ["Scheduled Date"],
        },
    ],
    searchFields: [
        {
            fieldName: "product_id",
            label: "Producto",
            fieldType: "many2one",
            alternates: ["Product"],
        },
        {
            fieldName: "trace_id",
            label: "Lote",
            fieldType: "many2one",
            alternates: ["Lot"],
        },
    ],
};

const ORDER = {
    viewType: "form",
    resModel: "sale.order",
    viewTypes: ["list", "form"],
    filters: [],
    dateFilters: [],
    groupBys: [],
    searchFields: [],
    recordCount: 1,
    form: {
        fields: [
            {
                name: "partner_id",
                label: "Cliente",
                type: "many2one",
                relation: "res.partner",
            },
            { name: "quantity", label: "Cantidad", type: "float" },
            { name: "price_unit", label: "Precio unitario", type: "float" },
            { name: "date_due", label: "Fecha de vencimiento", type: "date" },
            { name: "discount", label: "Descuento", type: "float" },
            {
                name: "user_id",
                label: "Vendedor",
                type: "many2one",
                relation: "res.users",
            },
            {
                name: "warehouse_id",
                label: "Almacén",
                type: "many2one",
                relation: "stock.warehouse",
            },
            { name: "scheduled_date", label: "Fecha programada", type: "date" },
            {
                name: "priority",
                label: "Prioridad",
                type: "selection",
                selection: [
                    ["0", "Normal"],
                    ["1", "Urgente"],
                ],
            },
            { name: "note", label: "Notas", type: "text" },
            { name: "description", label: "Descripción", type: "html" },
        ],
        buttons: [
            {
                label: "Confirmar",
                clickParams: { name: "action_confirm", type: "object" },
            },
            {
                label: "Confirmar pedido",
                clickParams: { name: "button_confirm", type: "object" },
            },
            {
                label: "Registrar pago",
                clickParams: { name: "action_register_payment", type: "object" },
            },
            {
                label: "Validar",
                clickParams: { name: "button_validate", type: "object" },
            },
            {
                label: "Enviar",
                clickParams: { name: "action_send_quotation", type: "object" },
            },
        ],
        displayName: "S00042",
    },
    reports: [
        { id: 1, name: "Cotización en PDF" },
        { id: 2, name: "Cotización/orden" },
        { id: 3, name: "Factura PROFORMA" },
    ],
};

/** @type {Record<string, string>} */
const FIELDS_IN_ENGLISH = {
    partner_id: "Customer",
    quantity: "Quantity",
    price_unit: "Unit Price",
    date_due: "Due Date",
    discount: "Discount",
    user_id: "Salesperson",
    warehouse_id: "Warehouse",
    scheduled_date: "Scheduled Date",
    priority: "Priority",
    note: "Notes",
    description: "Description",
};
/** @type {Record<string, string>} */
const BUTTONS_IN_ENGLISH = {
    action_confirm: "Confirm",
    button_confirm: "Confirm Order",
    action_register_payment: "Register Payment",
    button_validate: "Validate",
    action_send_quotation: "Send",
};
ORDER.form.fields = ORDER.form.fields.map((field) => ({
    ...field,
    alternates: [FIELDS_IN_ENGLISH[field.name]],
}));
ORDER.form.buttons = ORDER.form.buttons.map((button) => ({
    ...button,
    spoken: [],
    alternates: [BUTTONS_IN_ENGLISH[button.clickParams.name]],
}));

const TARGETS = [
    "Nuevo",
    "Guardar",
    "Descartar",
    "Confirmar",
    "Cancelar",
    "Imprimir",
    "Acción",
    "Anterior",
    "Siguiente",
    "Enviar mensaje",
    "Registrar una nota",
    "Actividades",
    "Seguidores",
    "Adjuntos",
    "Cliente",
    "Cantidad",
].map((label) => ({ label, risk: 0 }));

/**
 * The English labels as the loader hands them over: with how a Mexican speaker
 * says them.
 *
 * @param {any} view
 */
function asLoaded(view) {
    const said = (/** @type {any} */ term) =>
        term.alternates
            ? { ...term, alternates: saidInLanguage("en_US", term.alternates) }
            : term;
    return {
        ...view,
        canExport: view.viewType !== "form",
        filters: view.filters.map(said),
        dateFilters: view.dateFilters.map(said),
        groupBys: view.groupBys.map(said),
        searchFields: view.searchFields.map(said),
        form: view.form && {
            ...view.form,
            fields: view.form.fields.map(said),
            buttons: view.form.buttons.map(said),
        },
    };
}

/** @type {Record<string, any>} */
const VIEWS = {
    sales: asLoaded(SALES),
    invoices: asLoaded(INVOICES),
    bills: asLoaded(BILLS),
    pickings: asLoaded(PICKINGS),
    order: asLoaded(ORDER),
    order_numbers: asLoaded(ORDER),
};

/**
 * @param {string} screen
 * @param {{ terms?: import("@voice_command/interpreter/terms").TermPhrase[] }} [options]
 * @returns {import("@voice_command/interpreter/vocabulary").Vocabulary}
 */
export function corpusVocabulary(screen, { terms = SEED_PHRASES } = {}) {
    return {
        menus: MENUS,
        view: VIEWS[screen],
        commands: COMMANDS,
        today: parseISO("2026-09-26T10:00:00"),
        extensions: ["dictate", "log_note", "compose_message"],
        targets: TARGETS,
        numbersShown: screen === "order_numbers",
        terms,
    };
}
