// @ts-check
/** @odoo-module native */
import { Component, onMounted, onPatched, status, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useEventBus, useMountedListener, useService } from "@web/core/utils/hooks";
/**
 * @typedef {Object} Props
 * @property {"camera" | "screen"} type
 * @property {import("models").RtcSession} session
 * @extends {Component<Props, import("@web/env").OdooEnv>}
 */
export class CallParticipantVideo extends Component {
    static props = { session: t.any(), type: t.any(), inset: t.any().optional() };
    static template = "discuss.CallParticipantVideo";
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.bus = useEventBus();
        this.rtc = useService("discuss.rtc");
        this.store = useService("mail.store");
        this.root = /** @type {import("@odoo/owl").Ref<HTMLVideoElement>} */ (
            elementRef()
        );
        onMounted(() => this._update());
        onPatched(() => this._update());
        useMountedListener(this.bus, "RTC-SERVICE:PLAY_MEDIA", async () => {
            await this.play();
        });
    }

    _update() {
        if (!this.root.el) {
            return;
        }
        const stream = this.props.session?.getStream(this.props.type);
        const srcObject = stream || null;
        if (this.root.el.srcObject === srcObject) {
            return;
        }
        this.root.el.srcObject = srcObject;
        this.root.el.load();
    }

    async play() {
        try {
            await this.root.el?.play?.();
            this.props.session.videoError = undefined;
        } catch (error) {
            if (status(this) === "destroyed") {
                return;
            }
            this.props.session.videoError = error.name;
        }
    }

    async onVideoLoadedMetaData() {
        await this.play();
    }
}
