"""remove unlocked copper of nets matching a regex. usage: rip_nets.py IN OUT REGEX"""
import sys, re, pcbnew
b = pcbnew.LoadBoard(sys.argv[1]); rx = re.compile(sys.argv[3]); rm = []
for t in b.GetTracks():
    if rx.match(t.GetNetname()) and not t.IsLocked():
        rm.append(t)
nets = sorted(set(t.GetNetname() for t in rm))
for t in rm:
    b.Remove(t)
b.Save(sys.argv[2]); print('ripped', len(rm), 'items of', len(nets), 'nets')
