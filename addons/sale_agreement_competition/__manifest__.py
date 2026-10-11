{
    "name": "Sales Agreement Price Comparison",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Display recorded competitor prices and price gaps on sale agreement lines",
    "description": "Adds market-price, comparison-scope and percentage-gap columns to the agreement line list. The shared trade agreement competition addon computes these values from recorded competitor offers. This addon supplies the sale agreement view extension; it does not fetch external market prices.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "sale_agreement",
        "sale_competition",
        "trade_agreement_competition",
    ],
    "data": [
        "views/sale_agreement_views.xml",
    ],
    "auto_install": True,
}
