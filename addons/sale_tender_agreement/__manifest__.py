{
    "name": "Sales Tender Agreement Awards",
    "version": "19.0.1.0.0",
    "category": "Sales/Sales",
    "summary": "Enable sales tenders to award blanket agreements to winning buyers",
    "description": "Applies the shared tender-agreement mixins to sales tenders and offers and adds agreement links to the tender view. Selecting the agreements award mode creates confirmed customer agreements from awarded quantities and net prices; the default award mode remains orders.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "sale_agreement",
        "sale_tender",
        "trade_tender_agreement",
    ],
    "data": [
        "views/sale_tender_views.xml",
    ],
    "auto_install": True,
}
