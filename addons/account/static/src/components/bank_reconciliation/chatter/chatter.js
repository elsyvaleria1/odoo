/** @odoo-module native */
import { WebChatter } from "@mail/chatter/web/web_chatter";
import { t } from "@odoo/owl";

export class BankRecChatter extends WebChatter {
    static props = { ...WebChatter.props, statementLine: t.any().optional() };

    async reloadParentView() {
        await this.props.statementLine?.load();
    }
}
