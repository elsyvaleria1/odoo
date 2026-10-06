/** @odoo-module native */
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { isValidEmail } from "@point_of_sale/utils";
import { useSelfOrder } from "@pos_self_order/app/services/self_order_service";
import { deserializeDate, formatValue, serializeDateTime } from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { rpc } from "@web/core/network";
import { useService } from "@web/core/utils/hooks";
export class PresetInfoPopup extends Component {
    static template = "pos_self_order.PresetInfoPopup";
    static props = { callback: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.notification = useService("notification");
        this.selfOrder = useSelfOrder();
        this.state = proxy({
            selectedSlot: null,
            selectedPartnerId: null,
            name: "",
            email: "",
            phone: "",
            phoneError: "",
            street: "",
            countryId: this.selfOrder.config.company_id.country_id.id,
            stateId:
                this.selfOrder.config.company_id.country_id.state_ids[0]?.id || null,
            city: "",
            zip: "",
        });

        onWillStart(async () => {
            await this.selfOrder.syncPresetSlotAvaibility(this.preset);
        });
    }

    async setInformations() {
        if (!this.checkPhoneFormat()) {
            return;
        }

        if (this.preset.needsPartner || this.state.phone) {
            const result = await rpc(`/pos-self-order/validate-partner`, {
                access_token: this.selfOrder.access_token,
                partner_id: this.state.selectedPartnerId,
                name: this.state.name,
                email: this.state.email,
                phone: this.state.phone,
                street: this.state.street,
                city: this.state.city,
                country_id: this.state.countryId,
                state_id: this.state.stateId,
                zip: this.state.zip,
            });
            const partner = this.selfOrder.models.connectNewData(result);
            this.selfOrder.currentOrder.floating_order_name = `${this.preset.name} - ${partner["res.partner"][0].name}`;
            this.selfOrder.currentOrder.partner_id = partner["res.partner"][0];
        } else {
            this.selfOrder.currentOrder.floating_order_name = this.state.name;
        }

        if (this.preset.needsSlot && this.state.selectedSlot) {
            this.selfOrder.currentOrder.preset_time = this.state.selectedSlot;
        }

        this.props.callback(this.state);
    }

    selectExistingPartner(event) {
        const partner = this.selfOrder.models["res.partner"].get(event.target.value);
        this.state.name = partner?.name || "";
        this.state.email = partner?.email || "";
        this.state.phone = partner?.phone || "";
        this.state.street = partner?.street || "";
        this.state.city = partner?.city || "";
        this.state.countryId = partner?.country_id?.id || null;
        this.state.stateId = partner?.state_id?.id || null;
        this.state.zip = partner?.zip || "";
    }

    get existingPartners() {
        return this.selfOrder.models["res.partner"].getAll();
    }

    get partnerIsSelected() {
        return this.state.selectedPartnerId && this.state.selectedPartnerId !== "0";
    }

    close() {
        this.props.callback(false);
    }

    get preset() {
        return this.selfOrder.currentOrder.preset_id;
    }

    get slots() {
        return Object.entries(this.preset.upcomingAvailabilities).filter(
            (s) => Object.keys(s[1]).length > 0,
        );
    }

    get countries() {
        return this.selfOrder.models["res.country"].getAll();
    }

    get states() {
        const country = this.selfOrder.models["res.country"].get(this.state.countryId);
        return country?.state_ids || [];
    }

    get validSelection() {
        const partnerInfo =
            this.state.name &&
            this.state.phone &&
            this.state.street &&
            this.state.city &&
            this.state.countryId &&
            (this.state.stateId || !this.states.length) &&
            this.state.zip;
        return (
            (!this.preset.needsSlot || Boolean(this.state.selectedSlot)) &&
            (!this.preset.needsName || this.state.name) &&
            (!this.preset.needsEmail || isValidEmail(this.state.email)) &&
            (!this.preset.needsPartner || partnerInfo) &&
            this.checkPhoneFormat()
        );
    }

    formatDate(date) {
        return formatValue(deserializeDate(date), localization.dateFormat);
    }

    slotValue(datetime) {
        return serializeDateTime(datetime);
    }

    formatSlot(datetime, format) {
        return formatValue(datetime, format);
    }

    checkPhoneFormat() {
        if (!this.state.phone) {
            return true;
        }
        const phone = this.state.phone.replace(/[\s.\-()]/g, "");
        const pattern = /^\+\d{8,18}$/;
        return pattern.test(phone);
    }
}
