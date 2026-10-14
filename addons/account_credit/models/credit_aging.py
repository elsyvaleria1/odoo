from odoo.addons.account.tools.aging import AgingBucket, AgingLadder

CREDIT_LADDER = AgingLadder(
    (
        AgingBucket("current", "Not due", None, 0),
        AgingBucket("b1_30", "1-30 days", 1, 30),
        AgingBucket("b31_60", "31-60 days", 31, 60),
        AgingBucket("b61_90", "61-90 days", 61, 90),
        AgingBucket("b91_180", "91-180 days", 91, 180),
        AgingBucket("b180_plus", "Over 180 days", 181, None),
    )
)
