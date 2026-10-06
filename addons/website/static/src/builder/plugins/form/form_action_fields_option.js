/** @odoo-module native */
import { useBuilderContext } from "@html_builder/core/builder_context";
import { BaseOptionComponent } from "@html_builder/core/utils";
import { onWillStart, onWillUpdateProps, proxy, t } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";

const log = makeLogger("website.builder.option.form_action_fields_option");

export class FormActionFieldsOption extends BaseOptionComponent {
    static template = "website.s_website_form_form_action_fields_option";
    static dependencies = ["websiteFormOption"];
    static props = { activeForm: t.object().optional() };

    setup() {
        super.setup();
        this.builderContext = useBuilderContext();
        useLifecycleLog(log);
        this.prepareFormModel = this.dependencies.websiteFormOption.prepareFormModel;
        this.state = proxy({
            formInfo: {
                fields: [],
            },
        });
        onWillStart(() => this.getFormInfo());
        onWillUpdateProps(this.getFormInfo.bind(this));
    }
    async getFormInfo(props = this.props) {
        const el = this.builderContext.getEditingElement();
        const endFormInfo = log.perf("getFormInfo", () => ({
            model: props.activeForm?.model,
        }));
        const formInfo = await this.prepareFormModel(el, props.activeForm);
        endFormInfo(() => ({ hasFormInfo: !!formInfo }));
        Object.assign(
            this.state.formInfo,
            {
                fields: [],
                formFields: [],
                successPage: undefined,
            },
            formInfo,
        );
    }
}
