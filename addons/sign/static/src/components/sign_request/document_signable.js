/** @odoo-module native */
import { App, Component, proxy, t, useProps, whenReady, xml } from "@odoo/owl";
import {
    buildPDFViewerURL,
    injectPDFCustomStyles,
} from "@sign/components/sign_request/utils";
import {
    NextDirectSignDialog,
    PublicSignerDialog,
    SignNameAndSignatureDialog,
    SignRefusalDialog,
    SMSSignerDialog,
    ThankYouDialog,
} from "@sign/dialogs/dialogs";
import { useAppContext } from "@web/core/app_context";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { hidePDFJSButtons } from "@web/core/utils/pdfjs";
import { makeAppConfig, makeEnv, startServices } from "@web/env";
import { AlertDialog } from "@web/ui/dialog";
import { MainComponentsContainer } from "@web/ui/main_components_container";

import { SignablePDFIframe } from "./signable_PDF_iframe.js";

export function datasetFromElements(elements) {
    return Array.from(elements).map((el) =>
        Object.entries(el.dataset).reduce((dataset, [key, value]) => {
            try {
                const parsed = JSON.parse(value);
                if (
                    key === "value" &&
                    typeof parsed === "number" &&
                    parsed > Number.MAX_SAFE_INTEGER
                ) {
                    dataset[key] = value;
                } else {
                    dataset[key] = parsed;
                }
            } catch {
                dataset[key] = value;
            }
            return dataset;
        }, {}),
    );
}

export class Document extends Component {
    static template = xml`<t t-call-slot='default'/>`;
    static props = { parent: t.any(), PDFIframeClass: t.any() };
    props = useProps(this.constructor.props);

    setup() {
        this.appContext = useAppContext();
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.ui = useService("ui");
        this.signInfo = useService("signInfo");

        this.state = proxy({
            documentsWithUnsignedItems: new Set(),
            viewedDocuments: new Set(),
            openedDocumentIndex: 0,
        });

        useLayoutEffect(
            () => {
                this.getDataFromHTML();
                if (!this.requestID) {
                    return;
                }
                this.signInfo.set({
                    documentId: this.requestID,
                    signRequestToken: this.requestToken,
                    signRequestState: this.requestState,
                    signRequestItemId: this.signRequestItemId,
                    signRequestItemToken: this.accessToken,
                    todayFormattedDate: this.todayFormattedDate,
                    dateFormat: this.dateFormat,
                });
            },
            () => [],
        );

        useLayoutEffect(
            () => {
                if (
                    !this.state.documentsWithUnsignedItems ||
                    !this.state.viewedDocuments ||
                    !this.documents ||
                    this.documents.length === 0
                ) {
                    return;
                }

                const hasUnsignedDocs = this.state.documentsWithUnsignedItems.size > 0;
                const currentDocUnsigned = this.isDocumentUnsigned();
                const allDocsViewed =
                    this.state.viewedDocuments.size === this.documents.length;

                if (!hasUnsignedDocs && allDocsViewed) {
                    this.showBanner(this.validateBanner);
                    return;
                }

                this.hideBanner(this.validateBanner);

                if (currentDocUnsigned) {
                    this.hideBanner(this.nextDocumentBanner);
                } else {
                    this.showBanner(this.nextDocumentBanner);
                }
            },
            () => [
                this.state.documentsWithUnsignedItems,
                this.state.openedDocumentIndex,
            ],
        );
    }

    /** @returns {Set} */
    getDocumentsWithUnsignedItems() {
        return this.state.documentsWithUnsignedItems;
    }

    /** @returns {boolean} */
    isDocumentUnsigned() {
        if (!this.documents) {
            return false;
        }
        const documentId = this.documents[this.state.openedDocumentIndex].id;
        return this.state.documentsWithUnsignedItems.has(documentId);
    }

    /**
     * @param {string} documentId
     * @param {boolean} hasUnsignedItems
     */
    updateDocumentsWithUnsignedItems(documentId, hasUnsignedItems) {
        const newSet = new Set(this.state.documentsWithUnsignedItems);
        if (hasUnsignedItems) {
            newSet.add(documentId);
        } else {
            newSet.delete(documentId);
        }
        this.state.documentsWithUnsignedItems = newSet;
        this.controlNavigatorVisibility(hasUnsignedItems);
    }

