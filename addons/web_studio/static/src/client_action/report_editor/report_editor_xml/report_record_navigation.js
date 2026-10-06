/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { Pager } from "@web/components/pager";
import { RecordSelector } from "@web/components/record_selectors";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useStudioEditorContext } from "@web_studio/client_action/editor/studio_editor_context";

export class ReportRecordNavigation extends Component {
    static components = { RecordSelector, Pager };
    static template = "web_studio.ReportEditor.ReportRecordNavigation";
    static props = { onWillPrint: t.function().optional() };
    props = useProps(this.constructor.props);

    setup() {
        this.studioContext = useStudioEditorContext();
        this.reportEditorModel = proxy(this.studioContext.reportEditorModel);
        this.action = useService("action");
        this.notification = useService("notification");
    }

    get multiRecordSelectorProps() {
        const currentId = this.reportEditorModel.reportEnv.currentId;
        return {
            resModel: this.reportEditorModel.reportResModel,
            update: (resId) => {
                this.reportEditorModel.loadReportHtml({ resId });
            },
            resId: currentId,
            domain: this.reportEditorModel.getModelDomain(),
            context: { studio: false },
        };
    }

    get pagerProps() {
        const { reportEnv } = this.reportEditorModel;
        const { ids, currentId } = reportEnv;
        return {
            limit: 1,
            offset: ids.indexOf(currentId),
            total: ids.length,
        };
    }

    updatePager({ offset }) {
        const ids = this.reportEditorModel.reportEnv.ids;
        const resId = ids[offset];
        this.reportEditorModel.loadReportHtml({ resId });
    }

    async printPreview() {
        const model = this.reportEditorModel;
        await this.props.onWillPrint?.();
        const recordId =
            model.reportEnv.currentId || model.reportEnv.ids.find((i) => !!i) || false;
        if (!recordId) {
            this.notification.add(
                _t(
                    "There is no record on which this report can be previewed. Create at least one record to preview the report.",
                ),
                {
                    type: "danger",
                    title: _t("Report preview not available"),
                },
            );
            return;
        }

        const action = await rpc("/web_studio/print_report", {
            record_id: recordId,
            report_id: model.editedReportId,
        });
        this.reportEditorModel.renderKey++;
        return this.action.doAction(action, { clearBreadcrumbs: true });
    }
}
