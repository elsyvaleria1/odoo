/** @odoo-module native */
import { Composer } from "@mail/core/common/composer";
import { t } from "@odoo/owl";
import { parseISO, serializeDate } from "@web/core/l10n/dates";

export class AccountReportComposer extends Composer {
    static props = {
        ...Composer.props,
        reportController: t.any().optional(),
        date_to: t.any(),
        list: t.any().optional(),
    };

    get postData() {
        return {
            ...super.postData,
            account_reports_annotation_date: serializeDate(
                parseISO(this.props.date_to),
            ),
        };
    }

    async _sendMessage(value, postData, extraData) {
        const message = await super._sendMessage(value, postData, extraData);
        this.props.reportController?.addAnnotation(
            message.id,
            message.model,
            message.res_id,
            message.body,
        );
        this.props.list?.records.forEach((record) => {
            if (record.isInEdition) {
                record.load();
            }
            return record;
        });
        return message;
    }

    get fullComposerAdditionalContext() {
        return {
            ...super.fullComposerAdditionalContext,
            default_account_reports_annotation_date: serializeDate(
                parseISO(this.props.date_to),
            ),
        };
    }
}