    documentNavigate(shift) {
        this.state.openedDocumentIndex =
            (this.state.openedDocumentIndex + shift + this.documents.length) %
            this.documents.length;
        this.state.viewedDocuments.add(
            this.documents[this.state.openedDocumentIndex].id,
        );
        this.documents.forEach((doc, index) => {
            if (index === this.state.openedDocumentIndex) {
                doc.iframe.classList.remove("d-none");
            } else {
                doc.iframe.classList.add("d-none");
            }
        });
        document.querySelectorAll(".o_sign_document_navigator_text").forEach((text) => {
            if (text) {
                text.textContent =
                    this.state.openedDocumentIndex + 1 + " / " + this.documents.length;
            }
        });
    }

    showBanner(banner) {
        if (banner) {
            banner.style.display = "block";
            const an = banner.animate(
                { opacity: 1 },
                { duration: 500, fill: "forwards" },
            );
            an.finished.then(() => {
                if (this.ui.isSmall) {
                    banner.scrollIntoView({
                        behavior: "smooth",
                        block: "center",
                        inline: "center",
                    });
                }
            });
        }
    }

    hideBanner(banner) {
        if (banner) {
            banner.style.display = "none";
            banner.style.opacity = 0;
        }
    }

    controlNavigatorVisibility(hasUnsignedItems) {
        if (this.documents) {
            const currentDoc = this.documents[this.state.openedDocumentIndex];
            const iframeManager = currentDoc.iframeManager;
            if (iframeManager && iframeManager.navigator) {
                if (!hasUnsignedItems && this.isDocumentUnsigned()) {
                    hasUnsignedItems = Object.values(
                        iframeManager.signItems || {},
                    ).some((pageItems) =>
                        Object.values(pageItems).some(
                            (item) =>
                                item.data.responsible === iframeManager.currentRole,
                        ),
                    );
                }
                iframeManager.navigator.toggle(hasUnsignedItems);
            }
        }
    }

    getDataFromHTML() {
        const { el: parentEl } = this.props.parent;
        this.documents = datasetFromElements(
            parentEl.querySelectorAll(".o_sign_document_input_info"),
        );
        const iframes = parentEl.querySelectorAll(".o_sign_pdf_iframe");
        for (let i = 0; i < this.documents.length; i++) {
            if (i > 0) {
                iframes[i].classList.add("d-none");
            }
            iframes[i].setAttribute(
                "src",
                buildPDFViewerURL(
                    this.documents[i].attachmentLocation,
                    this.ui.isSmall,
                ),
            );
            hidePDFJSButtons(iframes[i], {
                hideDownload: true,
                hidePrint: true,
                hidePresentation: true,
                hideRotation: true,
            });
            this.documents[i].iframe = iframes[i];
        }
        this.documents.forEach((document) => {
            document.iframe.addEventListener("load", () => {
                setTimeout(() => {
                    document.iframeManager = this.initializeIframe(
                        document.iframe,
                        document.id,
                    );
                }, 1);
            });
        });

        document.querySelectorAll(".o_sign_document_navigator_text").forEach((text) => {
            if (text) {
                text.textContent = "1 / " + this.documents.length;
            }
        });
        document
            .querySelectorAll(".o_sign_document_navigator_left_arrow")
            .forEach((arrow) => {
                arrow?.addEventListener("click", (e) => this.documentNavigate(-1));
            });
        document
            .querySelectorAll(".o_sign_document_navigator_right_arrow")
            .forEach((arrow) => {
                arrow?.addEventListener("click", (e) => this.documentNavigate(1));
            });

        this.templateName = parentEl.querySelector(
            "#o_sign_input_template_name",
        )?.value;
        this.templateID = parseInt(
            parentEl.querySelector("#o_sign_input_template_id")?.value,
        );
        this.templateItemsInProgress = parseInt(
            parentEl.querySelector("#o_sign_input_template_in_progress_count")?.value,
        );
        this.requestID = parseInt(
            parentEl.querySelector("#o_sign_input_sign_request_id")?.value,
        );
        this.requestToken = parentEl.querySelector(
            "#o_sign_input_sign_request_token",
        )?.value;
        this.requestState = parentEl.querySelector(
            "#o_sign_input_sign_request_state",
        )?.value;
        this.signRequestItemId = parseInt(
            parentEl.querySelector("#o_sign_input_sign_request_item_id")?.value,
        );
        this.accessToken = parentEl.querySelector("#o_sign_input_access_token")?.value;
        this.todayFormattedDate = parentEl.querySelector(
            "#o_sign_input_today_formatted_date",
        )?.value;
        this.dateFormat = parentEl.querySelector("#o_sign_input_date_format")?.value;
        this.templateEditable = Boolean(
            parentEl.querySelector("#o_sign_input_template_editable"),
        );
        this.authMethod = parentEl.querySelector("#o_sign_input_auth_method")?.value;
        this.signerName = parentEl.querySelector(
            "#o_sign_signer_name_input_info",
        )?.value;
        this.signerPhone = parentEl.querySelector(
            "#o_sign_signer_phone_input_info",
        )?.value;
        this.redirectURL = parentEl.querySelector(
            "#o_sign_input_optional_redirect_url",
        )?.value;
        this.redirectURLText = parentEl.querySelector(
            "#o_sign_input_optional_redirect_url",
        )?.value;
        this.redirectURLText = parentEl.querySelector(
            "#o_sign_input_optional_redirect_url_text",
        )?.value;
        this.isSignerHasCompany = Boolean(
            parentEl.querySelector("#o_sign_input_is_signer_user")?.value,
        );
        this.types = datasetFromElements(
            parentEl.querySelectorAll(".o_sign_field_type_input_info"),
        );
        const items = datasetFromElements(
            parentEl.querySelectorAll(".o_sign_item_input_info"),
        );
        this.documents.forEach(
            (document) =>
                (document.items = items.filter(
                    (item) => item.document_id === document.id,
                )),
        );
        this.state.documentsWithUnsignedItems = new Set(
            this.documents.filter((doc) => doc.items?.length > 0).map((doc) => doc.id),
        );
        this.state.viewedDocuments = new Set([this.documents[0].id]);
        this.selectOptions = datasetFromElements(
            parentEl.querySelectorAll(".o_sign_select_options_input_info"),
        );
        this.showThankYouDialog = Boolean(
            parentEl.querySelector("#o_sign_show_thank_you_dialog"),
        );
        this.validateBanner = parentEl.querySelector(".o_sign_validate_banner");
        this.validateButton = parentEl.querySelector(".o_validate_button");
        this.nextDocumentBanner = parentEl.querySelector(
            ".o_sign_next_document_banner",
        );
        this.nextDocumentButton = parentEl.querySelector(".o_next_document_button");
        this.currentRole = parseInt(
            parentEl.querySelector("#o_sign_input_current_role")?.value,
        );
        this.currentName = parentEl.querySelector(
            "#o_sign_input_current_role_name",
        )?.value;

        this.isUnknownPublicUser = Boolean(
            parentEl.querySelector("#o_sign_is_public_user"),
        );
        this.frameHash = parentEl.querySelector("#o_sign_input_sign_frame_hash")?.value;
        this.validateButton?.addEventListener("click", () => {
            this.signDocuments();
        });
        this.nextDocumentButton?.addEventListener("click", () => {
            this.documentNavigate(1);
        });
    }

