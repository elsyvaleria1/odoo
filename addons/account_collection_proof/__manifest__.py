{
    "name": "Field Collections Confirmed by the Customer",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "The customer confirms on their own phone or email what they paid the collector",
    "description": "When a collection in custody is posted, its customer is asked to confirm it on every channel that reaches them (email, Telegram): the amount, the day, how they paid, who received it, with the link to their receipt. They answer Confirm or Not right there, and the answer is chained as proof evidence on the collection. The mail asking them replaces the plain receipt mail. A collection whose customer no channel reaches shows as unreachable; with the customer at hand, the collector proves the collection with a code sent to them instead. Not right, or no answer in three days, puts an activity on the collection supervisor's list; the remittance that hands such collections in says how many of them the customer has not confirmed, without blocking it. Cancelling or resetting a collection takes the question back.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "account_collection",
        "mail_proof",
    ],
    "data": [
        "views/account_payment_views.xml",
        "views/account_collection_remittance_views.xml",
    ],
}
