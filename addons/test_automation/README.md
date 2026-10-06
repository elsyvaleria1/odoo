# Automation Tests

Provides test models and regression suites for the automation framework and its webhook extension. The loaded test package covers flow handling, server actions, UI tours, time triggers, webhooks and runtime workflows.

Dependencies are declared in the manifest, including `automation`, `automation_webhook` and `test_mail`. This is a test addon, not an automation application or a demonstration of every supported workflow.

Run the addon with Odoo testing enabled on a dedicated test database and select `/test_automation`. Verify the collected test count and failures in the resulting log; this README does not report an executed test run or a fixed coverage count.