    initializeIframe(iframe, sign_document_id) {
        if (
            !iframe.contentDocument.querySelector('link[href*="pdfjs_overrides.css"]')
        ) {
            injectPDFCustomStyles(iframe.contentDocument);
        }
        const props = this.getIframeProps(sign_document_id);
        const iframeManager = new this.props.PDFIframeClass(
            iframe.contentDocument,
            this.appContext,
            {
                rpc,
                orm: this.orm,
                dialog: this.dialog,
                ui: this.ui,
                signInfo: this.signInfo,
            },
            props,
        );
        return iframeManager;
    }

    getMailFromSignItems() {
        let mail = "";
        for (let i = 0; i < this.documents.length; i++) {
            const document = this.documents[i];
            const iframeManager = document.iframeManager;
            for (const page in iframeManager.signItems) {
                Object.values(iframeManager.signItems[page]).forEach(({ el }) => {
                    const childInput = el.querySelector("input");
                    const value = el.value || (childInput && childInput.value);
                    if (value && value.indexOf("@") >= 0) {
                        mail = value;
                    }
                });
            }
        }
        return mail;
    }

    updateSignerName(name) {
        this.signerName = name;
        this.documents.forEach((document) =>
            document.iframeManager.updateSignerName(name),
        );
    }

    async openAuthDialog() {
        const authDialog = await this.getAuthDialog();
        if (authDialog.component) {
            this.closeFn = this.dialog.add(authDialog.component, authDialog.props, {
                onClose: () => {
                    this.validateButton.removeAttribute("disabled");
                },
            });
        } else {
            this._sign();
        }
    }

    async getAuthDialog() {
        if (this.authMethod === "sms" && !this.signatureInfo.smsToken) {
            const credits = await rpc("/sign/has_sms_credits");
            if (credits) {
                return {
                    component: SMSSignerDialog,
                    props: {
                        signerPhone: this.signerPhone,
                        postValidation: (code) => {
                            this.signatureInfo.smsToken = code;
                            return this._signDocuments();
                        },
                    },
                };
            }
            return false;
        }
        return false;
    }

