/** @odoo-module native */
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { useCarousel } from "@web/ui/carousel/carousel_hook";
import { standardActionServiceProps } from "@web/webclient/actions";

export class HrReferralWelcome extends Component {
    static template = "hr_referral.Welcome";
    static props = { ...standardActionServiceProps };
    static path = "referrals";
    props = useProps(this.constructor.props);

    setup() {
        super.setup();

        this.actionService = useService("action");
        this.orm = useService("orm");

        this.dashboardData = proxy({});

        this.isDebug = odoo.debug;

        this.carousel = useCarousel({
            count: () => this.onboardingLength || 0,
            wrap: false,
        });

        onWillStart(async () => {
            Object.assign(
                this.dashboardData,
                await this.orm.call("hr.applicant", "acquire_referral_welcome_screen"),
            );
            this.dashboardData.company_id = user.activeCompany.id;
        });
    }

    get reachedEnd() {
        return this.carousel.atEnd;
    }

    get onboardingLength() {
        return this.dashboardData.onboarding && this.dashboardData.onboarding.length;
    }

    get applicantId() {
        return this.dashboardData.new_friend_id;
    }

    /**
     * @private
     * @param {MouseEvent} e
     */
    async _onMessageDismissClicked(event, message_id) {
        await this.orm.call("hr.referral.alert", "action_dismiss", [message_id]);
        this.dashboardData.message = this.dashboardData.message.filter(
            (message) => message.id !== message_id,
        );
    }

    /**
     * Save that user has seen the onboarding screen then restart the view
     *
     * @private
     * @param {MouseEvent} e
     */
    async _completeOnboarding(completed) {
        await this.orm.call("res.users", "action_complete_onboarding", [completed]);
        this.actionService.doAction(
            {
                type: "ir.actions.client",
                tag: "hr_referral_welcome",
                name: _t("Dashboard"),
                target: "main",
            },
            { noEmptyTransition: true },
        );
    }

    /**
     * User upgrade his level then restart the view
     *
     * @private
     */
    async _upgradeLevel() {
        await this.orm.call("hr.applicant", "upgrade_level", []);
        this.actionService.doAction(
            {
                type: "ir.actions.client",
                tag: "hr_referral_welcome",
                name: _t("Dashboard"),
                target: "main",
            },
            { noEmptyTransition: true },
        );
    }

    /**
     * Save the new user's friend then restart the view
     *
     * @private
     * @param {MouseEvent} e
     */
    async _chooseFriend(friendId) {
        await this.orm.call("hr.applicant", "choose_a_friend", [
            [this.applicantId],
            friendId,
        ]);
        this.actionService.doAction(
            {
                type: "ir.actions.client",
                tag: "hr_referral_welcome",
                name: _t("Dashboard"),
                target: "main",
            },
            { noEmptyTransition: true },
        );
    }
}

registry.category("actions").add("hr_referral_welcome", HrReferralWelcome);
