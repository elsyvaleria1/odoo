/** @odoo-module native */
import { Thread } from "@mail/core/common/thread";
import { useMailContext } from "@mail/utils/common/mail_context";
import { t } from "@odoo/owl";

import { AccountReportMessage } from "./message.js";

export class AccountReportThread extends Thread {
    static template = "account.Thread";
    static props = { ...Thread.props, reportController: t.any().optional() };
    static components = { ...Thread.components, Message: AccountReportMessage };

    setup() {
        super.setup();
        this.mailContext = useMailContext();
    }
}
