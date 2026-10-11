/** @odoo-module native */
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { NameAndSignature } from "@web/components/signature";
import { localization } from "@web/core/l10n/localization";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { elementRef } from "@web/core/utils/element_ref";
import { Dialog } from "@web/ui/dialog";

export class SignNameAndSignature extends NameAndSignature {
    static template = "sign.NameAndSignature";
    static props = {
        ...NameAndSignature.props,
        activeFrame: t.boolean(),
        defaultFrame: t.string(),
        frame: t.object().optional(),
        hash: t.string(),
        onNameChange: t.function(),
        onSignatureChange: t.function().optional(),
    };

    setup() {
        super.setup();
        this.props.signature.signatureChanged = this.state.signMode !== "draw";

        if (this.props.frame) {
            this.state.activeFrame = this.props.activeFrame || false;
            this.frame = this.props.defaultFrame;

            this.signFrame = elementRef();
            this.props.frame.updateFrame = () => {
                if (this.state.activeFrame) {
                    this.props.signature.signatureChanged = true;
                    const xOffset = localization.direction === "rtl" ? 0.75 : 0.06;
                    this.signFrame.el.classList.toggle("active", true);
                    return this.html2canvas(this.signFrame.el, {
                        backgroundColor: null,
                        width: this.signatureRef.el.width,
                        height: this.signatureRef.el.height,
                        x: -this.signatureRef.el.width * xOffset,
                        y: -this.signatureRef.el.height * 0.09,
                    }).then((canvas) => {
                        this.frame = canvas.toDataURL("image/png");
                    });
                }
                return Promise.resolve(false);
            };

            this.props.frame.getFrameImageSrc = () =>
                this.state.activeFrame ? this.frame : false;
        }

        onWillStart(() => {
            if (this.props.frame) {
                return Promise.all([
                    user.hasGroup("base.group_user").then((isSystemUser) => {
                        this.showFrameCheck = isSystemUser;
                    }),
                    import("html2canvas").then(({ default: html2canvas }) => {
                        this.html2canvas = html2canvas;
                    }),
                ]);
            }
        });
    }

    onFrameChange() {
        this.state.activeFrame = !this.state.activeFrame;
    }

    onSignatureAreaClick() {
        if (this.state.signMode === "draw") {
            this.props.signature.signatureChanged = true;
            this.props.onSignatureChange(this.state.signMode);
        }
    }

    onClickSignLoad() {
        super.onClickSignLoad();
        this.props.signature.signatureChanged = true;
    }

    async onClickSignAuto() {
        if (this.fonts.length <= 1) {
            this.fonts = await rpc(`/web/sign/get_fonts/`);
        }
        super.onClickSignAuto();
        this.props.signature.signatureChanged = true;
    }

    onClickSignDrawClear() {
        super.onClickSignDrawClear();
        this.props.signature.signatureChanged = true;
    }

    get signFrameClass() {
        return this.state.activeFrame && this.state.signMode !== "draw" ? "active" : "";
    }

    /**
     * Override to enable/disable SignNameAndSignatureDialog's footer buttons
     * @param { Event } e
     */
    onInputSignName(e) {
        super.onInputSignName(e);
        this.props.onNameChange(this.props.signature.name);
        this.props.onSignatureChange(this.state.signMode);
    }
}

export class SignNameAndSignatureDialog extends Component {
    static props = {
        signature: t.object(),
        frame: t.object().optional(),
        signatureType: t.string().optional(),
        displaySignatureRatio: t.number(),
        activeFrame: t.boolean(),
        defaultFrame: t.string().optional(),
        mode: t.string().optional(),
        signatureImage: t.string().optional(),
        hash: t.string(),
        onConfirm: t.function(),
        onConfirmAll: t.function().optional(),
        close: t.function(),
    };
    static template = "sign.SignNameAndSignatureDialog";
    static components = {
        Dialog,
        SignNameAndSignature,
    };
    props = useProps(this.constructor.props);

    setup() {
        this.footerState = proxy({
            signButtonDisabled:
                !this.props.signature.name || !this.props.signature.signatureChanged,
            signAllButtonsDisabled: !this.props.signature.name,
        });
    }

    get nameAndSignatureProps() {
        return {
            signature: this.props.signature || "signature",
            signatureType: this.props.signatureType,
            displaySignatureRatio: this.props.displaySignatureRatio,
            activeFrame: this.props.activeFrame,
            defaultFrame: this.props.defaultFrame || "",
            mode: this.props.mode || "auto",
            frame: this.props.frame || false,
            hash: this.props.hash,
            onNameChange: this.onNameChange.bind(this),
            defaultFont: "LaBelleAurore-Regular.ttf",
            onSignatureChange: this.onSignatureChange.bind(this),
        };
    }

    get dialogProps() {
        return {
            title: _t("Adopt Your Signature"),
            size: "md",
        };
    }

    onNameChange(name) {
        const isNameFilled = Boolean(name);
        this.footerState.signButtonDisabled = !isNameFilled;
        this.footerState.signAllButtonsDisabled = !isNameFilled;
    }

    onSignatureChange(signMode) {
        const { name, isSignatureEmpty, signatureChanged } = this.props.signature;
        const isAutoMode = signMode === "auto";
        const buttonsDisabled = !name || isAutoMode ? !name.trim() : isSignatureEmpty;
        if (this.footerState.signAllButtonsDisabled !== buttonsDisabled) {
            this.footerState.signAllButtonsDisabled = buttonsDisabled;
        }
        this.footerState.signButtonDisabled = buttonsDisabled || !signatureChanged;
    }
}
