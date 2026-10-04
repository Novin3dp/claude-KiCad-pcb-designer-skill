#!/usr/bin/env python3
"""Readable summary of a kicad-cli DRC JSON report: unconnected pairs, counts per type, and every real violation
(zone-fill items skipped unless ZONES=1).   usage: drcsum.py REPORT.json"""
import json, collections, sys, os
d = json.load(open(sys.argv[1]))
fmt = lambda i: i['description'][:70] + '@(%.2f,%.2f)' % (i['pos']['x'], i['pos']['y'])
print('unconnected', len(d['unconnected_items']))
for u in d['unconnected_items']:
    print('  U', ' | '.join(fmt(i) for i in u['items']))
print(collections.Counter(v['type'] for v in d['violations']))
if d.get('schematic_parity'):
    print('parity', collections.Counter(v['type'] for v in d['schematic_parity']))
show = ('shorting_items', 'clearance', 'hole_to_hole', 'hole_clearance', 'tracks_crossing', 'solder_mask_bridge',
        'track_dangling', 'via_dangling', 'copper_edge_clearance', 'drill_out_of_range', 'via_diameter', 'track_width',
        'items_not_allowed', 'annular_width')
for v in d['violations']:
    if v['type'] in show and (os.environ.get('ZONES') or 'Zone' not in json.dumps(v)):
        print('  ', v['type'], ' | '.join(fmt(i) for i in v['items']))
