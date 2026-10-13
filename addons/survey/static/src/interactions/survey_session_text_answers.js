/** @odoo-module native */
import SESSION_CHART_COLORS from "@survey/interactions/survey_session_colors";
import { getPaletteColor } from "@web/core/colors/colors";
import {
    deserializeDate,
    deserializeDateTime,
    formatDate,
    formatDateTime,
} from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { renderToElement } from "@web/core/utils/render";
import { Interaction } from "@web/public/interaction";

export class SurveySessionTextAnswers extends Interaction {
    static selector = ".o_survey_session_text_answers_container";
    dynamicContent = {
        _root: {
            "t-on-updateTextAnswers": this.updateTextAnswers,
        },
    };

    setup() {
        this.answerIds = [];
    }

    /** @param {CustomEvent} ev */
    updateTextAnswers(ev) {
        const inputLineValues = ev.detail.inputLineValues;
        const questionType = ev.detail.questionType;

        inputLineValues.forEach((inputLineValue) => {
            if (!this.answerIds.includes(inputLineValue.id) && inputLineValue.value) {
                let textValue = inputLineValue.value;
                if (questionType === "date") {
                    textValue = formatDate(deserializeDate(textValue));
                } else if (questionType === "datetime") {
                    textValue = formatDateTime(deserializeDateTime(textValue));
                }
                const textAnswerEl = renderToElement(
                    "survey.survey_session_text_answer",
                    {
                        value: textValue,
                        borderColor: `rgb(${getPaletteColor(this.answerIds.length, SESSION_CHART_COLORS.slice(0, 10))})`,
                    },
                );
                this.insert(textAnswerEl, this.el);
                const spanWidth = textAnswerEl.querySelector("span").offsetWidth;
                const containerEl = textAnswerEl.querySelector(
                    ".o_survey_session_text_answer_container",
                );
                textAnswerEl.style.width = `calc(${spanWidth}px + 1.2rem)`;
                containerEl.style.width = `calc(${spanWidth}px + 1.2rem)`;
                containerEl.style.opacity = "1";
                this.answerIds.push(inputLineValue.id);
            }
        });
    }
}

registry
    .category("public.interactions")
    .add("survey.survey_session_text_answers", SurveySessionTextAnswers);
