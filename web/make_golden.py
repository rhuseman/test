"""Generate golden.json: reference results from bolt_calc.py for the JS port.

Run from the repo root after changing bolt_calc.py:
    python3 web/make_golden.py
"""
import itertools
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bolt_calc as bc  # noqa: E402

FIELDS = ["at", "pitch", "se", "preload", "c", "bolt_load_max", "stress_max",
          "sigma_a", "sigma_m", "n_yield", "n_proof", "n_ultimate",
          "n_fatigue", "n_separation"]


def num(x):
    return "inf" if math.isinf(x) else x


def cases():
    inch_sizes = [str(d) for d in bc.UNC] + ["1/2", "1-1/4"]
    metric_sizes = [f"M{d}" for d in bc.METRIC_COARSE]
    systems = [(inch_sizes, list(bc.SAE_GRADES), [5000, 20000], [1.5, 6.0]),
               (metric_sizes, list(bc.ISO_CLASSES), [20000, 90000], [30, 150])]
    joints = [{"joint": False}, {"c": 0.3},
              {"grip": None}, {"preload_fraction": 0.9, "c": 0.2}]
    for sizes, grades, loads, grips in systems:
        for size, grade, series, threads, load, j in itertools.product(
                sizes, grades, ["coarse", "fine"], ["rolled", "cut"],
                loads, joints):
            kw = dict(size=size, grade=grade, series=series, threads=threads,
                      load_max=load, load_min=load / 4, **j)
            if "grip" in kw:
                for g, member in zip(grips, ["steel", "aluminum"]):
                    yield dict(kw, grip=g, bolt_length=g * 1.4, member=member)
            else:
                yield kw


out = []
for kw in cases():
    try:
        r = bc.analyze(**kw)
    except ValueError:
        out.append({"input": kw, "error": True})
        continue
    res = {f: num(getattr(r, f)) for f in FIELDS}
    res.update(proof=r.strength.proof, yield_=r.strength.yield_,
               ultimate=r.strength.ultimate, se_note=r.se_note)
    if r.stiffness:
        res.update(kb=r.stiffness.kb, km=r.stiffness.km)
    out.append({"input": kw, "expected": res})

path = os.path.join(os.path.dirname(__file__), "golden.json")
with open(path, "w") as f:
    json.dump(out, f, indent=0)
print(f"Wrote {len(out)} cases to {path}")
