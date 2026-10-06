/** @odoo-module native */
import { Component, onWillStart, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { standardActionServiceProps } from "@web/webclient/actions";

export class AccountImportGuide extends Component {
    static template = "account_base_import.accountImportTemplate";
    static components = { ControlPanel };
    static props = { ...standardActionServiceProps };
    props = useProps(this.constructor.props);
    setup() {
        this.config = useViewConfig();
        this.actionService = useService("action");
        this.orm = useService("orm");
        this.config.setDisplayName(_t("Accounting Import Guide"));
        onWillStart(async () => {
            const current_company_id = user.activeCompany.id;
            this.data = await this.orm.searchRead(
                "res.company",
                [["id", "=", current_company_id]],
                ["country_code"],
            );
            this.isFecImportModuleInstalled = await this.orm.searchCount(
                "ir.module.module",
                [
                    ["name", "=", "l10n_fr_fec_import"],
                    ["state", "=", "installed"],
                ],
            );
        });
    }

    get countryCode() {
        return this.data[0].country_code;
    }

    get downloadAssetTemplateUrl() {
        const companyId = user?.activeCompany?.id;
        if (!companyId) {
            return "#";
        } // Fallback or disable the link
        return `/web/binary/download_asset_template/${companyId}`;
    }

    _importAccountGuideAction(action) {
        this.actionService.doAction(action);
    }

    _openModuleInstallation(module) {
        this.actionService.doAction({
            name: _t("Install a module"),
            res_model: "ir.module.module",
            type: "ir.actions.act_window",
            views: [
                [false, "kanban"],
                [false, "list"],
                [false, "form"],
            ],
            view_mode: "kanban,list,form",
            context: {
                search_default_name: module,
                search_default_extra: true,
            },
        });
    }
}

registry.category("actions").add("account_import_guide", AccountImportGuide);
