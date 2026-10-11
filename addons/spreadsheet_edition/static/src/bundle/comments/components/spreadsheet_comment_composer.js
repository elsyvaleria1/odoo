/** @odoo-module native */
import { Composer } from "@mail/core/common/composer";

export class SpreadsheetCommentComposer extends Composer {
    constructor(...args) {
        super(...args);
    }
    /**
     * @override
     */
    async _sendMessage(value, postData) {
        await this.props.onPostCallback(value, postData);
        this.props.composer.clear();
        return;
    }
}
