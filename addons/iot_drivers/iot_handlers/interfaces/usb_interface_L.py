from usb import core

from odoo.addons.iot_drivers.interface import Interface


class USBInterface(Interface):
    connection_type = "usb"
    allow_unsupported = True

    @staticmethod
    def usb_matcher(dev) -> bool:
        if dev.bDeviceClass in [7, 9]:
            return False
        elif dev.bDeviceClass == 0:
            for conf in dev:
                for interface in conf:
                    if interface.bInterfaceClass == 7:
                        return False

        try:
            return dev.product != "USB2.0-Ser!"
        except ValueError:
            return True

    def get_devices(self):
        usb_devices = {}
        devs = core.find(find_all=True, custom_match=self.usb_matcher)
        cpt = 2
        for dev in devs:
            identifier = "usb_%04x:%04x" % (dev.idVendor, dev.idProduct)
            if identifier in usb_devices:
                identifier += "_%s" % cpt
                cpt += 1
            usb_devices[identifier] = dev
        return usb_devices
