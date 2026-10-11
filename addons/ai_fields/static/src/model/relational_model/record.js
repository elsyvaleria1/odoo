/** @odoo-module native */
import { markup } from "@odoo/owl";
import { x2ManyCommands } from "@web/core/network";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";
import { RelationalRecord } from "@web/model/relational_model";

const notificationTitles = [
    _t("I couldn't quite make sense of that"),
    _t("Hmm... that was a bit fuzzy for me"),
    _t("Missing a few pieces of the puzzle"),
    _t("I gave it a shot, but came up empty"),
    _t("My circuits didn't quite get it"),
    _t("I couldn't connect the dots"),
    _t("That was a bit over my head"),
    _t("Felt like a riddle I couldn’t solve"),
];

function getRandomToasterTitle() {
    const index = Math.floor(Math.random() * notificationTitles.length);
    return notificationTitles[index];
}

patch(RelationalRecord.prototype, {
    computeAiField(fieldName) {
        return this.model.mutex.exec(() => this._computeAiField(fieldName));
    },

    computeAiProperty(fullName) {
        return this.model.mutex.exec(() => this._computeAiProperty(fullName));
    },

    async _computeAiField(fieldName) {
        const field = this.fields[fieldName];
        if (!field?.ai) {
            throw new Error("Cannot compute a non-AI field using AI");
        }
        let value;
        try {
            value = await this.model.orm.call(this.resModel, "get_ai_field_value", [
                this.resId || [],
                fieldName,
                this.getChangesLocked(),
            ]);
        } catch (e) {
            if (e.exceptionName === "odoo.addons.ai_fields.tools.UnresolvedQuery") {
                this.model.viewContext.services.notification.add(e.data.message, {
                    autocloseDelay: 7000,
                    title: `🤖 ${getRandomToasterTitle()}`,
                    type: "warning",
                });
                value = field.type === "many2many" && [x2ManyCommands.set([])];
            } else {
                throw e;
            }
        }
        if (field.type === "many2many") {
            await this.updateLocked({ [fieldName]: value });
            return;
        }
        await this.updateLocked(
            this.parseServerValues(
                { [fieldName]: value },
                { currentValues: this.data },
            ),
        );
    },

    async _computeAiProperty(fullName) {
        const property = this.fields[fullName];
        if (!property?.ai) {
            throw new Error("Cannot compute a non-AI property using AI");
        }
        let value;
        try {
            value = await this.model.orm.call(this.resModel, "get_ai_property_value", [
                this.resId || [],
                fullName,
                this.getChangesLocked(),
            ]);
        } catch (e) {
            if (e.exceptionName === "odoo.addons.ai_fields.tools.UnresolvedQuery") {
                this.model.viewContext.services.notification.add(e.data.message, {
                    autocloseDelay: 7000,
                    title: `🤖 ${getRandomToasterTitle()}`,
                    type: "warning",
                });
                return false;
            }
            throw e;
        }
        if (property.type === "html") {
            return markup(value);
        }
        return value;
    },
});
