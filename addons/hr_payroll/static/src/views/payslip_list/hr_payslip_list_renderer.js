/** @odoo-module native */
import { t } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { useDebugMode } from "@web/core/debug/debug_context";
import { ListRenderer } from "@web/views/list";

import { PayslipActionHelper } from "../../components/payslip_action_helper/payslip_action_helper.js";

// How many of a structure's benefits are worth a column before the list gets
// too wide to read.
const VISIBLE_BENEFIT_COLUMNS = 4;

export class PayslipListRenderer extends ListRenderer {
    static template = "hr_payroll.PayslipListRenderer";
    static components = {
        ...ListRenderer.components,
        PayslipActionHelper,
    };
    static props = { ...ListRenderer.props, onGenerate: t.any(), payrunId: t.any() };

    setup() {
        super.setup();
        this.debug = useDebugMode();
        this.keyPayrunOptionalFields = `payrun_${this.keyOptionalFields}`;
    }

    /**
     * @override
     * Benefits are defined per salary structure, so a benefit column only means
     * the same thing in every row while the list holds a single structure. With
     * more than one, drop them rather than line up unrelated figures; with one,
     * surface the first few instead of leaving every benefit behind the
     * optional-columns dropdown.
     *
     * This overrides processAllColumns and NOT getPropertyFieldColumns, which is
     * where upstream puts it: that method on ListRenderer
     * (web/static/src/views/list/list_renderer.js) is a wrapper nobody calls --
     * list_column_utils.processAllColumns invokes the module function directly,
     * so an override of it loads and never runs. Odoo task 28332.
     */
    processAllColumns(allColumns, list) {
        const columns = super.processAllColumns(allColumns, list);
        if (list.resModel !== "hr.payslip") {
            return columns;
        }
        const structIds = new Set(
            list.records.map((record) => record.data.struct_id?.id).filter(Boolean),
        );
        if (!structIds.size) {
            return columns;
        }
        const isBenefit = (col) =>
            col.relatedPropertyField?.name === "payslip_properties";
        if (structIds.size > 1) {
            return columns.filter((col) => !isBenefit(col));
        }
        let benefitIndex = 0;
        return columns.map((col) =>
            isBenefit(col)
                ? {
                      ...col,
                      optional:
                          benefitIndex++ < VISIBLE_BENEFIT_COLUMNS ? "show" : "hide",
                  }
                : col,
        );
    }

    get payslipActionHelperProps() {
        const helperProps = {
            onClickCreate: this.props.onAdd.bind(this.onClickCreate),
            onClickGenerate: this.props.onGenerate.bind(this.onGenerate),
        };
        if (this.props.payrunId) {
            helperProps.payrunId = this.props.payrunId;
        }
        return helperProps;
    }

    /** utils **/
    get inPayrun() {
        return this.props.payrunId;
    }

    /** overrides **/
    /**
     * @override
     */
    getActiveColumns(list) {
        if (this.inPayrun) {
            this.allColumns = this.allColumns.map((col) =>
                col.options && "payrun_optional" in col.options
                    ? { ...col, optional: col.options.payrun_optional }
                    : col,
            );
        }
        return super.getActiveColumns(list);
    }

    saveOptionalActiveFields() {
        const storageKey = this.inPayrun
            ? this.keyPayrunOptionalFields
            : this.keyOptionalFields;
        browser.localStorage.setItem(
            storageKey,
            Object.keys(this.optionalActiveFields).filter(
                (fieldName) => this.optionalActiveFields[fieldName],
            ),
        );
    }

    computeOptionalActiveFields() {
        const storageKey = this.inPayrun
            ? this.keyPayrunOptionalFields
            : this.keyOptionalFields;
        const localStorageValue = browser.localStorage.getItem(storageKey);
        const optionalColumn = this.allColumns.filter(
            (col) =>
                col.type === "field" &&
                (col.optional || (this.inPayrun && col.options?.payrun_optional)),
        );
        const optionalActiveFields = {};
        if (localStorageValue !== null) {
            const localStorageOptionalActiveFields = localStorageValue.split(",");
            for (const col of optionalColumn) {
                optionalActiveFields[col.name] =
                    localStorageOptionalActiveFields.includes(col.name);
            }
        } else {
            for (const col of optionalColumn) {
                if (this.inPayrun && col.options?.payrun_optional) {
                    optionalActiveFields[col.name] =
                        col.options?.payrun_optional === "show";
                } else {
                    optionalActiveFields[col.name] = col.optional === "show";
                }
            }
        }
        return optionalActiveFields;
    }
}
