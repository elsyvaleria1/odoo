/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { KeepLast } from "@web/core/utils/concurrency";
import { debounce } from "@web/core/utils/timing";
import { getDataURLFromFile } from "@web/core/utils/urls";
import { Interaction } from "@web/public/interaction";

import { HrContractSalarySelectMenu } from "../js/hr_contract_salary_select_menu.js";

class SelectMenuWrapper extends Component {
    static template = "hr_contract_salary.SelectMenuWrapper";
    static components = { HrContractSalarySelectMenu };
    static props = { el: t.object(), name: t.string(), selectMenus: t.object() };
    props = useProps(this.constructor.props);

    setup() {
        this.selectMenu = proxy(this.props.selectMenus[this.props.name]);

        const optgroup = [...this.props.el.querySelectorAll("optgroup")];
        if (optgroup.length) {
            this.selectMenu.groups = optgroup.map((x) => ({
                label: x.label,
                choices: [...x.querySelectorAll("option")],
            }));
        } else {
            this.selectMenu.choices = [
                ...this.props.el.querySelectorAll("option"),
            ].filter((x) => x.value);
        }

        this.props.el.classList.add("d-none");
    }

    onSelect(value) {
        this.selectMenu.value = value;
        this.props.el.value = value;
        const event = new Event("change", { bubbles: true });
        this.props.el.dispatchEvent(event);
    }
}

export class SalaryPackage extends Interaction {
    static selector = "#hr_cs_form";

    dynamicContent = {
        ".benefit_input": {
            "t-on-change": this.onchangeBenefit,
        },
        "input.folded": {
            "t-on-change": this.onchangeFolded,
        },
        ".personal_info": {
            "t-on-change": this.onchangePersonalInfo,
        },
        "#hr_cs_submit": {
            "t-on-click": this.submitSalaryPackage,
        },
        ".o_submit_feedback": {
            "t-on-click": this.submitFeedback,
        },
        "a[name='recompute']": {
            "t-on-click": this.recompute,
        },
        "button[name='toggle_personal_information']": {
            "t-on-click": this.togglePersonalInformation,
        },
        "input.border-danger": {
            "t-on-change": this.checkFormValidity,
        },
        "div.invalid_radio": {
            "t-on-change": this.checkFormValidity,
        },
        "input.document": {
            "t-on-change": this.onchangeDocument,
        },
        "input[type='range']": {
            "t-on-input": this.onchangeSlider,
        },
        "select[name='private_country_id']": {
            "t-on-change": this.onchangeCountry,
        },
        "#hr_contract_salary *:has(> select:not(.refuse-reason-select))": {
            "t-component": (el) => {
                const child = el.querySelector("select:not(.refuse-reason-select)");
                return [
                    SelectMenuWrapper,
                    {
                        el: child,
                        name: child.name,
                        selectMenus: this.selectMenus,
                    },
                ];
            },
        },
        "input[type='number']": {
            "t-on-keydown": this.onkeydownInput,
        },
    };

    setup() {
        this.keepLast = new KeepLast();
        this.selectMenus = proxy({});
        document.body.id = "hr_contract_salary";
        const selectWrapperEls = this.el.querySelectorAll(
            "#hr_contract_salary select:not(.refuse-reason-select)",
        );

        const workingScheduleSelect = this.el.querySelector(
            "#hr_contract_salary select[name='simulation_working_schedule']",
        );
        if (workingScheduleSelect) {
            const wrapperDiv = workingScheduleSelect.parentNode.insertBefore(
                this.el.ownerDocument.createElement("div"),
                workingScheduleSelect,
            );
            wrapperDiv.append(workingScheduleSelect);
        }

        selectWrapperEls.forEach((el) => {
            this.selectMenus[el.name] = {
                disabled: false,
                choices: [],
                value: el.value,
                groups: [],
                required: el.required,
                autoSort: false,
            };
        });

        this.updateGross = debounce(this.updateGross, 1000);
        this.initializeUnsetSliders();
        const whitelistInput = document.querySelector("input[name='whitelist']");
        const whitelist = whitelistInput ? whitelistInput.value : "";
        if (whitelist) {
            const whitelisted_fields = whitelist.split(",");
            this.el.querySelectorAll("input").forEach((input) => {
                if (!whitelisted_fields.includes(input.name)) {
                    input.setAttribute("disabled", true);
                }
            });
            for (const [name, selectMenuInst] of Object.entries(this.selectMenus)) {
                if (!whitelisted_fields.includes(name)) {
                    selectMenuInst.disabled = true;
                }
            }
        }
        this.stateElements = this.el
            .querySelector("select[name='private_state_id']")
            ?.querySelectorAll("option");
        this.onchangeCountry();

        this.el
            .querySelectorAll("#hr_cs_configurator .hr_cs_control input.folded:checked")
            .forEach((input) => {
                const foldedContent = input
                    .closest("div")
                    ?.querySelector(".folded_content");
                if (foldedContent) {
                    foldedContent.classList.remove("d-none");
                }
            });
    }

