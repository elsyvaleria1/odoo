/** @odoo-module native */

/**
 * @param {HTMLElement} element
 * @param {string} type
 * @param {Object} data
 */
function triggerDragEvent(element, type, data = {}) {
    const event = new DragEvent(type, { bubbles: true });
    for (const key in data) {
        Object.defineProperty(event, key, {
            value: data[key],
        });
    }
    element.dispatchEvent(event);
}

/**
 * @param {HTMLElement} from
 * @param {HTMLElement} to
 * @param {number} height
 * @param {number} width
 */
function dragAndDropSignItemAtHeight(from, to, height = 0.5, width = 0.5) {
    const rect = to.getBoundingClientRect();
    const iframeWindow = to.ownerDocument.defaultView;
    const toPosition = {
        x: rect.x + iframeWindow.scrollX + to.clientWidth * width,
        y: rect.y + iframeWindow.scrollY + to.clientHeight * height,
    };

    const dataTransferObject = {};
    const dataTransferMock = {
        setData: (key, value) => {
            dataTransferObject[key] = value;
        },
        getData: (key) => dataTransferObject[key],
        setDragImage: () => {},
        items: [],
    };

    triggerDragEvent(from, "dragstart", {
        dataTransfer: dataTransferMock,
    });

    triggerDragEvent(to, "drop", {
        pageX: toPosition.x,
        pageY: toPosition.y,
        dataTransfer: dataTransferMock,
    });

    triggerDragEvent(from, "dragend");
}

export default {
    dragAndDropSignItemAtHeight,
};
