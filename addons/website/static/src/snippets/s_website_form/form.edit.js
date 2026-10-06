/** @odoo-module native */
import { makeLogger } from "@web/core/debug/debug_logger";
import {
    formatDate,
    formatDateTime,
    fromEpochMilliseconds,
} from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { Interaction } from "@web/public/interaction";
import { Form } from "@website/snippets/s_website_form/form";

/**
 * @param {string | null | undefined} seconds
 * @returns {Temporal.ZonedDateTime | null}
 */
function fromUnixSeconds(seconds) {
    const value = parseInt(seconds);
    return Number.isNaN(value) ? null : fromEpochMilliseconds(value * 1000);
}

const log = makeLogger("website.snippet.s_website_form.edit");

export class FormEdit extends Interaction {
    static selector = ".s_website_form form, form.s_website_form";
    start() {
        log.pipeline("FormEdit start: formatting datetime inputs", () => ({
            inputs: this.el.querySelectorAll(
                ".s_website_form_input.datetimepicker-input",
            ).length,
        }));
        for (const el of this.el.querySelectorAll(
            ".s_website_form_input.datetimepicker-input",
        )) {
            const value = el.getAttribute("value");
            if (value) {
                const format =
                    el.closest(".s_website_form_field").dataset.type === "date"
                        ? formatDate
                        : formatDateTime;
                el.value = format(fromUnixSeconds(value));
            }
        }
    }

    _getDataForFields() {
        if (!this.dataForValues) {
            return [];
        }
        return Object.keys(this.dataForValues)
            .map((name) => this.el.querySelector(`[name="${CSS.escape(name)}"]`))
            .filter(
                (dataForValuesFieldEl) =>
                    dataForValuesFieldEl && dataForValuesFieldEl.name !== "email_to",
            );
    }
}

registry.category("public.interactions.edit").add("website.form", {
    Interaction: FormEdit,
});

patch(Form.prototype, {
    setup() {
        super.setup();
        this.editTranslations = this.services.website_edit.isEditingTranslations();
    },
    prefillValues() {
        if (this.editTranslations) {
            log.logic("Form prefillValues: skipped while editing translations");
            return;
        }
        super.prefillValues();
    },
});
