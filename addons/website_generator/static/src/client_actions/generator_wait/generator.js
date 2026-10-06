/** @odoo-module native */
import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    proxy,
    useProps,
} from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useBus, useService } from "@web/core/utils/hooks";
import { redirect } from "@web/core/utils/urls";
import { standardActionServiceProps } from "@web/webclient/actions";

class WebsiteGenerator extends Component {
    static template = "website_generator.WebsiteGenerator";
    static props = { ...standardActionServiceProps };
    props = useProps(this.constructor.props);
    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.website = useService("website");

        this.canCallGetResultWaitingRequests = true;
        this.state = proxy({
            error: "",
        });
        onWillStart(() => this._checkRequestStatus());
        onMounted(() => {
            this.interval = setInterval(() => this._checkRequestStatus(), 10000);
        });
        onWillUnmount(() => clearInterval(this.interval));

        useBus(this.website.bus, "HIDE-WEBSITE-LOADER", () => {
            if (!this.state.error) {
                redirect("/odoo?showWebsiteGeneratorNotification=1");
            }
        });
    }
    async _checkRequestStatus() {
        const [lastScrapRequest] = await this.orm.silent.searchRead(
            "website_generator.request",
            [],
            ["id", "status", "status_message", "website_id"],
            { limit: 1, order: "id DESC" },
        );
        if (!lastScrapRequest) {
            redirect("/odoo");
            return;
        }
        if (
            ["error_request_still_processing", "error_maintenance", "waiting"].includes(
                lastScrapRequest.status,
            )
        ) {
            if (this.canCallGetResultWaitingRequests) {
                this.canCallGetResultWaitingRequests = false;
                this.lastGetResultWaitingRequests = this.orm
                    .call("website_generator.request", "get_result_waiting_requests")
                    .then(() => {
                        this.canCallGetResultWaitingRequests = true;
                    });
            }
            this._showWebsiteLoader();
            return;
        }
        this.orm.silent.write("website_generator.request", [lastScrapRequest.id], {
            notified: true,
        });
        if (lastScrapRequest.status.includes("error")) {
            this.state.error = lastScrapRequest.status_message;
            clearInterval(this.interval);
            this.website.hideLoader();
            return;
        }

        this.website.prepareOutLoader();

        window.location.href = `/website/force/${lastScrapRequest.website_id[0]}`;
    }

    _showWebsiteLoader() {
        this.website.showLoader({
            title: _t("Importing your website."),
            bottomMessageTemplate:
                "website_generator.request_website_loader_bottom_message",
            showLoader: false,
            showCloseButton: true,
        });
    }
}

registry.category("actions").add("website_generator", WebsiteGenerator);
