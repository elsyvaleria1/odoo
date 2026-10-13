/** @odoo-module native */
import { Component, onMounted, proxy, t, useProps } from "@odoo/owl";
import { tabComponents } from "@voip/softphone/tab";
import { isSubstring, matchPhoneNumber } from "@voip/utils/utils";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";

/** @typedef {import("models").ResPartner} ResPartner */

export class AddressBook extends Component {
    static components = tabComponents;
    static props = {
        contactsFilter: t.function().optional(() => (contact) => true),
        extraClass: t.string().optional(""),
        onClickBack: t.function().optional(),
        slots: t.object().optional(),
    };
    static template = "voip.AddressBook";
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
        this.userAgent = useService("voip.user_agent");
        this.voip = useService("voip");
        this.ui = useService("ui");
        this.state = proxy(this.voip.softphone.addressBook);
        onMounted(() => this.voip.fetchContacts(this.state.searchInputValue));
        this.onInputSearch = useDebounced(
            () => this.voip.fetchContacts(this.state.searchInputValue),
            300,
        );
    }

    /** @returns {Map<string, Array<ResPartner>>} */
    get contactsByInitial() {
        const contacts = [...this.filteredContacts];
        const compareFn = new Intl.Collator(user.lang).compare;
        const getInitial = (contact) => [...contact.voipName][0]?.toUpperCase() || "#";
        contacts.sort((a, b) => {
            const initialA = getInitial(a);
            const initialB = getInitial(b);
            if (initialA === "#" && initialB !== "#") {
                return 1;
            }
            if (initialA !== "#" && initialB === "#") {
                return -1;
            }
            return compareFn(a.voipName, b.voipName);
        });
        return Map.groupBy(contacts, getInitial);
    }

    /** @returns {ResPartner[]} */
    get filteredContacts() {
        const contacts = this.voip.softphone.contacts.filter(this.props.contactsFilter);
        const searchTerms = this.state.searchInputValue;
        if (!searchTerms) {
            return contacts;
        }
        return contacts.filter(
            ({ voipName, phone }) =>
                isSubstring(voipName, searchTerms) ||
                matchPhoneNumber(phone, searchTerms),
        );
    }

    /**
     * @param {ResPartner} contact
     * @returns {string}
     */
    getSubtitle(contact) {
        if (contact.is_company) {
            return "";
        }
        const info = [];
        if (contact.commercial_company_name) {
            info.push(contact.commercial_company_name);
        }
        if (contact.function) {
            info.push(contact.function);
        }
        return info.join(" - ");
    }

    /** @param {ResPartner} contact */
    onClickActivity(contact) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_id: false,
            res_model: "mail.activity",
            views: [[false, "form"]],
            view_mode: "form",
            target: "new",
            context: {
                default_activity_type_id: this.voip.callActivityTypeId,
                default_res_id: contact.id,
                default_res_model: "res.partner",
            },
        });
    }

    /** @param {ResPartner} contact */
    onClickCall(contact) {
        this.userAgent.makeCall({ partner: contact, phone_number: contact.phone });
    }

    /** @param {ResPartner} contact */
    onClickContact(contact) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: contact.id,
            views: [[false, "form"]],
            target: this.ui.isSmall ? "new" : "current",
        });
    }

    openPartnerForm() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            views: [[false, "form"]],
            target: this.ui.isSmall ? "new" : "current",
        });
    }
}
