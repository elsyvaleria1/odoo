/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import {
    Configurator,
    ROUTES,
    SkipButton,
} from "@website/client_actions/configurator/configurator";
import { WEBSITE_GENERATOR_ROUTE } from "@website_enterprise/client_actions/configurator/configurator";

ROUTES.websiteGenerator = WEBSITE_GENERATOR_ROUTE;

export class WebsiteGeneratorScreen extends Component {
    static components = { SkipButton };
    static template = "website_generator.Configurator.WebsiteGeneratorScreen";
    static props = { navigate: t.function(), skip: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.ui = useService("ui");
        this.state = proxy({
            isValidatingUrl: false,
            isValidUrl: false,
            url: "",
            submitted: false,
        });
    }

    async checkUrl() {
        this.state.isValidatingUrl = true;
        this.state.submitted = true;
        const result = await this.orm
            .call("website", "url_check", [this.state.url], {})
            .catch(() => null);
        if (result?.status === "success") {
            this.state.isValidatingUrl = false;
            this.state.isValidUrl = true;
            return true;
        }
        switch (result?.status) {
            case "error_invalid_url":
                this.notification.add("Please check your URL and try again.", {
                    title: _t("The provided URL is not reachable"),
                    type: "danger",
                });
                break;
            case "error_banned_url":
                this.notification.add("We can't process your request.", {
                    title: _t("The provided URL is not allowed"),
                    type: "danger",
                });
                break;
            case "error_allowed_request_exhausted":
                this.notification.add(
                    "You have exceeded the number of requests, try again later.",
                    {
                        title: _t("Too many requests"),
                        type: "danger",
                    },
                );
                break;
            case "error_url_redirection":
                this.notification.add(
                    "The requested URL redirected to another URL, try again with the final URL.",
                    {
                        title: _t("URL redirection"),
                        type: "danger",
                    },
                );
                break;
            default:
                this.notification.add("Something went wrong.", {
                    title: _t("Error"),
                });
                break;
        }
        this.state.isValidatingUrl = false;
        this.state.isValidUrl = false;
        return false;
    }

    async onUrlInput(ev) {
        this.state.url = ev.target.value;
        this.state.submitted = false;
    }

    async makeWebsiteGeneratorRequest(ev) {
        ev.preventDefault();
        const formData = new FormData(ev.currentTarget);
        const data = Object.fromEntries(formData.entries());
        this.ui.block();
        if (!(await this.checkUrl())) {
            this.ui.unblock();
            return;
        }
        let result;
        try {
            result = await this.orm.call("website", "import_website", [], data);
        } finally {
            if (!result) {
                this.ui.unblock();
            }
        }

        if (result) {
            this.action.doAction({
                type: "ir.actions.act_url",
                url: "/odoo/action-website_generator.website_generator_screen?reload=true",
                target: "self",
            });
        } else {
            this.notification.add(result, {
                title: _t("Something went wrong while importing your website."),
            });
        }
    }
}

patch(Configurator, {
    components: {
        ...Configurator.components,
        WebsiteGeneratorScreen,
    },
});

patch(Configurator.prototype, {
    get currentComponent() {
        if (this.state.currentStep === ROUTES.websiteGenerator) {
            return WebsiteGeneratorScreen;
        }
        return super.currentComponent;
    },
});