    willStart() {
        return Promise.all([this.updateGross(), this.setUpBenefits()]);
    }

    setUpBenefits() {
        return Promise.all(
            Array.from(document.querySelectorAll("input")).map(async (input) => {
                const dependentBenefits = input.getAttribute(
                    "data-benefit_ids-dependent",
                );
                const requested_documents = input.getAttribute(
                    "data-requested_documents",
                );
                let mandatoryBenefitSelected;
                if (dependentBenefits || requested_documents) {
                    let newValue;
                    if (input.type === "radio") {
                        const target = [
                            ...document.querySelectorAll(
                                "input[name='" + input.name + "']",
                            ),
                        ].find((elem) => elem.checked);
                        newValue = target?.getAttribute("data-value");
                        if (newValue === "No") {
                            newValue = 0;
                        }
                    } else if (input.type === "checkbox") {
                        newValue = input.checked;
                    } else {
                        newValue = input.value;
                    }
                    mandatoryBenefitSelected = Boolean(+newValue);
                }

                if (dependentBenefits && !mandatoryBenefitSelected) {
                    await this.updateDependentBenefits(
                        dependentBenefits,
                        mandatoryBenefitSelected,
                    );
                }
                if (requested_documents) {
                    requested_documents.split(",").forEach((requested_document) => {
                        const documentDiv = document.querySelector(
                            "div[name='" + requested_document + "']",
                        );
                        if (documentDiv) {
                            documentDiv.classList.toggle(
                                "d-none",
                                !mandatoryBenefitSelected,
                            );
                        }
                    });
                }
            }),
        );
    }

    initializeUnsetSliders() {
        document.querySelectorAll("input[type='range']").forEach((input) => {
            const inputName = input.name.replace("_slider", "");
            const valueInput = document.querySelector(
                "input[name='" + inputName + "']",
            );
            if (valueInput && !valueInput.value) {
                input.value = 0;
                valueInput.value = 0;
            }
        });
    }

    async getFileData(documentName) {
        const fileInput = document.querySelector("input[name='" + documentName + "']");
        if (fileInput && fileInput.files[0]) {
            const testString = await getDataURLFromFile(fileInput.files[0]);
            const regex = new RegExp(",(.{0,})", "g");
            const img_src = regex.exec(testString)[1];
            return img_src;
        }
        return false;
    }

    async getPersonalDocuments() {
        const documentNames = Array.from(
            document.querySelectorAll("input[type='file']"),
        ).map((input) => ({
            name: input.name,
            appliesOn: input.getAttribute("applies-on"),
        }));
        const documentSrcs = {
            version_personal: {},
            employee: {},
            address: {},
            bank_account: {},
        };
        const promises = documentNames.map(async ({ name, appliesOn }) => {
            const docSrc = await this.getFileData(name);
            documentSrcs[appliesOn][name] = docSrc;
        });
        await Promise.all(promises);
        return documentSrcs;
    }

    /**
     * Run an rpc and keep the form usable if it fails.
     *
     * Every call here used to be bare: a 500 or a dropped connection left the
     * configurator mid-update - "Recompute" showing, NET marked outdated, the
     * net panel hidden - with nothing told to the applicant, who is a
     * candidate on a public page and has no console to look at.
     *
     * @param {Promise} promise the rpc to guard
     * @param {Function} [restore] undo whatever the caller changed before it
     * @returns {Promise} resolving to undefined when the call failed
     */
    async guardRpc(promise, restore) {
        try {
            return await promise;
        } catch {
            restore?.();
            this.services.notification.add(
                _t("Something went wrong. Please check your connection and try again."),
                { type: "danger" },
            );
            return undefined;
        }
    }