    closeDialog() {
        this.closeFn && this.closeFn();
        this.closeFn = false;
    }

    async signDocuments() {
        this.signatureInfo = {
            name: this.signerName || "",
            mail: this.getMailFromSignItems(),
            signatureValues: {},
            frameValues: {},
        };
        for (let i = 0; i < this.documents.length; i++) {
            const iframeManager = this.documents[i].iframeManager;
            const [signatureValues, frameValues] =
                iframeManager.getSignatureValuesFromConfiguration();
            Object.assign(this.signatureInfo.signatureValues, signatureValues);
            Object.assign(this.signatureInfo.frameValues, frameValues);
        }
        const noSignItems = this.documents.every((document) => {
            const iframeManager = document.iframeManager;
            return Object.keys(iframeManager.signItems).length === 0;
        });
        this.signatureInfo.hasNoSignature =
            Object.keys(this.signatureInfo.signatureValues).length === 0 && noSignItems;
        this._signDocuments();
    }

    _signDocuments() {
        this.validateButton.setAttribute("disabled", true);
        if (this.signatureInfo.hasNoSignature) {
            const signature = {
                name: this.signerName || "",
            };
            this.closeFn = this.dialog.add(SignNameAndSignatureDialog, {
                signature,
                onConfirm: () => {
                    this.signatureInfo.name = signature.name;
                    this.signatureInfo.signatureValues = signature
                        .getSignatureImage()
                        .split(",")[1];
                    this.signatureInfo.frameValues = [];
                    this.signatureInfo.hasNoSignature = false;
                    this.closeDialog();
                    this._signDocuments();
                },
            });
        } else if (this.isUnknownPublicUser) {
            this.closeFn = this.dialog.add(
                PublicSignerDialog,
                {
                    name: this.signatureInfo.name,
                    mail: this.signatureInfo.mail,
                    postValidation: async (requestID, requestToken, accessToken) => {
                        this.signInfo.set({
                            documentId: requestID,
                            signRequestToken: requestToken,
                            signRequestItemToken: accessToken,
                        });
                        this.requestID = requestID;
                        this.requestToken = requestToken;
                        this.accessToken = accessToken;
                        if (this.coords.latitude !== undefined) {
                            await rpc(
                                `/sign/save_location/${requestID}/${accessToken}`,
                                this.coords,
                            );
                        }
                        this.isUnknownPublicUser = false;
                        this._signDocuments();
                    },
                },
                {
                    onClose: () => {
                        this.validateButton.removeAttribute("disabled");
                    },
                },
            );
        } else if (this.authMethod) {
            this.openAuthDialog();
        } else {
            this._sign();
        }
    }

    _getRouteAndParams() {
        const route = this.signatureInfo.smsToken
            ? `/sign/sign/${encodeURIComponent(this.requestID)}/${encodeURIComponent(
                  this.accessToken,
              )}/${encodeURIComponent(this.signatureInfo.smsToken)}`
            : `/sign/sign/${encodeURIComponent(this.requestID)}/${encodeURIComponent(
                  this.accessToken,
              )}`;

        const params = {
            signature: this.signatureInfo.signatureValues,
            frame: this.signatureInfo.frameValues,
        };

        return [route, params];
    }

    disableItems() {
        for (let i = 0; i < this.documents.length; i++) {
            const iframeManager = this.documents[i].iframeManager;
            iframeManager.disableItems();
        }
    }

    openThankYouDialog() {
        this.dialog.add(ThankYouDialog, {
            redirectURL: this.redirectURL,
            redirectURLText: this.redirectURLText,
        });
    }

    async _sign() {
        const [route, params] = this._getRouteAndParams();
        this.ui.block();
        const response = await rpc(route, params).finally(() => this.ui.unblock());
        this.validateButton.removeAttribute("disabled");
        if (response.success) {
            this.signInfo.set({ companyCountryCode: response.company_country_code });
            if (response.url) {
                document.location.pathname = response.url;
            } else {
                this.disableItems();
                const nameList = this.signInfo.get("nameList");
                if (nameList && nameList.length > 0) {
                    this.dialog.add(NextDirectSignDialog);
                } else {
                    this.openThankYouDialog();
                }
            }
        } else {
            this.onSignError(response);
        }
    }

