/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { url } from "@web/core/utils/urls";

/**
 * Displays general information (avatar, name, etc.) about the contact
 * associated with the given call.
 */
export class ContactInfo extends Component {
    static props = {
        contact: t.or([t.object(), t.boolean()]).optional(),
        phoneNumber: t.string().optional(),
        extraClass: t.string().optional(""),
    };
    static template = "voip.ContactInfo";
    props = useProps(this.constructor.props);

    /** @returns {string} */
    get avatarAlt() {
        if (!this.contact) {
            return _t("Default profile picture");
        }
        return _t("Profile picture of %(user)s", { user: this.contact.name });
    }

    /** @returns {string} */
    get avatarUrl() {
        if (!this.contact) {
            return "/base/static/img/avatar_grey.png";
        }
        return url("/web/image", {
            model: "res.partner",
            id: this.contact.id,
            field: "avatar_128",
        });
    }

    /** @returns {import("models").ResPartner} */
    get contact() {
        return this.props.contact;
    }

    /** @returns {string} */
    get contactInfo() {
        if (!this.contact) {
            return ""; // TODO
        }
        const info = [];
        if (this.contact.commercial_company_name) {
            info.push(this.contact.commercial_company_name);
        }
        // ⚠ French: function = job position
        if (this.contact.function) {
            info.push(this.contact.function);
        }
        return info.join(", ");
    }

    /** @returns {string} */
    get contactName() {
        return this.contact?.voipName || this.props.phoneNumber;
    }
}
