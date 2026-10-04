"""Shared helpers: footprint loading, board setup, coordinates in mm."""
import pcbnew

import os
LIBS = os.environ.get('KICAD_FOOTPRINT_DIR', os.environ.get('KICAD10_FOOTPRINT_DIR', '/usr/share/kicad/footprints')).rstrip('/') + '/'
LOCAL = {}      # project footprint libraries: nickname -> .pretty path (eco.py fills it from env FP_LIBS)
MM = 1e6


def mm(v):
    return int(round(v * MM))


def pt(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def load_fp(lid):
    lib, name = lid.split(':')
    path = LOCAL.get(lib, LIBS + lib + '.pretty')
    f = pcbnew.FootprintLoad(path, name)
    if f is None:
        raise RuntimeError('footprint not found: ' + lid)
    f.SetFPID(pcbnew.LIB_ID(lib, name))
    return f


def courtyard(f, side_layer=None):
    """courtyard bbox (mm) of a placed footprint as (x0,y0,x1,y1)."""
    lay = pcbnew.B_CrtYd if f.IsFlipped() else pcbnew.F_CrtYd
    cy = f.GetCourtyard(lay)
    if cy.OutlineCount():
        b = cy.BBox()
    else:
        b = f.GetBoundingBox(False)
    return (b.GetLeft() / MM, b.GetTop() / MM, b.GetRight() / MM, b.GetBottom() / MM)
