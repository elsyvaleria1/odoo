import ctypes
from logging import getLogger
from time import sleep

from odoo.addons.iot_drivers.iot_handlers.lib.ctypes_terminal_driver import (
    CtypesTerminalDriver,
    create_ctypes_string_buffer,
    import_ctypes_library,
)
from odoo.addons.iot_drivers.tools.system import IS_WINDOWS

_logger = getLogger(__name__)
CANCELLED_BY_POS = 2

LIB_NAME = "libsix_odoo_w.dll" if IS_WINDOWS else "libsix_odoo_l.so"
TIMAPI = import_ctypes_library("tim", LIB_NAME)

TIMAPI.six_cancel_transaction.argtypes = [ctypes.c_void_p]

TIMAPI.six_perform_transaction.argtypes = [
    ctypes.c_void_p,
    ctypes.c_char_p,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.POINTER(ctypes.c_int),
    ctypes.c_char_p,
]

TIMAPI.six_terminal_balance.argtypes = [
    ctypes.c_void_p,
    ctypes.c_char_p,
    ctypes.POINTER(ctypes.c_int),
]


class SixDriver(CtypesTerminalDriver):
    connection_type = "tim"

    def __init__(self, identifier, device) -> None:
        super().__init__(identifier, device)
        self.device_name = "Six terminal %s" % self.device_identifier
        self.device_manufacturer = "Six"

    def processTransaction(self, transaction):
        if transaction["amount"] <= 0:
            return self.send_status(
                error="The terminal cannot process negative or null transaction amounts.",
                request_data=transaction,
            )
        elif transaction["transactionType"] not in ["Refund", "Payment"]:
            return self.send_status(
                error="Invalid transaction type.", request_data=transaction
            )

        self.send_status(stage="WaitingForCard", request_data=transaction)

        transaction_id = create_ctypes_string_buffer()
        merchant_receipt = create_ctypes_string_buffer()
        customer_receipt = create_ctypes_string_buffer()
        card_number = create_ctypes_string_buffer()
        card_brand = create_ctypes_string_buffer()
        error_code = ctypes.c_int(0)
        error = create_ctypes_string_buffer()

        try:
            _logger.info("Start transaction #%s", transaction)
            result = TIMAPI.six_perform_transaction(
                self.dev,
                str(transaction["posId"]).encode(),
                ctypes.c_int(transaction["userId"]),
                ctypes.c_int(1)
                if transaction["transactionType"] == "Payment"
                else ctypes.c_int(2),
                ctypes.c_int(transaction["amount"]),
                transaction["currency"].encode(),
                transaction_id,
                merchant_receipt,
                customer_receipt,
                card_number,
                card_brand,
                ctypes.byref(error_code),
                error,
            )
            if result == 1:
                _logger.info("Successfully finished transaction #%s", transaction)
                self.send_status(
                    response="Approved",
                    ticket=customer_receipt.value.decode(),
                    ticket_merchant=merchant_receipt.value.decode(),
                    card=card_brand.value.decode(),
                    card_no=card_number.value.decode(),
                    transaction_id=transaction_id.value.decode(),
                    request_data=transaction,
                )
            elif result == 0:
                if error_code.value == CANCELLED_BY_POS:
                    sleep(3)
                    _logger.info("Transaction #%s cancelled by PoS user", transaction)
                    self.send_status(stage="Cancel", request_data=transaction)
                    _logger.info("Transaction %s cancelled by Odoo PoS", transaction)
                else:
                    error_message = f"{error_code.value}: {error.value.decode()}"
                    _logger.info(
                        "Transaction #%s failed with error: %s",
                        transaction,
                        error_message,
                    )
                    self.send_status(error=error_message, request_data=transaction)
            elif result == -1:
                _logger.warning(
                    "Terminal disconnected during transaction #%s", transaction
                )
                self.send_status(disconnected=True)
        except OSError:
            _logger.exception(
                "Failed to perform Six transaction. Check for potential segmentation faults"
            )
            sleep(3)
            self.send_status(
                error="An error has occured. Check the transaction result manually with the payment provider",
                request_data=transaction,
            )

    def cancelTransaction(self, transaction):
        self.send_status(stage="waitingCancel", request_data=transaction)
        if not self.terminal_busy:
            return self.send_status(stage="Cancel", request_data=transaction)
        try:
            _logger.info("cancel transaction request for %s", transaction)
            if not TIMAPI.six_cancel_transaction(
                ctypes.cast(self.dev, ctypes.c_void_p)
            ):
                _logger.info("Transaction #%s could not be cancelled", transaction)
                self.send_status(
                    stage="Cancel",
                    error="Transaction could not be cancelled",
                    request_data=transaction,
                )
        except OSError:
            _logger.exception(
                "Failed to cancel Six transaction. Check for potential segmentation faults."
            )
            sleep(3)
            self.send_status(
                error="An error has occured when cancelling Six transaction. Check the transaction result manually with the payment provider",
                request_data=transaction,
            )

    def six_terminal_balance(self, data):
        balance_receipt_buffer = create_ctypes_string_buffer()
        n_receipts = ctypes.c_int(0)
        try:
            _logger.info("Requesting terminal balance")
            result = TIMAPI.six_terminal_balance(
                self.dev, balance_receipt_buffer, ctypes.byref(n_receipts)
            )
            if result:
                _logger.info("Terminal balance request success")
                n_receipts_val = n_receipts.value
                receipt_val = balance_receipt_buffer.value.decode()
                if n_receipts_val > 1:
                    _logger.warning(
                        "%s receipts returned from terminal balance request, only the first will be used",
                        n_receipts_val,
                    )
                elif n_receipts_val == -1:
                    receipt_val += "\nTruncated receipt"
                    _logger.warning(
                        "The balance receipt was truncated, consider increasing the buffer size"
                    )
                self.send_status(request_data=data, ticket=receipt_val)
            else:
                _logger.info("Failed to get terminal balance")
                self.send_status(
                    error="Failed to get terminal balance", request_data=data
                )
        except OSError:
            _logger.exception(
                "Failed to get terminal balance. Check for potential segmentation faults."
            )
            self.send_status(
                error="An error has occured when requesting the terminal balance. Check the terminal manually",
                request_data=data,
            )
