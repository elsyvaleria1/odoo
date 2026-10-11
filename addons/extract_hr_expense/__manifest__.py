{
    "name": "Expense Receipt Extraction",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Expenses",
    "summary": "Populate eligible expense fields from receipt extraction results",
    "description": "Adds receipt-extraction actions and maps merchant, date, amount and currency results to expenses under the addon’s default-value checks. Uses the extraction framework and its installed strategies. Product prediction and catalog-price replacement belong to the separate expense-prediction bridge.",
    "author": "AgroMarin",
    "website": "https://agromarin.com",
    "license": "Other OSI approved licence",
    "depends": [
        "hr_expense",
        "extract",
    ],
    "data": [
        "views/hr_expense_views.xml",
    ],
}
