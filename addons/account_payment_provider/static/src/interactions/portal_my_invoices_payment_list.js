/** @odoo-module native */
import { deserializeDateTime, diff, today } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { Interaction } from "@web/public/interaction";

export class PortalMyInvoicesPaymentList extends Interaction {
    static selector = ".o_portal_my_doc_table";

    start() {
        const startOfToday = today();
        const dueDateEls = this.el.querySelectorAll(".o_portal_invoice_due_date");
        for (const dueDateEl of dueDateEls) {
            const dateTime = deserializeDateTime(
                dueDateEl.getAttribute("datetime"),
            ).startOfDay();
            const days = diff(dateTime, startOfToday, "days");

            const dueDateLabel =
                days === 0
                    ? _t("due today")
                    : days > 0
                      ? _t("due in %s day(s)", Math.abs(days).toFixed())
                      : _t("%s day(s) overdue", Math.abs(days).toFixed());

            // We use `.createTextNode()` to escape possible HTML in translations (XSS)
            dueDateEl.replaceChildren(document.createTextNode(dueDateLabel));
        }
    }
}

registry
    .category("public.interactions")
    .add(
        "account_payment.portal_my_invoices_payment_list",
        PortalMyInvoicesPaymentList,
    );
