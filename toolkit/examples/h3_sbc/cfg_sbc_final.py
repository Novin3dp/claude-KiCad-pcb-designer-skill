"""final connectivity pass: the plane rails are routed like signals so that islands (pads / stub-via groups whose
inner-layer pour was cut off) get joined to the main copper by real tracks."""
from cfg_sbc import *          # noqa
import cfg_sbc as _B
PLANE_NETS = {'VCC_DRAM'}
PLANE_STUBS = False


def width(net, cls):
    s = short(net)
    if s in ('VCC_3V3', 'VDD_SYS', 'VDD_CPUX', 'GND'):
        return float(__import__('os').environ.get('FW', 0.25))
    return _B.width(net, cls)


def route_net(net, cls):
    s = short(net)
    return s not in PLANE_NETS and s != 'NC' and not net.startswith('unconnected')
