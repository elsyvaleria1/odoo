/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { useSpreadsheetEnv } from "@spreadsheet/hooks";
import { helpers, registries } from "@spreadsheet/o_spreadsheet/o_spreadsheet";
import { _t } from "@web/core/translation";
const { topbarComponentRegistry } = registries;

function getLocalesComparison(spreadsheetLocale, userLocale) {
    const differences = [];
    if (spreadsheetLocale.dateFormat !== userLocale.dateFormat) {
        differences.push(_t("- dates: %s", spreadsheetLocale.dateFormat));
    }

    if (
        spreadsheetLocale.thousandsSeparator !== userLocale.thousandsSeparator ||
        spreadsheetLocale.decimalSeparator !== userLocale.decimalSeparator
    ) {
        differences.push(
            _t(
                "- numbers: %s",
                helpers.formatValue(1234567.89, {
                    format: "#,##0.00",
                    locale: spreadsheetLocale,
                }),
            ),
        );
    }

    return differences.join("\n");
}

export class LocaleStatus extends Component {
    static template = "spreadsheet_edition.LocaleStatus";
    static props = {};
    props = useProps(this.constructor.props);
    env = useSpreadsheetEnv();

    get mismatchedLocaleTitle() {
        const spreadsheetLocale = this.env.model.getters.getLocale();
        const userLocale = this.env.getUserLocale();

        const title = _t(
            "Difference between user locale (%(user_locale)s) and spreadsheet locale (%(spreadsheet_locale)s). This spreadsheet is using the formats below:",
            {
                user_locale: userLocale.code,
                spreadsheet_locale: spreadsheetLocale.code,
            },
        );
        const comparison = getLocalesComparison(spreadsheetLocale, userLocale);

        return comparison ? title + "\n" + comparison : "";
    }
}

topbarComponentRegistry.add("locale_status", {
    component: LocaleStatus,
    isVisible: (env) =>
        env.getUserLocale?.() &&
        getLocalesComparison(env.model.getters.getLocale(), env.getUserLocale()) !== "",
    sequence: 12,
});
