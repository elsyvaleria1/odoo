/** @odoo-module native */
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/translation";

/**
 * @param {HTMLElement} cart
 * @param {HTMLElement} elem
 * @param {number} offsetTop
 * @param {number} offsetLeft
 * @returns {Promise}
 */
function animateClone(cart, elem, offsetTop, offsetLeft) {
    if (!cart) {
        return Promise.resolve();
    }
    cart.classList.remove("d-none");
    const blinkEl = cart.querySelector(".o_animate_blink");
    if (blinkEl) {
        blinkEl.classList.add("o_red_highlight", "o_shadow_animation");
        setTimeout(() => blinkEl.classList.remove("o_shadow_animation"), 500);
        setTimeout(() => blinkEl.classList.remove("o_red_highlight"), 2500);
    }
    return new Promise(function (resolve) {
        if (!elem) {
            resolve();
            return;
        }
        const imgToDrag = elem.querySelector("img");
        if (imgToDrag) {
            const imgRect = imgToDrag.getBoundingClientRect();
            const cartRect = cart.getBoundingClientRect();
            const imgClone = imgToDrag.cloneNode(true);
            imgClone.className = "o_website_sale_animate";
            Object.assign(imgClone.style, {
                position: "fixed",
                top: imgRect.top + "px",
                left: imgRect.left + "px",
                width: imgRect.width + "px",
                height: imgRect.height + "px",
                zIndex: "9999",
                transition: "all 0.5s ease",
            });
            document.body.appendChild(imgClone);

            imgClone.offsetHeight;
            Object.assign(imgClone.style, {
                top: cartRect.top + offsetTop + "px",
                left: cartRect.left + offsetLeft + "px",
                width: "75px",
                height: "75px",
            });

            imgClone.addEventListener(
                "transitionend",
                function onEnd() {
                    imgClone.removeEventListener("transitionend", onEnd);
                    Object.assign(imgClone.style, {
                        width: "0px",
                        height: "0px",
                        transition: "all 0.3s ease",
                    });
                    imgClone.addEventListener(
                        "transitionend",
                        function onShrinkEnd() {
                            imgClone.removeEventListener("transitionend", onShrinkEnd);
                            imgClone.remove();
                            resolve();
                        },
                        { once: true },
                    );
                },
                { once: true },
            );
        } else {
            resolve();
        }
    });
}

/**
 * @param { HTMLElement } element
 * @returns { HTMLFormElement|undefined }
 */
function getClosestProductForm(element) {
    return (
        element.closest("form") ?? element.closest(".js_product")?.querySelector("form")
    );
}

/**
 * @param {Object} data
 * @return {void}
 */
function updateCartNavBar(data) {
    browser.sessionStorage.setItem("website_sale_cart_quantity", data.cart_quantity);
    const cartQuantityElements = document.querySelectorAll(".my_cart_quantity");
    for (const cartQuantityElement of cartQuantityElements) {
        if (data.cart_quantity === 0) {
            cartQuantityElement.classList.add("d-none");
        } else {
            const cartIconElement = document.querySelector("li.o_wsale_my_cart");
            cartIconElement.classList.remove("d-none");
            cartQuantityElement.classList.remove("d-none");
            cartQuantityElement.classList.add("o_mycart_zoom_animation");
            setTimeout(() => {
                cartQuantityElement.textContent = data.cart_quantity;
                cartQuantityElement.classList.remove("o_mycart_zoom_animation");
            }, 300);
        }
    }

    document
        .querySelector(".oe_cart")
        ?.classList.toggle("col-lg-7", !!data.cart_quantity);

    if (data.cart_ready) {
        document
            .querySelector("a[name='website_sale_main_button']")
            ?.classList.remove("disabled");
    } else {
        document
            .querySelector("a[name='website_sale_main_button']")
            ?.classList.add("disabled");
    }
}

/**
 * @return {void}
 */
function updateQuickReorderButton() {
    const quickReorderButton = document.getElementById("quick_reorder_button");
    if (document.querySelector(".o_wsale_quick_reorder_line_group")) {
        quickReorderButton.removeAttribute("disabled");
        quickReorderButton.parentElement.title = "";
    } else {
        quickReorderButton.click();
        quickReorderButton.setAttribute("disabled", "true");
        quickReorderButton.parentElement.title = _t(
            "No previous products available for reorder.",
        );
    }
}

/**
 * @param {string | null} message
 */
function showWarning(message) {
    if (!message) {
        return;
    }
    const page = document.querySelector(".oe_website_sale");
    if (!page) {
        return;
    }
    let cartAlert = page.querySelector("#data_warning");
    if (!cartAlert) {
        cartAlert = document.createElement("div");
        cartAlert.className = "alert alert-danger alert-dismissible";
        cartAlert.setAttribute("role", "alert");
        cartAlert.id = "data_warning";
        cartAlert.innerHTML =
            '<button type="button" class="btn-close" data-bs-dismiss="alert"></button> ' +
            "<span></span>";
        page.prepend(cartAlert);
    }
    const span = cartAlert.querySelector("span:last-child");
    if (span) {
        span.textContent = message;
    }
}

/**
 * @param {Element} container
 */
function getSelectedAttributeValues(container) {
    return Array.from(
        container.querySelectorAll(
            "input.js_variant_change:checked, select.js_variant_change",
        ),
    ).map((el) => parseInt(el.value));
}

/**
 * @param {Element} container
 */
function getSelectedVariantAttributeValues(container) {
    return Array.from(
        container.querySelectorAll(
            "input.js_variant_change:checked:not(.no_variant), select.js_variant_change:not(.no_variant)",
        ),
    ).map((el) => parseInt(el.value));
}

export default {
    animateClone: animateClone,
    getClosestProductForm: getClosestProductForm,
    updateCartNavBar: updateCartNavBar,
    showWarning: showWarning,
    getSelectedAttributeValues: getSelectedAttributeValues,
    getSelectedVariantAttributeValues: getSelectedVariantAttributeValues,
    updateQuickReorderButton: updateQuickReorderButton,
};
