/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { standardWidgetProps } from "@web/views/widgets";

export class SurveyQuestionTriggerWidget extends Component {
    static template = "survey.surveyQuestionTrigger";
    static props = { ...standardWidgetProps };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.lastTrigger = { warning: false, tooltip: "" };
    }

    get trigger() {
        if (!this.props.record.data.triggering_question_ids.records.length) {
            return (this.lastTrigger = { warning: false, tooltip: "" });
        }
        const { triggerError, misplacedTriggerQuestionRecords } =
            this.surveyQuestionTriggerError;
        if (triggerError === "MISPLACED_TRIGGER_WARNING") {
            this.lastTrigger = {
                warning: true,
                tooltip:
                    "⚠ " +
                    _t(
                        'Triggers based on the following questions will not work because they are positioned after this question:\n"%s".',
                        misplacedTriggerQuestionRecords
                            .map((question) => question.data.title)
                            .join('", "'),
                    ),
            };
        } else if (triggerError === "WRONG_QUESTIONS_SELECTION_WARNING") {
            this.lastTrigger = {
                warning: true,
                tooltip:
                    "⚠ " +
                    _t(
                        "Conditional display is not available when questions are randomly picked.",
                    ),
            };
        } else if (triggerError !== "MISSING_TRIGGER_ERROR") {
            this.lastTrigger = {
                warning: false,
                tooltip: _t(
                    'Displayed if "%s".',
                    this.props.record.data.triggering_answer_ids.records
                        .map((answer) => answer.data.display_name)
                        .join('", "'),
                ),
            };
        }
        return this.lastTrigger;
    }

    /** @returns {{ triggerError: String, misplacedTriggerQuestionRecords: Record[] }} */
    get surveyQuestionTriggerError() {
        const record = this.props.record;
        if (!record.data.triggering_question_ids.records.length) {
            return { triggerError: "", misplacedTriggerQuestionRecords: [] };
        }
        if (this.props.record.data.questions_selection === "random") {
            return {
                triggerError: "WRONG_QUESTIONS_SELECTION_WARNING",
                misplacedTriggerQuestionRecords: [],
            };
        }

        const missingTriggerQuestionsIds = [];
        const triggerQuestionsRecords = [];
        for (const triggeringQuestion of record.data.triggering_question_ids.records) {
            const triggeringQuestionRecord =
                record.model.root.data.question_and_page_ids.records.find(
                    (rec) => rec.resId === triggeringQuestion.resId,
                );
            if (triggeringQuestionRecord) {
                triggerQuestionsRecords.push(triggeringQuestionRecord);
            } else {
                missingTriggerQuestionsIds.push(triggeringQuestion.resId);
            }
        }

        if (
            missingTriggerQuestionsIds.length ===
            this.props.record.data.triggering_question_ids.records.length
        ) {
            return {
                triggerError: "MISSING_TRIGGER_ERROR",
                misplacedTriggerQuestionRecords: [],
            };
        }
        const misplacedTriggerQuestionRecords = [];
        for (const triggerQuestionRecord of triggerQuestionsRecords) {
            if (
                record.data.sequence < triggerQuestionRecord.data.sequence ||
                (record.data.sequence === triggerQuestionRecord.data.sequence &&
                    record.resId < triggerQuestionRecord.resId)
            ) {
                misplacedTriggerQuestionRecords.push(triggerQuestionRecord);
            }
        }
        return {
            triggerError: misplacedTriggerQuestionRecords.length
                ? "MISPLACED_TRIGGER_WARNING"
                : "",
            misplacedTriggerQuestionRecords: misplacedTriggerQuestionRecords,
        };
    }
}

export const surveyQuestionTriggerWidget = {
    component: SurveyQuestionTriggerWidget,
    fieldDependencies: [
        { name: "triggering_question_ids", type: "many2many" },
        { name: "triggering_answer_ids", type: "many2many" },
    ],
};
registry
    .category("view_widgets")
    .add("survey_question_trigger", surveyQuestionTriggerWidget);