    onSignError(response) {
        if (response.sms) {
            this.signatureInfo.smsToken = undefined;
            this.dialog.add(AlertDialog, {
                title: _t("Error"),
                body: _t(
                    "Your signature was not submitted. Check the SMS validation code, or request a new one: a code expires after 10 minutes or 5 wrong attempts.",
                ),
            });
        } else if (response.no_sms_credits) {
            this.dialog.add(AlertDialog, {
                title: _t("Error"),
                body: _t(
                    "This document cannot be signed right now: the SMS validation is unavailable. The sender has been notified.",
                ),
            });
        } else {
            this.dialog.add(
                AlertDialog,
                {
                    title: _t("Error"),
                    body: _t(
                        "Sorry, an error occurred, please try to fill the document again.",
                    ),
                },
                {
                    onClose: () => {
                        window.location.reload();
                    },
                },
            );
            this.validateButton.setAttribute("disabled", true);
        }
    }

    getIframeProps(sign_document_id) {
        const document = this.documents.find(
            (document) => document.id === sign_document_id,
        );
        return {
            attachmentLocation: document.attachmentLocation,
            requestID: this.requestID,
            requestToken: this.requestToken,
            accessToken: this.accessToken,
            signItemTypes: this.types,
            signItems: document.items,
            hasSignRequests: false,
            signItemOptions: this.selectOptions,
            currentRole: this.currentRole,
            currentName: this.currentName,
            readonly: document.iframe.getAttribute("readonly") === "readonly",
            frameHash: this.frameHash,
            signerName: this.signerName,
            signerPhone: this.signerPhone,
            isUnknownPublicUser: this.isUnknownPublicUser,
            authMethod: this.authMethod,
            redirectURL: this.redirectURL,
            redirectURLText: this.redirectURLText,
            templateEditable: this.templateEditable,
            showThankYouDialog: this.showThankYouDialog,
            isSignerHasCompany: this.isSignerHasCompany,
            openThankYouDialog: () => this.openThankYouDialog(),
            documentId: sign_document_id,
            updateDocumentsWithUnsignedItems: (documentId, hasUnsignedItems) =>
                this.updateDocumentsWithUnsignedItems(documentId, hasUnsignedItems),
            isDocumentUnsigned: () => this.isDocumentUnsigned(),
            getDocumentsWithUnsignedItems: () => this.getDocumentsWithUnsignedItems(),
            signDocuments: () => this.signDocuments(),
            updateSignerName: (name) => this.updateSignerName(name),
        };
    }
}

function usePublicRefuseButton(component) {
    useLayoutEffect(
        () => {
            const refuseButtons = document.querySelectorAll(
                ".o_sign_refuse_document_button",
            );
            if (refuseButtons.length) {
                refuseButtons.forEach((button) =>
                    button.addEventListener("click", () => {
                        component.dialog.add(SignRefusalDialog);
                    }),
                );
                if (
                    new URLSearchParams(window.location.search).get(
                        "refuse_document",
                    ) === "1"
                ) {
                    refuseButtons[0].click();
                }
            }
        },
        () => [],
    );
}

export class SignableDocument extends Document {
    static components = {
        MainComponentsContainer,
    };
    static template = xml`<MainComponentsContainer/>`;

    setup() {
        super.setup();
        this.coords = {};
        usePublicRefuseButton(this);
        useLayoutEffect(
            () => {
                if (this.requestID) {
                    const { el: parentEl } = this.props.parent;
                    const askLocation = parentEl.getElementById(
                        "o_sign_ask_location_input",
                    );
                    if (askLocation && navigator.geolocation) {
                        navigator.geolocation.getCurrentPosition(
                            ({ coords: { latitude, longitude } }) => {
                                Object.assign(this.coords, {
                                    latitude,
                                    longitude,
                                });
                                if (this.requestState !== "shared") {
                                    rpc(
                                        `/sign/save_location/${this.requestID}/${this.accessToken}`,
                                        this.coords,
                                    );
                                }
                            },
                            () => {},
                            { enableHighAccuracy: true },
                        );
                    }
                }
            },
            () => [this.requestID],
        );
    }

    getIframeProps(sign_document_id) {
        return {
            ...super.getIframeProps(sign_document_id),
            coords: this.coords,
        };
    }
}

/** @param { HTMLElement } parent */
export async function initDocumentToSign(parent) {
    const env = makeEnv();
    await startServices(env);
    await whenReady();
    const app = new App(makeAppConfig(env, { name: "Signable Document" }));
    await app
        .createRoot(SignableDocument, {
            props: {
                parent: { el: parent },
                PDFIframeClass: SignablePDFIframe,
            },
        })
        .mount(parent.body);
}
