{
    "name": "Freight Requests from Shipping Orders",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "A shipping order sent with /embarque prepares the carrier's freight request",
    "description": "When a shipping order sent with /embarque goes on a delivery order, prepares the freight request of the carrier's approval category as a draft: the carrier's billing partner, the tracking number as reference, the destination and the customer as location, the sheet's total as amount and the single line of the category's product, the sales order, the salesperson and the carrier's bank accounts in the reason, and the sheet attached. The delivery orders it pays for are listed on the request, apart from the approval gate of the transfer, so approving the freight never validates them. A request already open for the same tracking number gets the transfer instead of a second request. The draft is never submitted: whoever owns it checks it against the sheet and submits it.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_shipment_telegram",
        "approval_account",
        "approval_app",
        "approval_product",
    ],
    "data": [
        "views/delivery_carrier_views.xml",
        "views/approval_request_views.xml",
        "views/stock_picking_views.xml",
    ],
    "auto_install": True,
}
