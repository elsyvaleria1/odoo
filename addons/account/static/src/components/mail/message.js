/** @odoo-module native */
import { Message } from "@mail/core/common/message";
import { t } from "@odoo/owl";

export class AccountReportMessage extends Message {
    static props = { ...Message.props, reportController: t.any().optional() };
}
