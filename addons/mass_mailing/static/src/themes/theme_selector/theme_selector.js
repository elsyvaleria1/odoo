/** @odoo-module native */
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ThemeSelector extends Component {
    static template = "mass_mailing.ThemeSelector";
    static props = { config: t.object() };
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.themeService = useService("mass_mailing.themes");
        this.config = this.props.config;
        this.themes = this.themeService.getThemes();
        this.savedTemplates = proxy([]);
        onWillStart(async () => {
            const themeServicePromise = this.themeService.load();
            const savedPromise = this.orm.call(
                "mailing.mailing",
                "action_fetch_templates",
                [this.savedTemplateDomain],
            );
            const [savedTemplates] = await Promise.all([
                savedPromise,
                themeServicePromise,
            ]);
            Object.assign(
                this.savedTemplates,
                savedTemplates.map((saved) => ({
                    html: saved.body_arch,
                    id: saved.id,
                    modelId: saved.mailing_model_id[0],
                    modelName: saved.mailing_model_id[1],
                    name: `template_${saved.id}`,
                    nowrap: true,
                    subject: saved.subject,
                    userId: saved.user_id[0],
                    userName: saved.user_id[1],
                })),
            );
        });
    }

    get savedTemplateDomain() {
        return this.props.config.filterTemplates
            ? [["mailing_model_id", "=", this.props.config.mailingModelId]]
            : [];
    }

    async onRemoveSavedTemplate(index) {
        const saved = this.savedTemplates[index];
        if (!saved) {
            return;
        }
        const notificationAction = await this.orm.call(
            "mailing.mailing",
            "action_remove_from_templates",
            [saved.id],
        );
        this.savedTemplates.splice(index, 1);
        this.action.doAction(notificationAction);
    }

    onSelectSavedTemplate(html) {
        this.props.config.setThemeHTML(html);
    }

    onSelectTheme(themeOptions) {
        this.props.config.setThemeHTML(themeOptions.html);
    }
}