    getBenefits() {
        const benefits = {
            version_personal: {},
            version: {},
            employee: {},
            address: {},
            bank_account: {},
        };
        benefits.employee.job_title =
            document.querySelector("input[name='job_title']")?.value ?? "";
        benefits.employee.employee_job_id =
            document.querySelector("input[name='employee_job_id']")?.value ?? "";
        benefits.employee.department_id =
            document.querySelector("input[name='department_id']")?.value ?? "";
        document.querySelectorAll("input[applies-on]").forEach((input) => {
            if (input.type === "file") {
                return;
            }
            const appliesOn = input.getAttribute("applies-on");
            if (input.type === "checkbox") {
                benefits[appliesOn][input.name] = input.checked;
            } else if (input.type === "radio" && input.checked) {
                benefits[appliesOn][input.name] = input.getAttribute("data-value");
            } else if (input.type !== "hidden" && input.type !== "radio") {
                benefits[appliesOn][input.name] = input.value;
            }
        });
        document.querySelectorAll("textarea[applies-on]").forEach((area) => {
            const appliesOn = area.getAttribute("applies-on");
            benefits[appliesOn][area.name] = area.value;
        });
        document
            .querySelectorAll("select.benefit_input, select.personal_info")
            .forEach((select) => {
                if (select.name === "simulation_working_schedule") {
                    return;
                }
                const appliesOn = select.getAttribute("applies-on");
                benefits[appliesOn][select.name] = select.value;
            });
        return benefits;
    }

    updateGrossToNetModal(data) {
        this.el.querySelector("div[name='salary_package_resume']").replaceChildren();
        this.renderAt(
            "hr_contract_salary.salary_package_resume",
            {
                lines: data.resume_lines_mapped,
                categories: data.resume_categories,
                configurator_warning: data.configurator_warning,
            },
            this.el.querySelector("div[name='salary_package_resume']"),
        );

        const wageWithHolidaysInput = document.querySelector(
            "input[name='wage_with_holidays']",
        );
        if (wageWithHolidaysInput) {
            wageWithHolidaysInput.value = data["wage_with_holidays"];
        }
        const netDiv = document.querySelector("div[name='net']");
        if (netDiv) {
            netDiv.classList.remove("d-none");
            netDiv.style.display = "";
        }
        const netInput = document.querySelector("input[name='NET']");
        if (netInput) {
            netInput.classList.remove("o_outdated");
        }
    }

    onchangeFoldedResetInteger() {
        return true;
    }

    onchangeFolded(event) {
        const foldedContent =
            event.target.parentElement.parentElement.querySelector(".folded_content");
        if (!foldedContent) {
            return;
        }
        const checked = event.target.checked;
        if (!checked) {
            foldedContent.querySelectorAll("input").forEach((input) => {
                if (
                    input.type === "number" &&
                    this.onchangeFoldedResetInteger(input.name)
                ) {
                    input.value = 0;
                    input.dispatchEvent(new Event("change", { bubbles: true }));
                }
            });
        } else {
            foldedContent.querySelectorAll("select").forEach((select) => {
                select.dispatchEvent(new Event("change", { bubbles: true }));
            });
        }
        foldedContent.classList.toggle("d-none", !checked);
    }

    onchangeSlider(event) {
        const benefitField = event.target.name.replace("_slider", "");
        const input = document.querySelector("input[name='" + benefitField + "']");
        if (input) {
            input.value = event.target.value;
        }
    }

    async onchangeCountry() {
        const stateElement = document.querySelector("select[name='private_state_id']");
        if (!stateElement) {
            return;
        }
        const selectedStateID = stateElement.value;
        const countryID = document.querySelector(
            "select[name='private_country_id']",
        )?.value;
        let enableState = true;
        const stateSelectMenu = this.selectMenus["private_state_id"];
        stateElement.querySelectorAll("option").forEach((option) => option.remove());
        if (!this.stateElements) {
            return;
        }
        this.stateElements.forEach((option) => stateElement.appendChild(option));
        stateElement.querySelectorAll("option").forEach((option) => {
            const stateCountryID = option.getAttribute("data-additional-info");
            if (countryID === stateCountryID) {
                enableState = false;
            } else {
                option.remove();
            }
        });
        let selectedIndex = -1;
        for (let i = 0; i < stateElement.length; ++i) {
            if (stateElement.options[i].value === selectedStateID) {
                selectedIndex = i;
            }
        }
        const choicesEls = [...stateElement.querySelectorAll("option")];
        if (selectedIndex === -1) {
            stateSelectMenu.value = "";
        }
        stateSelectMenu.choices = choicesEls;
        stateSelectMenu.disabled = enableState;
        stateElement.selectedIndex = selectedIndex;
    }

