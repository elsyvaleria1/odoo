{
    "name": "Customer Credit - Commercial Scores",
    "version": "19.0.1.2.0",
    "category": "Accounting/Accounting",
    "summary": "Include measured customer commercial scores in credit scoring",
    "description": "Adds a commercial-score dimension to the credit scorecard and displays the customer’s commercial tier on credit profiles and reviews. The observer returns no measurement for a partner without score lines, so an unscored customer does not contribute a zero score. Requires both credit management and partner scoring.",
    "author": "AgroMarin",
    "website": "https://agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "account_credit",
        "partner_scoring",
    ],
    "data": [
        "data/scorecard_dimension_data.xml",
        "views/credit_profile_views.xml",
        "views/credit_review_views.xml",
        "views/credit_profile_search_views.xml",
    ],
    "auto_install": True,
}
