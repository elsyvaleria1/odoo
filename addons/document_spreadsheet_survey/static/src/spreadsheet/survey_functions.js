/** @odoo-module native */

import { helpers, registries } from "@odoo/o-spreadsheet";
import { _t } from "@web/core/translation";
const { arg, toNumber } = helpers;

registries.functionRegistry.add("ODOO.SURVEY", {
    description: _t("Return the results of a survey."),
    args: [arg("survey_id (number)", _t("The survey id"))],
    category: "Odoo",
    compute: function (surveyId) {
        surveyId = toNumber(surveyId, this.locale);
        return this.getters.getSurveyResults(surveyId).survey_table;
    },
});
