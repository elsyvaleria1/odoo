/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { cohortView } from "@web_cohort/cohort_view";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";
import {
    fieldsToChoices,
    InteractiveEditorSidebar,
    NewViewDialog,
    Property,
    SidebarViewToolbox,
    useEditNodeAttributes,
} from "@web_studio/editor";

export class CohortEditorSidebar extends Component {
    static template = "web_cohort_studio.CohortEditorSidebar";
    static props = {
        openViewInForm: t.function().optional(),
        openDefaultValues: t.function().optional(),
    };
    static components = {
        InteractiveEditorSidebar,
        Property,
        SidebarViewToolbox,
    };
    props = useProps(this.constructor.props);

    setup() {
        this.viewEditorModel = proxy(useCurrentViewEditorModel());
        this.editArchAttributes = useEditNodeAttributes({ isRoot: true });
    }

    onViewAttributeChanged(value, name) {
        value = value ? value : "";
        return this.editArchAttributes({ [name]: value });
    }

    get modelParams() {
        return this.viewEditorModel.controllerProps.modelParams;
    }

    get dateFields() {
        return fieldsToChoices(
            this.viewEditorModel.fields,
            ["date", "datetime"],
            (field) => field.store,
        );
    }

    get measureFields() {
        return fieldsToChoices(
            this.viewEditorModel.fields,
            ["integer", "float", "monetary"],
            (field) => field.name !== "id" && field.store && field.aggregator,
        );
    }

    get intervalChoices() {
        return [
            { label: _t("Day"), value: "day" },
            { label: _t("Week"), value: "week" },
            { label: _t("Month"), value: "month" },
            { label: _t("Quarter"), value: "quarter" },
            { label: _t("Year"), value: "year" },
        ];
    }

    get modeChoices() {
        return [
            { label: _t("Retention"), value: "retention" },
            { label: _t("Churn"), value: "churn" },
        ];
    }

    get timelineChoices() {
        return [
            { label: _t("Forward"), value: "forward" },
            { label: _t("Backwards"), value: "backward" },
        ];
    }
}

registry.category("studio_editors").add("cohort", {
    label: _t("Cohort"),
    icon: "oi oi-view-cohort",
    group: "reporting",
    newViewDialog: NewViewDialog,
    newViewMandatoryStopDate: true,
    ...cohortView,
    Sidebar: CohortEditorSidebar,
});
