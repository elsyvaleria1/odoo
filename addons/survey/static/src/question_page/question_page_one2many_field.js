/** @odoo-module native */
import { provideSurveyContext } from "@survey/question_page/survey_context";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { X2ManyField, x2ManyField } from "@web/fields/relational/x2many";
import { useX2ManyCrud } from "@web/fields/relational/x2many_crud";
import { useOpenX2ManyRecord } from "@web/fields/relational/x2many_dialog";

import { QuestionPageListRenderer } from "./question_page_list_renderer.js";

class SurveySaveError extends Error {}
function SurveySaveErrorHandler(env, error, originalError) {
    if (originalError instanceof SurveySaveError) {
        env.services.notification.add(originalError.message, {
            title: _t("Validation Error"),
            type: "danger",
        });
        return true;
    }
}
registry
    .category("error_handlers")
    .add("surveySaveErrorHandler", SurveySaveErrorHandler, { sequence: 10 });

class QuestionPageOneToManyField extends X2ManyField {
    static components = {
        ...X2ManyField.components,
        ListRenderer: QuestionPageListRenderer,
    };
    static props = {
        ...X2ManyField.props,
        editable: X2ManyField.props.editable.optional("bottom"),
    };
    setup() {
        super.setup();
        provideSurveyContext({
            openRecord: (record) => this.openRecord(record),
        });

        const { saveAndLink: superSaveAndLink, updateRecord: superUpdateRecord } =
            useX2ManyCrud(() => this.list, this.isMany2Many);

        const self = this;
        const saveRecord = async (record) => {
            await superSaveAndLink(record);
            try {
                await self.props.record.save();
            } catch (error) {
                await this.list.delete(record);
                throw new SurveySaveError(error?.data?.message ?? error.message);
            }
        };

        const updateRecord = async (record) => {
            await superUpdateRecord(record);
            try {
                await self.props.record.save();
            } catch (error) {
                throw new SurveySaveError(error?.data?.message ?? error.message);
            }
        };

        const openRecord = useOpenX2ManyRecord({
            resModel: this.list.resModel,
            activeField: this.activeField,
            activeActions: this.activeActions,
            getList: () => this.list,
            saveRecord,
            updateRecord,
        });
        this._openRecord = async (params) => {
            const { record, name } = this.props;
            if (!(await record.save())) {
                return;
            }
            if (params.record) {
                params.record = record.data[name].records.find(
                    (r) => r.resId === params.record.resId,
                );
            }
            await openRecord(params);
        };
        this.canOpenRecord = true;
    }
}

export const questionPageOneToManyField = {
    ...x2ManyField,
    component: QuestionPageOneToManyField,
    additionalClasses: [...(x2ManyField.additionalClasses || []), "o_field_one2many"],
};

registry.category("fields").add("question_page_one2many", questionPageOneToManyField);
