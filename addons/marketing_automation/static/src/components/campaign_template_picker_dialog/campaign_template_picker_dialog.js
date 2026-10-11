/** @odoo-module native */
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { Notebook } from "@web/components/notebook";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";

export class CampaignTemplatePickerDialog extends Component {
    static template = "marketing_automation.CampaignTemplatePickerDialog";
    static components = {
        Dialog,
        Notebook,
    };
    static props = { close: t.function().optional() };
    props = useProps(this.constructor.props);
    /**
     * @override
     */
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
        this.activeTemplate = proxy({});

        this.notebookPages = [];

        onWillStart(async () => {
            const templateGroups = await this.orm.call(
                "marketing.campaign",
                "get_campaign_templates_info",
                [],
            );

            const firstGroup = Object.keys(templateGroups)[0];
            this.setActive(Object.keys(templateGroups[firstGroup].templates)[0]);

            for (const [groupId, groupValues] of Object.entries(templateGroups)) {
                this.notebookPages.push({
                    Component: CampaignTemplatePickerSheet,
                    id: groupId,
                    props: {
                        activeTemplate: this.activeTemplate,
                        setActive: (arg) => this.setActive(arg),
                        templates: groupValues.templates,
                    },
                    title: groupValues.label,
                });
            }
        });
    }

    async onLoadTemplate() {
        const action = await this.orm.call(
            "marketing.campaign",
            "get_action_marketing_campaign_from_template",
            [this.activeTemplate.name],
        );
        if (!action) {
            return;
        }
        this.action.doAction(action);
        this.props.close();
    }

    setActive(templateName) {
        this.activeTemplate.name = templateName;
    }
}

class CampaignTemplatePickerSheet extends Component {
    static template = "marketing_automation.CampaignTemplatePickerDialogSheet";
    static props = {
        activeTemplate: t.object(),
        setActive: t.function(),
        templates: t.object(),
    };
    props = useProps(this.constructor.props);
}
