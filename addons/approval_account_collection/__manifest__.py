{
    "name": "Cash Hand-in Proven by Both Parties",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "Validate a cash remittance only once the collector and the receiving treasury user each approve it with a passkey proof",
    "description": "Validating a remittance handed in to a cash till raises an approval request naming the two parties: the collector who hands the cash over and the treasury user who asked to validate, who receives it. Each decides with a proof of identity covering the remittance's collections, amount handed in and till (a passkey, as the shipped Cash Hand-in category requires; an administrator may add other methods), approving or refusing. When both approve, the remittance is validated in the receiver's name; a figure changed after the request was raised is refused. A collector cannot receive their own cash. Remittances deposited in a bank are not asked: the bank statement line matched by reference and amount is their proof. Installing the module is the decision to require this: the shipped category is active.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "account_collection",
        "approval_proof",
        "auth_passkey_proof",
    ],
    "data": [
        "data/approval_binding_data.xml",
        "data/approval_category_data.xml",
        "views/account_collection_remittance_views.xml",
    ],
}
