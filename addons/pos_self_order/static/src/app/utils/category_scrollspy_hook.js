/** @odoo-module native */
import { onMounted, onWillUnmount } from "@odoo/owl";

/**
 * @param {string} categoryId
 * @param {Object} categoryScrollContainerRef
 * @param {Object} productScrollContainerRef
 * @param {Function} [onCategoryVisible=() => {}]
 * @param {Object} [options={}]
 * @param {number} [options.categoryScrollOffsetLeft=-5]
 * @param {number} [options.productScrollOffsetTop=-15]
 * @param {number} [options.visibleThreshold=100]
 */

export function useCategoryScrollSpy(
    categoryId,
    categoryScrollContainerRef,
    productScrollContainerRef,
    onCategoryVisible = () => {},
    options = {},
) {
    const {
        categoryScrollOffsetLeft = 0,
        productScrollOffsetTop = -5,
        visibleThreshold = 100,
    } = options;

    let categorySections = [];
    let isScrolling = false;

    let selectedCategoryId = categoryId;

    function selectCategory(categoryId) {
        selectedCategoryId = categoryId;
        onCategoryVisible(selectedCategoryId);
        const tabEl = categoryScrollContainerRef.el.querySelector(
            `[data-category-pill="${categoryId}"]`,
        );
        if (tabEl) {
            const scrollLeft = tabEl.offsetLeft + categoryScrollOffsetLeft;
            categoryScrollContainerRef.el.scrollTo({
                left: scrollLeft || 0,
                behavior: "smooth",
            });
        }
    }

    function scrollToCategory(categoryId) {
        const section = categorySections.find(
            (el) => el.dataset.category === "" + categoryId,
        );
        const { el: scrollEl } = productScrollContainerRef;

        if (section) {
            const containerTop = scrollEl.getBoundingClientRect().top;
            const sectionTop = section.getBoundingClientRect().top;
            const scrollOffset =
                sectionTop - containerTop + scrollEl.scrollTop + productScrollOffsetTop;
            scrollEl.scrollTo({ top: scrollOffset });
        }

        selectCategory(categoryId);
    }

    function onProductScroll() {
        let topCategory = null;
        let minTop = Infinity;
        const containerTop =
            productScrollContainerRef.el.getBoundingClientRect().top + visibleThreshold;

        for (const section of categorySections) {
            const distanceFromTop = section.getBoundingClientRect().top - containerTop;
            const absDistanceFromTop = Math.abs(distanceFromTop);

            if (distanceFromTop <= 0 && absDistanceFromTop < minTop) {
                topCategory = section.dataset.category;
                minTop = absDistanceFromTop;
            } else if (distanceFromTop > 0) {
                if (!topCategory) {
                    topCategory = section.dataset.category;
                }
                break;
            }
        }

        const topCategoryId = Number(topCategory);
        if (selectedCategoryId !== topCategoryId) {
            selectCategory(topCategoryId);
        }
    }

    function deferScroll() {
        if (!isScrolling) {
            isScrolling = true;
            requestAnimationFrame(() => {
                onProductScroll();
                isScrolling = false;
            });
        }
    }

    onMounted(() => {
        const scrollEl = productScrollContainerRef.el;
        categorySections = [...scrollEl.querySelectorAll("[data-category]")];
        scrollEl.addEventListener("scroll", deferScroll);
        onProductScroll();
    });

    onWillUnmount(() => {
        productScrollContainerRef.el.removeEventListener("scroll", deferScroll);
    });

    return {
        scrollToCategory,
    };
}
