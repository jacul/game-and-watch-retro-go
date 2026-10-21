"""Load or start the RAM helper in separate processes. Never program flash."""
import argparse
import logging
from .common import HELPER_ADDRESS, helper_firmware, make_connection, require


def run(stage, backend, device, firmware):
    require(stage in ('load', 'start'), 'Expected load or start')
    require(len(firmware) >= 8, 'Invalid helper image')
    opened = False
    try:
        backend.open()
        opened = True
        backend.set_frequency(100000)
        if stage == 'load':
            print('RESET:', backend('reset halt', decode=False))
            print('TARGET:', backend('targets', decode=False))
            print('REGISTERS:', backend('reg', decode=False))
            require(backend.read_uint32(0xE000ED00) == 0x411FC271, 'Unexpected CPU')
            backend.write_memory(HELPER_ADDRESS, firmware)
        require(backend.read_memory(HELPER_ADDRESS, len(firmware)) == firmware,
                'RAM helper readback mismatch; stopped before execution')
        if stage == 'load':
            print('RAM helper verified. It has not been started. Flash is unchanged.')
            return
        # Starting in a second process was reliable on the tested device.
        device.write_uint32('status', 0)
        device.write_uint32('status_override', 0)
        msp, pc = (int.from_bytes(firmware[i:i + 4], 'little') for i in (0, 4))
        backend.write_register('msp', msp)
        backend.write_register('pc', pc)
        print('MSP:', hex(backend.read_register('msp')))
        print('PC:', hex(backend.read_register('pc')))
        backend.resume()
        device.wait_for_idle()
        print('RAM HELPER IDLE. Flash is unchanged.')
    finally:
        if opened:
            backend.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('load', 'start'))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    backend, device = make_connection()
    run(args.stage, backend, device, helper_firmware())


if __name__ == '__main__':
    main()
