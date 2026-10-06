// @ts-check
/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { Deferred, KeepLast } from "@web/core/utils/concurrency";
import { memoize } from "@web/core/utils/functions";
/**
 * @typedef {Object} Props
 * @property {string} src
 * @property {string} [alt]
 * @property {string} [class]
 * @property {string} [loading]
 * @property {((event: Event) => void)} [onLoad]
 * @property {((event: Event) => void)} [onClick]
 * @property {boolean} [paused]
 * @property {string} [style]
 * @extends {Component<Props, import("@web/env").OdooEnv>}
 */
export class Gif extends Component {
    static template = "mail.Gif";
    static props = {
        src: t.string(),
        alt: t.string().optional(),
        class: t.string().optional(),
        loading: t.string().optional(),
        onLoad: t.function().optional(),
        onClick: t.function().optional(),
        paused: t.boolean().optional(),
        style: t.string().optional(),
    };
    static components = {};
    props = useProps(this.constructor.props);

    generateGifSnapshot = memoize(
        /** @param {string} src */ async (src) => {
            const deferred = new Deferred();
            const image = document.createElement("img");
            if (new URL(src).origin !== location.origin) {
                image.crossOrigin = "anonymous";
            }
            image.src = src;
            image.onerror = () => {
                deferred.resolve(null);
            };
            image.onload = () => {
                const canvas = document.createElement("canvas");
                canvas.width = image.width;
                canvas.height = image.height;
                canvas
                    .getContext("2d")
                    .drawImage(image, 0, 0, image.width, image.height);
                deferred.resolve(canvas.toDataURL("image/gif"));
            };
            return deferred;
        },
    );

    setup() {
        this.state = proxy({ snapshot: null });
        this.keepLast = new KeepLast();
    }

    /** @param {Event} event */
    onLoad(event) {
        this.props.onLoad?.(event);
        this.keepLast
            .add(this.generateGifSnapshot(this.props.src))
            .then((snapshot) => (this.state.snapshot = snapshot));
    }
}
