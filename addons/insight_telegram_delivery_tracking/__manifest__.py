{
    "name": "Telegram Questions About Carrier Tracking",
    "version": "19.0.1.0.0",
    "oldest_upgradable_version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Answer questions about parcel shipments and their carrier status from Telegram",
    "description": "Adds a tracking report to the Telegram questions bot: where one shipment is by its tracking number, what a customer has on the way, or every parcel still on the way, at the destination branch or delivered by the carrier and not yet validated. It reads the carrier status already recorded on the transfers, never the carrier's service, so an answer is as fresh as the last scheduled read and says when that was.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "insight_telegram",
        "delivery_tracking",
    ],
    "auto_install": True,
}
