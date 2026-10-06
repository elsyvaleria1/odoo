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
            // MISSING_TRIGGER_ERROR keeps the previous state: the trigger itself goes at the
            // next save, and showing the "normal" icon until then would flicker.
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

    /**
     * `surveyQuestionTriggerError` is computed here and does not rely on
     * record data (is_placed_before_trigger) for two linked reasons:
     * 1. Performance: we avoid saving the survey each time a line is moved.
     * 2. Robustness, as sequences values do not always match between server
     * provided values when the records are not saved.
     *
     * @returns {{ triggerError: String, misplacedTriggerQuestionRecords: Record[] }}
     *   * `""`: No trigger error (also if `triggering_question_id`
     *     field is not set).
     *   * `"MISSING_TRIGGER_ERROR"`: `triggering_questions_ids` field is set
     *     but trigger record is not found. This can happen if all questions
     *     used as triggers are deleted on the client but not yet saved to DB.
     *   * `"MISPLACED_TRIGGER_WARNING"`: a `triggering_question_id` is set
     *     but is positioned after the current record in the list. This can
     *     happen if the triggering or the triggered question is moved.
     *   * `"WRONG_QUESTIONS_SELECTION_WARNING"`: a `triggering_question_id`
     *     is set but the survey is configured to randomize questions asked
     *     mode which ignores the triggers. This can happen if the survey mode
     *     is changed after triggers are set.
     */
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
                // Trigger question was deleted from the list
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
            }; // only if all are missing
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
        // Both are Many2many on survey.question. Declaring them as many2one
        // makes addFieldDependencies skip the `related` sub-schema, and a
        // dependency-first arch then loads them with no specification at all.
        { name: "triggering_question_ids", type: "many2many" },
        { name: "triggering_answer_ids", type: "many2many" },
    ],
};
registry
    .category("view_widgets")
    .add("survey_question_trigger", surveyQuestionTriggerWidget);