    onkeydownInput(event) {
        const disallowedKeys = ["KeyE", "NumpadSubtract", "Minus"];
        if (event.target.dataset.fieldType === "integer") {
            disallowedKeys.push("NumpadDecimal", "Period");
        }
        if (disallowedKeys.includes(event.code)) {
            event.preventDefault();
        }
    }

    _dismissAlerts() {
        setTimeout(() => {
            document.querySelectorAll(".alert").forEach((alertEl) => {
                alertEl.remove();
            });
        }, 4000);
    }

    _isInvalidInput() {
        let isInvalidInput;
        document.querySelectorAll("input[data-field-type=integer]").forEach((input) => {
            if (input.value && !Number.isInteger(parseFloat(input.value))) {
                isInvalidInput = true;
                if (!input.classList.contains("border-danger")) {
                    const alertDiv = document.createElement("div");
                    alertDiv.className =
                        "alert alert-danger alert-dismissable fade show";
                    alertDiv.textContent = _t("Not a valid input in integer field");
                    document
                        .querySelector("button#hr_cs_submit")
                        ?.parentElement?.append(alertDiv);
                    input.classList.toggle("border-danger", isInvalidInput);
                    this._dismissAlerts();
                }
            } else if (input.classList.contains("border-danger")) {
                input.classList.remove("border-danger");
            }
        });
        return isInvalidInput;
    }

    async onchangeBenefit(event) {
        if (this._isInvalidInput()) {
            return false;
        }
        if (event.target.type === "number" && parseFloat(event.target.value) < 0) {
            event.target.value = 0;
        }
        let benefitField = event.target.name;
        if (benefitField.includes("_slider")) {
            benefitField = benefitField.replace("_slider", "");
        } else if (benefitField.includes("_manual")) {
            benefitField = benefitField.replace("_manual", "");
        } else if (benefitField.includes("_radio")) {
            benefitField = benefitField.replace("_radio", "");
        } else if (benefitField.includes("select_")) {
            benefitField = benefitField.replace("select_", "");
        }
        const requested_documents = event.target.getAttribute(
            "data-requested_documents",
        );
        if (requested_documents) {
            let hide;
            if (event.target.type === "number") {
                hide = event.target.value === "0" || event.target.value === "";
            } else if (event.target.type === "checkbox") {
                hide = !event.target.checked;
            } else if (event.target.type === "radio") {
                hide = !!event.target.parentElement.querySelector(".hr_cs_control_no");
            }
            requested_documents.split(",").forEach((requested_document) => {
                const documentDiv = document.querySelector(
                    "div[name='" + requested_document + "']",
                );
                if (documentDiv) {
                    documentDiv.classList.toggle("d-none", hide);
                }
            });
        }

        let newValue;
        if (event.target.type === "radio") {
            const target = [
                ...document.querySelectorAll("input[name='" + event.target.name + "']"),
            ].find((elem) => elem.checked);
            const description = document.querySelector(
                "span[name='description_" + benefitField + "']",
            );
            if (description) {
                description.classList.toggle(
                    "d-none",
                    target.classList.contains("hide_description"),
                );
            }
            newValue = target.getAttribute("data-value");
            if (newValue === "No") {
                newValue = 0;
            }
        } else if (event.target.type === "checkbox") {
            newValue = event.target.checked;
        } else {
            newValue = event.target.value;
        }

        const dependentBenefits = event.target.getAttribute(
            "data-benefit_ids-dependent",
        );

        const mandatoryBenefitSelected = Boolean(+newValue);
        await this.updateDependentBenefits(dependentBenefits, mandatoryBenefitSelected);
        await this.updateAfterChangingBenefit(
            event.target.type,
            benefitField,
            newValue,
        );
    }

