"""Lazada integration constants.

Contains API endpoints, operation mappings, status mappings, and API limits
for Lazada integration.
"""

AUTH_URL = "https://auth.lazada.com/oauth/authorize"

API_ENDPOINTS = {
    "VN": "https://api.lazada.vn/rest/",
    "SG": "https://api.lazada.sg/rest/",
    "PH": "https://api.lazada.com.ph/rest/",
    "MY": "https://api.lazada.com.my/rest/",
    "TH": "https://api.lazada.co.th/rest/",
    "ID": "https://api.lazada.co.id/rest/",
    "ALL": "https://auth.lazada.com/rest/",
}

ALLOWED_LAZADA_DOC_HOSTS = {
    "lazada.com",
    "lazada.sg",
    "lazada.vn",
    "lazada.co.th",
    "lazada.co.id",
    "lazada.com.my",
    "lazada.com.ph",
}

API_OPERATIONS_MAPPING = {
    "GenerateAccessToken": {"url_path": "auth/token/create", "api_type": "public"},
    "RefreshAccessToken": {"url_path": "auth/token/refresh", "api_type": "public"},
    "GetSeller": {"url_path": "seller/get", "api_type": "seller"},
    "GetOrders": {"url_path": "orders/get", "api_type": "order"},
    "GetMultipleOrderItems": {"url_path": "orders/items/get", "api_type": "order"},
    "GetShipmentProvider": {
        "url_path": "order/shipment/providers/get",
        "api_type": "fulfillment",
    },
    "GetProducts": {"url_path": "products/get", "api_type": "product"},
    "UpdateSellableQuantity": {
        "url_path": "product/stock/sellable/update",
        "api_type": "product",
    },
    "PackagePack": {"url_path": "order/fulfill/pack", "api_type": "fulfillment"},
    "PrintAWB": {"url_path": "order/package/document/get", "api_type": "fulfillment"},
    "SetReadyToShip": {"url_path": "order/package/rts", "api_type": "fulfillment"},
}

ORDER_STATUSES_TO_SYNC = {"fbm": ["pending"], "fbl": ["confirmed"]}

ORDER_ITEM_STATUS_MAPPING = {
    "pending": "draft",
    "packed": "confirmed",
    "ready_to_ship_pending": "processing",
    "ready_to_ship": "processing",
    "shipped": "delivered",
    "delivered": "delivered",
    "confirmed": "delivered",
    "canceled": "canceled",
}

SUPPORTED_SHIPPING_PROVIDER_TYPES = ["express", "standard", "economy"]

ORDER_LIST_DAYS_LIMIT = 15
ORDER_LIST_SIZE_LIMIT = 100
ORDER_DETAIL_SIZE_LIMIT = 50
PRODUCT_LIST_SIZE_LIMIT = 50
SET_RTS_SIZE_LIMIT = 20
SYNC_INVENTORY_SIZE_LIMIT = 50
MAX_API_RETRIES = 3
