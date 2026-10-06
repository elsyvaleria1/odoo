// @ts-check
/** @odoo-module native */

import { Component, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useWebContext } from "@web/core/web_context_hooks";
import { isCompanyAllowed } from "@web/webclient/switch_company_menu/company_selector";

export class SwitchCompanyItem extends Component {
    static template = "web.SwitchCompanyItem";
    static props = { company: t.any(), level: t.number() };
    props = useProps(this.constructor.props);

    setup() {
        this.webContext = useWebContext();
        this.companySelector = proxy(this.webContext.companySelector);
    }

    /** @returns {boolean} */
    get isCompanySelected() {
        return this.companySelector.isCompanySelected(this.props.company.id);
    }

    /** @returns {boolean} */
    get isCompanyAllowed() {
        return isCompanyAllowed(this.props.company.id);
    }

    /** @returns {boolean} */
    get isCurrent() {
        return this.props.company.id === user.activeCompany.id;
    }

    /** @returns {string} */
    get toggleTitle() {
        return this.isCompanySelected
            ? _t("Hide %s content.", this.props.company.name)
            : _t("Show %s content.", this.props.company.name);
    }

    /** @returns {string} */
    get logIntoTitle() {
        return _t("Switch to %s", this.props.company.name);
    }

    logIntoCompany() {
        if (this.isCompanyAllowed) {
            this.companySelector.switchCompany("loginto", this.props.company.id);
        }
    }

    toggleCompany() {
        if (this.isCompanyAllowed) {
            this.companySelector.switchCompany("toggle", this.props.company.id);
        }
    }
}