    updateDependentBenefits(dependentBenefits, mandatoryBenefitSelected) {
        if (!dependentBenefits) {
            return;
        }
        return Promise.all(
            dependentBenefits
                .trim()
                .split(" ")
                .map(async (dependentBenefit) => {
                    const targets = [
                        ...document.querySelectorAll(
                            "input[name='" + dependentBenefit + "']",
                        ),
                    ];
                    const firstTarget = targets[0];
                    if (!firstTarget) {
                        return;
                    }
                    if (!mandatoryBenefitSelected) {
                        const dependentBenefitSelected =
                            this.checkInputSelected(dependentBenefit);
                        let dependentBenefitField = dependentBenefit;
                        let type = firstTarget.type;
                        if (dependentBenefit.includes("select_")) {
                            dependentBenefitField = dependentBenefit.replace(
                                "select_",
                                "",
                            );
                            type = "select";
                        } else if (dependentBenefit.includes("manual")) {
                            type = "manual";
                            dependentBenefitField = dependentBenefit.replace(
                                "_manual",
                                "",
                            );
                        } else if (dependentBenefit.includes("_slider")) {
                            type = "slider";
                            dependentBenefitField = dependentBenefit.replace(
                                "_slider",
                                "",
                            );
                        } else if (dependentBenefit.includes("_radio")) {
                            type = "radio";
                            dependentBenefitField = dependentBenefit.replace(
                                "_radio",
                                "",
                            );
                        }
                        if (dependentBenefitSelected) {
                            const targetType = firstTarget.type;
                            if (targetType === "checkbox") {
                                firstTarget.click();
                            } else if (targetType === "radio") {
                                const toCheck = targets.filter(
                                    (elem) => elem.dataset.value === "0.0",
                                );
                                if (toCheck[0]) {
                                    toCheck[0].click();
                                }
                            }
                            targets.forEach((t) => {
                                t.value = 0;
                                t.disabled = true;
                                if (t.parentElement) {
                                    t.parentElement.classList.add("o_disabled");
                                }
                            });
                            firstTarget.dispatchEvent(
                                new Event("change", { bubbles: true }),
                            );
                            await this.updateAfterChangingBenefit(
                                type,
                                dependentBenefitField,
                                0,
                            );
                        }
                        targets.forEach((t) => {
                            t.disabled = true;
                            if (t.parentElement) {
                                t.parentElement.classList.add("o_disabled");
                            }
                        });

                        const mandatoryBenefitsNames = (
                            firstTarget.getAttribute(
                                "data-benefit_ids-mandatory-names",
                            ) || ""
                        )
                            .trim()
                            .split(";")
                            .filter((elem) => elem !== "");
                        const dep = mandatoryBenefitsNames.shift();
                        const title = _t(
                            "In order to choose %s, first you need to choose:\n %s",
                            dep,
                            mandatoryBenefitsNames.join("\n "),
                        );

                        const closestDiv = firstTarget.closest("div");
                        if (closestDiv && closestDiv.parentElement) {
                            closestDiv.parentElement.setAttribute("title", title);
                        }
                        if (closestDiv) {
                            closestDiv.style.cursor = "pointer";
                        }
                    } else {
                        const mandatoryBenefits = (
                            firstTarget.getAttribute("data-benefit_ids-mandatory") || ""
                        )
                            .trim()
                            .split(" ");
                        const allMandatorySelected = mandatoryBenefits.every((adv) =>
                            this.checkInputSelected(adv),
                        );
                        if (allMandatorySelected) {
                            const disabledTargets = targets.filter((elem) =>
                                elem.hasAttribute("disabled"),
                            );
                            if (disabledTargets.length) {
                                disabledTargets.forEach((t) =>
                                    t.removeAttribute("disabled"),
                                );
                                if (firstTarget.parentElement) {
                                    firstTarget.parentElement.classList.remove(
                                        "o_disabled",
                                    );
                                }
                                const closestDiv = firstTarget.closest("div");
                                if (closestDiv) {
                                    closestDiv.style.cursor = "";
                                    closestDiv.removeAttribute("title");
                                }
                            }
                        }
                    }
                }),
        );
    }

    checkInputSelected(benefit) {
        const targets = [...document.querySelectorAll("input[name='" + benefit + "']")];
        if (!targets.length) {
            return false;
        }
        const type = targets[0].type;
        let newValue;
        if (type === "radio") {
            const checked = targets.find((elem) => elem.checked);
            newValue = checked ? checked.getAttribute("data-value") : undefined;
        } else if (type === "checkbox") {
            newValue = targets[0].checked;
        } else {
            newValue = targets[0].value;
        }
        return Boolean(+newValue);
    }

