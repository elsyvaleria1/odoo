/** @odoo-module native */
import { Component, EventBus, markup, proxy, t, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { _t } from "@web/core/translation";
import { useBus } from "@web/core/utils/hooks";

const log = makeLogger("website.component.fullscreen_indication");

export class FullscreenIndication extends Component {
    static props = { bus: t.instanceOf(EventBus) };
    static template = "website.FullscreenIndication";
    props = useProps(this.constructor.props);

    setup() {
        useLifecycleLog(log);
        this.state = proxy({ isVisible: false });
        useBus(this.props.bus, "FULLSCREEN-INDICATION-SHOW", this.show.bind(this));
        useBus(this.props.bus, "FULLSCREEN-INDICATION-HIDE", this.hide.bind(this));
    }

    show() {
        log.lifecycle("show: autofade timer started");
        setTimeout(() => (this.state.isVisible = true));
        this.autofade = setTimeout(() => (this.state.isVisible = false), 2000);
    }

    hide() {
        if (this.state.isVisible) {
            log.lifecycle("hide: autofade timer cleared");
            this.state.isVisible = false;
            clearTimeout(this.autofade);
        }
    }

    get fullScreenIndicationText() {
        return _t("Press %(key)s to exit full screen", {
            key: markup`<span>esc</span>`,
        });
    }
}
