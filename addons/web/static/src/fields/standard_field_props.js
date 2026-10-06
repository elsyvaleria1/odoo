// @ts-check
/** @odoo-module native */
import { t } from "@odoo/owl";

/**
 * @typedef StandardFieldProps
 * @property {string} [id]
 * @property {string} name
 * @property {boolean} [readonly]
 * @property {import("@web/model/relational_model/record").RelationalRecord} record
 */

export const standardFieldProps = {
    id: t.string().optional(),
    name: t.string(),
    readonly: t.boolean().optional(),
    record: t.object(),
};
