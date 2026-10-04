"""ncroute config for the demo board: route on F.Cu / B.Cu, GND and +3V3 come from the In1 / In2 planes."""
from cfg_template import *          # noqa  (kat/ is on ncroute's path)
PLANE_NETS = {'GND', '+3V3'}
DEFAULT_CLR = 0.20
CLASS_CLR = {'Default': 0.20}
VIA = (0.6, 0.3)
