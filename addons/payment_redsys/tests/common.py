from odoo.addons.payment.tests.common import PaymentCommon


class RedsysCommon(PaymentCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.redsys = cls._prepare_provider(
            "redsys",
            update_values={
                "redsys_merchant_code": "99999999",
                "redsys_merchant_terminal": "777",
                "redsys_secret_key": "a1b2c3d4e5f6g7h8a1b2c3d4e5f6g7h8",
            },
        )
        cls.provider = cls.redsys
        cls.merchant_parameters = {
            "Ds_Order": "Test Transaction",
            "Ds_Amount": cls.amount * 100,
            "Ds_Currency": 978,
            "Ds_Card_Brand": "1",
            "Ds_Response": "0000",
        }
        cls.encoded_merchant_parameter = (
            "eyJEc19PcmRlciI6ICJUZXN0IFRyYW5zYWN0aW9uIiwgIkRzX0Ftb3VudCI6IDExMTExMC45"
            "OTk5OTk5OTk5OSwgIkRzX0N1cnJlbmN5IjogOTc4LCAiRHNfQ2FyZF9CcmFuZCI6ICIxIiwg"
            "IkRzX1Jlc3BvbnNlIjogIjAwMDAifQ=="
        )
        cls.payment_data = {
            "Ds_MerchantParameters": cls.encoded_merchant_parameter,
            "Ds_Signature": "upzUj96lLgOEUP5lvaj7lz0Se4MXmc5_GoJ32ACqZ3A=",
        }