    async updateAfterChangingBenefit(type, benefitField, newValue) {
        if (type !== "file") {
            const result = await this.guardRpc(
                rpc("/salary_package/onchange_benefit", {
                    benefit_field: benefitField,
                    new_value: newValue,
                    offer_id: parseInt(
                        document.querySelector("input[name='offer_id']")?.value || "0",
                    ),
                    benefits: this.getBenefits(),
                    token: document.querySelector("input[name='token']")?.value || "",
                }),
            );
            if (!result) {
                return;
            }
            if (type !== "select") {
                const benefitInput = document.querySelector(
                    "input[name='" + benefitField + "']",
                );
                if (benefitInput) {
                    benefitInput.value = result.new_value;
                }
            }
            const descriptionSpan = document.querySelector(
                "span[name='description_" + benefitField + "']",
            );
            if (descriptionSpan) {
                descriptionSpan.innerHTML = result.description;
            }
            if (result.extra_values) {
                result.extra_values.forEach((extra_value) => {
                    const extraInput = document.querySelector(
                        "input[name='" + extra_value[0] + "']",
                    );
                    if (extraInput) {
                        extraInput.value = extra_value[1];
                    }
                });
            }
            await this.updateGross();
        }
    }

    async onchangeDocument(input) {
        if (input.target.files && input.target.files.length > 0) {
            const testString = await getDataURLFromFile(input.target.files[0]);
            const regex = new RegExp(",(.{0,})", "g");
            const img_src = regex.exec(testString)[1];
            const pdfIframe = document.getElementById(input.target.name + "_pdf");
            const imgEl = document.getElementById(input.target.name + "_img");
            if (img_src.startsWith("JVBERi0")) {
                if (pdfIframe) {
                    pdfIframe.src = testString;
                    pdfIframe.classList.remove("d-none");
                }
                if (imgEl) {
                    imgEl.classList.add("d-none");
                }
            } else {
                if (imgEl) {
                    imgEl.src = testString;
                    imgEl.classList.remove("d-none");
                }
                if (pdfIframe) {
                    pdfIframe.classList.add("d-none");
                }
            }
        }
    }

    updateGross() {
        document.querySelector("div[name='net']")?.classList.add("d-none");
        document.querySelector("div[name='compute_net']")?.classList.remove("d-none");
        document.querySelector("a[name='details']")?.classList.add("d-none");
        document.querySelector("a[name='recompute']")?.classList.remove("d-none");
        document.querySelector("input[name='NET']")?.classList.add("o_outdated");
        return this.keepLast.add(
            this.guardRpc(
                rpc("/salary_package/update_salary", {
                    offer_id: parseInt(
                        document.querySelector("input[name='offer_id']")?.value || "0",
                    ),
                    benefits: this.getBenefits(),
                    simulation_working_schedule:
                        document.querySelector(
                            "select[name='simulation_working_schedule']",
                        )?.value || "",
                    token: document.querySelector("input[name='token']")?.value || "",
                }).then((data) => {
                    const wageInput = document.querySelector("input[name='wage']");
                    if (wageInput) {
                        wageInput.value = data["new_gross"];
                    }
                    document
                        .querySelector("a[name='recompute']")
                        ?.classList.add("d-none");
                    document
                        .querySelector("a[name='details']")
                        ?.classList.remove("d-none");
                    this.updateGrossToNetModal(data);
                }),
                () => {
                    document
                        .querySelector("div[name='net']")
                        ?.classList.remove("d-none");
                    document
                        .querySelector("div[name='compute_net']")
                        ?.classList.add("d-none");
                },
            ),
        );
    }

    async onchangePersonalInfo(event) {
        let newValue;
        if (event.target.type === "radio") {
            const target = [
                ...document.querySelectorAll("input[name='" + event.target.name + "']"),
            ].find((elem) => elem.checked);
            newValue = target ? target.getAttribute("data-value") : undefined;
        } else if (event.target.type === "checkbox") {
            newValue = event.target.checked;
        } else {
            newValue = event.target.value;
        }
        const data = await this.guardRpc(
            rpc("/salary_package/onchange_personal_info", {
                field: event.target.name,
                value: newValue,
                offer_id:
                    parseInt(
                        document.querySelector("input[name='offer_id']")?.value || "0",
                    ) || false,
                token: document.querySelector("input[name='token']")?.value || "",
            }),
        );
        if (Object.keys(data || {}).length > 0) {
            const childDiv = document.querySelector(
                "div[name='personal_info_child_group_" + data.field + "']",
            );
            if (childDiv) {
                const childInputs = childDiv.querySelectorAll("input");
                if (data.hide_children) {
                    childDiv.classList.add("d-none");
                    childInputs.forEach((input) => input.removeAttribute("required"));
                } else {
                    childDiv.classList.remove("d-none");
                    childInputs.forEach((input) => input.setAttribute("required", ""));
                }
            }
        }
    }

    recompute() {
        document.querySelector("a[name='details']")?.classList.remove("d-none");
        document.querySelector("a[name='recompute']")?.classList.add("d-none");
        document.querySelector("input[name='NET']")?.classList.remove("o_outdated");
    }

