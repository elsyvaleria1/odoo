/** @odoo-module native */
import { WebChatter } from "@mail/chatter/web/web_chatter";
import { t } from "@odoo/owl";

import { AccountReportComposer } from "./composer.js";
import { AccountReportThread } from "./thread.js";

export class AccountReportChatter extends WebChatter {
    static template = "account.Chatter";
    static props = {
        ...WebChatter.props,
        reportController: t.any().optional(),
        date_to: t.any(),
        list: t.any().optional(),
    };
    static components = {
        ...WebChatter.components,
        Composer: AccountReportComposer,
        Thread: AccountReportThread,
    };
}
