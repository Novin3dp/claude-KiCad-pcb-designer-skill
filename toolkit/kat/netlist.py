"""Minimal KiCad netlist (.net) parser -> components & nets."""
import re

def tokenize(s):
    for m in re.finditer(r'\(|\)|"((?:[^"\\]|\\.)*)"|[^\s()"]+', s):
        t = m.group(0)
        if t in '()':
            yield t
        elif t.startswith('"'):
            yield ('S', m.group(1).replace('\\"', '"'))
        else:
            yield ('S', t)

def parse(s):
    stack = [[]]
    for t in tokenize(s):
        if t == '(':
            stack.append([])
        elif t == ')':
            x = stack.pop(); stack[-1].append(x)
        else:
            stack[-1].append(t[1])
    return stack[0][0]

def find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]

def val(node, key, default=None):
    f = find(node, key)
    return f[0][1] if f and len(f[0]) > 1 else default

def load(path):
    root = parse(open(path).read())
    comps = {}
    for c in find(find(root, 'components')[0], 'comp'):
        ref = val(c, 'ref')
        props = {val(p, 'name'): val(p, 'value', '') for p in find(c, 'property')}
        comps[ref] = dict(ref=ref, value=val(c, 'value'), footprint=val(c, 'footprint'),
                          sheet=props.get('Sheetname', ''), dnp='dnp' in props)
    nets = {}
    for n in find(find(root, 'nets')[0], 'net'):
        name = val(n, 'name')
        nets[name] = [(val(x, 'ref'), val(x, 'pin')) for x in find(n, 'node')]
    return comps, nets