    checkFormValidity() {
        const requiredInputs = [...document.querySelectorAll("input:required")];
        const requiredSelects = [...document.querySelectorAll("select:required")];
        const requiredTextAreas = [...document.querySelectorAll("textarea:required")];
        const requiredEmptyInput = requiredInputs.find(
            (input) =>
                input.value === "" &&
                input.name !== "" &&
                input.type !== "checkbox" &&
                input.offsetParent !== null,
        );
        const requiredEmptySelect = requiredSelects.find(
            (select) => select.value === "" && select.offsetParent !== null,
        );
        const requiredEmptyTextArea = requiredTextAreas.find(
            (textarea) => textarea.value === "" && textarea.offsetParent !== null,
        );
        const emailInput = document.querySelector("input[name='private_email']");
        const email = emailInput ? emailInput.value : "";
        const atpos = email.indexOf("@");
        const dotpos = email.lastIndexOf(".");
        const invalid_email =
            atpos < 1 || dotpos < atpos + 2 || dotpos + 2 >= email.length;
        const isInvalidInput = this._isInvalidInput();
        let elementToScroll;
        let elementToScrollPosition;
        const isEmailEmpty = email === "";

        let requiredEmptyRadio;
        const radios = [...document.querySelectorAll("input[type=radio]:required")];
        const groups = Object.values(
            radios.reduce(
                (result, el) =>
                    Object.assign(result, {
                        [el.name]: (result[el.name] || []).concat(el),
                    }),
                {},
            ),
        );
        groups.forEach((group) => {
            const radioContainer = group[0].parentElement.parentElement;
            if (!group.some((el) => el.checked)) {
                requiredEmptyRadio = true;
                radioContainer.classList.toggle("invalid_radio", requiredEmptyRadio);
                elementToScroll = radioContainer;
                elementToScrollPosition =
                    radioContainer.getBoundingClientRect().top + window.scrollY;
            } else if (radioContainer.classList.contains("invalid_radio")) {
                radioContainer.classList.remove("invalid_radio");
            }
        });
        const submitParent =
            document.querySelector("button#hr_cs_submit")?.parentElement;
        if (submitParent) {
            submitParent
                .querySelectorAll(".required_alert")
                .forEach((el) => el.remove());
        }

        if (
            requiredEmptyInput ||
            requiredEmptySelect ||
            requiredEmptyTextArea ||
            requiredEmptyRadio
        ) {
            const alertDiv = document.createElement("div");
            alertDiv.className =
                "alert alert-danger alert-dismissable fade show mt-2 required_alert";
            alertDiv.textContent = _t("Some required fields are not filled");
            if (submitParent) {
                submitParent.append(alertDiv);
            }
            requiredInputs.forEach((input) => {
                input.classList.toggle("border-danger", input.value === "");
                const inputPosition =
                    input.getBoundingClientRect().top + window.scrollY;
                if (
                    (!elementToScroll || inputPosition < elementToScrollPosition) &&
                    input.value === "" &&
                    input.type !== "checkbox"
                ) {
                    elementToScroll = input;
                    elementToScrollPosition = inputPosition;
                }
            });
            requiredTextAreas.forEach((textarea) => {
                textarea.classList.toggle("border-danger", textarea.value === "");
                const textareaPosition =
                    textarea.getBoundingClientRect().top + window.scrollY;
                if (
                    (!elementToScroll || textareaPosition < elementToScrollPosition) &&
                    textarea.value === ""
                ) {
                    elementToScroll = textarea;
                    elementToScrollPosition = textareaPosition;
                }
            });
            requiredSelects.forEach((select) => {
                const selectParent =
                    select.parentElement?.querySelector(".o_select_menu");
                if (selectParent) {
                    selectParent.classList.toggle("border-danger", select.value === "");
                    const selectPosition =
                        selectParent.getBoundingClientRect().top + window.scrollY;
                    if (
                        (!elementToScroll ||
                            selectPosition <= elementToScrollPosition) &&
                        select.value === ""
                    ) {
                        elementToScroll = selectParent;
                        elementToScrollPosition = selectPosition;
                    }
                }
            });
        } else {
            requiredInputs.forEach((input) => {
                input.classList.remove("border-danger");
            });
            requiredTextAreas.forEach((textarea) => {
                textarea.classList.remove("border-danger");
            });
            requiredSelects.forEach((select) => {
                const selectParent =
                    select.parentElement?.querySelector(".o_select_menu");
                if (selectParent && select.value !== "") {
                    selectParent.classList.remove("border-danger");
                }
            });
        }
        if (invalid_email) {
            if (emailInput) {
                emailInput.classList.add("border-danger");
            }
            if (!isEmailEmpty) {
                const emailAlertDiv = document.createElement("div");
                emailAlertDiv.className =
                    "alert alert-danger alert-dismissable fade show";
                emailAlertDiv.textContent = _t("Not a valid e-mail address");
                if (submitParent) {
                    submitParent.append(emailAlertDiv);
                }
            }
            if (emailInput) {
                const emailPosition =
                    emailInput.getBoundingClientRect().top + window.scrollY;
                if (!elementToScroll || emailPosition <= elementToScrollPosition) {
                    elementToScroll = emailInput;
                }
            }
        }
        this._dismissAlerts();
        if (elementToScroll) {
            elementToScroll.scrollIntoView({ block: "center", behavior: "smooth" });
        }
        return (
            !invalid_email &&
            !requiredEmptyInput &&
            !requiredEmptySelect &&
            !requiredEmptyTextArea &&
            !requiredEmptyRadio &&
            !isInvalidInput
        );
    }

