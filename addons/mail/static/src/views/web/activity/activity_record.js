// @ts-check
/** @odoo-module native */
import { ActivityCompiler } from "@mail/views/web/activity/activity_compiler";
import { Component, t, useProps } from "@odoo/owl";
import * as dates from "@web/core/l10n/dates";
import { evaluateBooleanExpr } from "@web/core/py_js/py";
import { user } from "@web/core/user";
import { isHtmlEmpty } from "@web/core/utils/dom/html";
import { Field } from "@web/fields/field";
import { getFormattedRecord, getImageSrcFromRecordInfo } from "@web/views/kanban";
import { compileViewTemplates } from "@web/views/view_compiler";
export class ActivityRecord extends Component {
    static components = {
        Field,
    };
    static props = {
        archInfo: t.object(),
        openRecord: t.function(),
        record: t.object(),
    };
    static template = "mail.ActivityRecord";
    props = useProps(this.constructor.props);

    setup() {
        this.evaluateBooleanExpr = evaluateBooleanExpr;
        this.widget = {
            deletable: false,
            editable: false,
            isHtmlEmpty,
        };
        const { templateDocs } = this.props.archInfo;
        const templates = compileViewTemplates(ActivityCompiler, templateDocs);
        this.recordTemplate = templates["activity-box"];
    }

    getRenderingContext() {
        const { record } = this.props;
        return {
            record: getFormattedRecord(record),
            /** @param {...any} args */
            activity_image: (...args) => getImageSrcFromRecordInfo(record, ...args),
            user_context: user.context,
            widget: this.widget,
            dates,
            __comp__: Object.assign(Object.create(this), { this: this }),
        };
    }
}