    async getFormInfo() {
        const personalDocuments = await this.getPersonalDocuments();
        let benefits = this.getBenefits();
        benefits = {
            employee: Object.assign(benefits.employee, personalDocuments.employee),
            version: Object.assign(benefits.version, personalDocuments.version),
            version_personal: Object.assign(
                benefits.version_personal,
                personalDocuments.version_personal,
            ),
            address: Object.assign(benefits.address, personalDocuments.address),
            bank_account: Object.assign(
                benefits.bank_account,
                personalDocuments.bank_account,
            ),
        };

        return {
            token: document.querySelector("input[name='token']")?.value || "",
            benefits: benefits,
            offer_id:
                parseInt(
                    document.querySelector("input[name='offer_id']")?.value || "0",
                ) || false,
            original_link:
                document.querySelector("input[name='original_link']")?.value || "",
        };
    }

    async submitSalaryPackage() {
        if (this.checkFormValidity()) {
            const formInfo = await this.getFormInfo();
            const data = await this.guardRpc(rpc("/salary_package/submit", formInfo));
            if (!data) {
                return;
            }
            if (data["error"]) {
                const errorDiv = document.createElement("div");
                errorDiv.className = "alert alert-danger alert-dismissable fade show";
                errorDiv.textContent = data["error_msg"];
                document
                    .querySelector("button#hr_cs_submit")
                    ?.parentElement?.append(errorDiv);
            } else {
                document.location.pathname =
                    "/sign/document/" + data["request_id"] + "/" + data["token"];
            }
        }
    }

    async submitFeedback() {
        const feedbackEl = document.getElementById("feedback-textarea");
        const offer_id =
            parseInt(document.querySelector("input[name='offer_id']")?.value || "0") ||
            false;
        const feedbackValue = feedbackEl ? feedbackEl.value : "";
        const token = document.querySelector("input[name='token']")?.value || "";
        if (!feedbackValue) {
            return;
        }
        const res = await this.guardRpc(
            rpc("/salary_package/post_feedback/", {
                feedback: feedbackValue,
                offer_id: offer_id,
                token,
            }),
        );
        if (res) {
            const successEl = document.getElementById("feedback-form-success");
            if (successEl) {
                successEl.style.display = "";
            }
            setTimeout(() => {
                if (successEl) {
                    successEl.style.display = "none";
                }
                if (feedbackEl) {
                    feedbackEl.value = "";
                }
                document.getElementById("feedback-form")?.classList.remove("show");
            }, 3000);
        }
    }

    togglePersonalInformation() {
        document
            .querySelectorAll("button[name='toggle_personal_information']")
            .forEach((btn) => {
                btn.classList.toggle("d-none");
            });
        const personalInfo = document.querySelector("div[name='personal_info']");
        if (personalInfo) {
            personalInfo.style.display =
                personalInfo.style.display === "none" ? "" : "none";
        }
        const withholdingTaxes = document.querySelector(
            "div[name='personal_info_withholding_taxes']",
        );
        if (withholdingTaxes) {
            withholdingTaxes.style.display =
                withholdingTaxes.style.display === "none" ? "" : "none";
        }
    }
}

registry
    .category("public.interactions")
    .add("hr_contract_salary.salary_package", SalaryPackage);
