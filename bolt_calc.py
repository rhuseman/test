"""Bolt-in-tension calculator: static strength and fatigue.

Method and data follow Shigley's Mechanical Engineering Design, Chapter 8
(tensile stress area, SAE/ISO bolt strengths, fully corrected bolt
endurance strengths, preloaded-joint fatigue with the Goodman criterion).

Units: inch grades (SAE J429) use in, lbf, psi.
       Metric classes (ISO 898-1) use mm, N, MPa.

This is an educational tool. Verify results before using them for design.
"""

import argparse
import math
import sys
from dataclasses import dataclass
from fractions import Fraction

# --- Thread data ------------------------------------------------------------

# Nominal diameter (in) -> threads per inch.
UNC = {
    0.25: 20, 0.3125: 18, 0.375: 16, 0.4375: 14, 0.5: 13, 0.5625: 12,
    0.625: 11, 0.75: 10, 0.875: 9, 1.0: 8, 1.125: 7, 1.25: 7, 1.375: 6,
    1.5: 6,
}
UNF = {
    0.25: 28, 0.3125: 24, 0.375: 24, 0.4375: 20, 0.5: 20, 0.5625: 18,
    0.625: 18, 0.75: 16, 0.875: 14, 1.0: 12, 1.125: 12, 1.25: 12,
    1.375: 12, 1.5: 12,
}
# Nominal diameter (mm) -> pitch (mm).
METRIC_COARSE = {
    5: 0.8, 6: 1.0, 8: 1.25, 10: 1.5, 12: 1.75, 14: 2.0, 16: 2.0,
    20: 2.5, 24: 3.0, 30: 3.5, 36: 4.0,
}
METRIC_FINE = {
    8: 1.0, 10: 1.25, 12: 1.25, 14: 1.5, 16: 1.5, 20: 1.5, 24: 2.0,
    30: 2.0, 36: 3.0,
}

# --- Material data ----------------------------------------------------------


@dataclass(frozen=True)
class Strength:
    d_min: float   # applicable size range, in or mm (inclusive)
    d_max: float
    proof: float   # Sp, psi or MPa
    yield_: float  # Sy
    ultimate: float  # Sut


# Shigley Table 8-9 (SAE J429), psi.
SAE_GRADES = {
    "1": [Strength(0.25, 1.5, 33e3, 36e3, 60e3)],
    "2": [Strength(0.25, 0.75, 55e3, 57e3, 74e3),
          Strength(0.875, 1.5, 33e3, 36e3, 60e3)],
    "5": [Strength(0.25, 1.0, 85e3, 92e3, 120e3),
          Strength(1.125, 1.5, 74e3, 81e3, 105e3)],
    "7": [Strength(0.25, 1.5, 105e3, 115e3, 133e3)],
    "8": [Strength(0.25, 1.5, 120e3, 130e3, 150e3)],
}
# Shigley Table 8-11 / ISO 898-1, MPa.
ISO_CLASSES = {
    "4.6": [Strength(5, 36, 225, 240, 400)],
    "4.8": [Strength(1.6, 16, 310, 340, 420)],
    "5.8": [Strength(5, 24, 380, 420, 520)],
    "8.8": [Strength(1.6, 15.99, 580, 640, 800),
            Strength(16, 36, 600, 660, 830)],
    "9.8": [Strength(1.6, 16, 650, 720, 900)],
    "10.9": [Strength(5, 36, 830, 940, 1040)],
    "12.9": [Strength(1.6, 36, 970, 1100, 1220)],
}

# Shigley Table 8-17: fully corrected endurance strength, ROLLED threads,
# includes the thread stress-concentration factor.
ENDURANCE_ROLLED = {
    ("5", "small"): 18.6e3, ("5", "large"): 16.3e3,
    ("7", None): 20.6e3, ("8", None): 23.2e3,
    ("8.8", None): 129, ("9.8", None): 140,
    ("10.9", None): 162, ("12.9", None): 190,
}
# Shigley Table 8-16: fatigue stress-concentration factor Kf.
KF = {  # (low strength?, threads) -> Kf
    (True, "rolled"): 2.2, (True, "cut"): 2.8,
    (False, "rolled"): 3.0, (False, "cut"): 3.8,
}
LOW_STRENGTH = {"1", "2", "4.6", "4.8", "5.8"}
# Table 8-17 values equal ~0.155*Sut for rolled threads with Kf = 3.0.
# Used to estimate grades that Table 8-17 does not list.
SE_RATIO_AT_KF3 = 0.155

# Shigley Table 8-8: member elastic modulus (psi, MPa) and Wileman
# constants A, B for km = E*d*A*exp(B*d/l).
MEMBERS = {
    "steel": (30.0e6, 206.8e3, 0.78715, 0.62873),
    "aluminum": (10.3e6, 71.0e3, 0.79670, 0.63816),
    "copper": (17.3e6, 118.6e3, 0.79568, 0.63553),
    "cast-iron": (14.5e6, 100.0e3, 0.77871, 0.61616),
}
BOLT_E = {"inch": 30.0e6, "metric": 206.8e3}  # all listed grades are steel


# --- Calculations -----------------------------------------------------------


def parse_size(size):
    """'1/2', '0.5', '1-1/4' -> inches (float); 'M12' -> mm (float)."""
    s = size.strip().upper()
    if s.startswith("M"):
        return float(s[1:]), "metric"
    s = s.replace('"', "").replace(" ", "-")
    whole, _, frac = s.rpartition("-") if "/" in s else ("", "", s)
    return float((Fraction(whole) if whole else 0) + Fraction(frac)), "inch"


def tensile_stress_area(d, system, series):
    """Returns (At, pitch). At in in^2 or mm^2."""
    if system == "inch":
        table = UNC if series == "coarse" else UNF
        if d not in table:
            raise ValueError(f"No {series} inch thread for d = {d} in. "
                             f"Available: {sorted(table)}")
        p = 1.0 / table[d]
        return math.pi / 4 * (d - 0.9743 * p) ** 2, p
    table = METRIC_COARSE if series == "coarse" else METRIC_FINE
    if d not in table:
        raise ValueError(f"No {series} metric thread for M{d:g}. "
                         f"Available: {sorted(table)}")
    p = table[d]
    return math.pi / 4 * (d - 0.9382 * p) ** 2, p


def material_strength(grade, d, system):
    grades = SAE_GRADES if system == "inch" else ISO_CLASSES
    if grade not in grades:
        kind = "SAE grade" if system == "inch" else "ISO class"
        raise ValueError(f"Unknown {kind} '{grade}'. "
                         f"Available: {', '.join(grades)}")
    for s in grades[grade]:
        if s.d_min <= d <= s.d_max:
            return s
    raise ValueError(f"Grade {grade} is not specified for this size.")


def endurance_strength(grade, d, threads, sut):
    """Returns (Se, note). Se already includes the thread notch effect."""
    low = grade in LOW_STRENGTH
    key = (grade, ("small" if d <= 1.0 else "large") if grade == "5" else None)
    if key in ENDURANCE_ROLLED:
        se = ENDURANCE_ROLLED[key]
        note = "Shigley Table 8-17"
    else:
        se = SE_RATIO_AT_KF3 * sut * KF[(False, "rolled")] / KF[(low, "rolled")]
        note = "estimated from Sut (grade not in Table 8-17)"
    if threads == "cut":
        se *= KF[(low, "rolled")] / KF[(low, "cut")]
        note += ", scaled for cut threads by Kf ratio"
    return se, note


def thread_length(d, bolt_length, system):
    """Standard thread length LT (Shigley Table 8-7)."""
    if system == "inch":
        return 2 * d + (0.25 if bolt_length <= 6 else 0.5)
    if bolt_length <= 125:
        return 2 * d + 6
    return 2 * d + (12 if bolt_length <= 200 else 25)


@dataclass
class Stiffness:
    kb: float  # bolt stiffness, lbf/in or N/mm
    km: float  # member stiffness
    c: float   # kb / (kb + km)
    ld: float  # unthreaded length in grip
    lt: float  # threaded length in grip


def joint_constant(d, at, system, grip, bolt_length, member="steel"):
    """Joint constant C from bolt and member stiffness.

    Assumes a through-bolt with nut, both members of the same material,
    and grip = total clamped thickness including washers.
    """
    if member not in MEMBERS:
        raise ValueError(f"Unknown member material '{member}'. "
                         f"Available: {', '.join(MEMBERS)}")
    if grip <= 0 or bolt_length < grip:
        raise ValueError("Need grip > 0 and bolt length >= grip.")
    ad = math.pi / 4 * d ** 2
    ld = min(max(bolt_length - thread_length(d, bolt_length, system), 0), grip)
    lt = grip - ld
    kb = ad * at * BOLT_E[system] / (ad * lt + at * ld)  # Shigley eq. 8-17
    e_psi, e_mpa, a, b = MEMBERS[member]
    e = e_psi if system == "inch" else e_mpa
    km = e * d * a * math.exp(b * d / grip)  # Wileman, Shigley eq. 8-23
    return Stiffness(kb, km, kb / (kb + km), ld, lt)


@dataclass
class Result:
    at: float
    pitch: float
    strength: Strength
    se: float
    se_note: str
    preload: float
    c: float
    bolt_load_max: float
    stress_max: float
    sigma_a: float
    sigma_m: float
    n_yield: float
    n_proof: float
    n_ultimate: float
    n_fatigue: float
    n_separation: float  # inf when there is no joint
    stiffness: Stiffness = None  # set when C was calculated


def analyze(size, grade, series="coarse", threads="rolled",
            load_max=0.0, load_min=0.0, preload=None,
            preload_fraction=0.75, c=0.25, joint=True,
            grip=None, bolt_length=None, member="steel"):
    """Analyze a bolt under an external tensile load cycling load_min..load_max.

    joint=True : preloaded clamped joint (Shigley 8-11). Bolt share of the
                 external load is C = kb/(kb+km). preload defaults to
                 preload_fraction * proof load. If grip and bolt_length
                 are given, C is calculated and the c argument is ignored.
    joint=False: bare bolt carrying the full load (C = 1, no preload).
    """
    d, system = parse_size(size)
    at, pitch = tensile_stress_area(d, system, series)
    st = material_strength(grade, d, system)
    se, se_note = endurance_strength(grade, d if system == "inch" else 0,
                                     threads, st.ultimate)
    stiffness = None
    if not joint:
        c, fi = 1.0, 0.0
    else:
        if grip is not None or bolt_length is not None:
            if grip is None or bolt_length is None:
                raise ValueError("Give both grip and bolt length.")
            stiffness = joint_constant(d, at, system, grip, bolt_length, member)
            c = stiffness.c
        fi = preload if preload is not None else preload_fraction * st.proof * at

    bolt_max = fi + c * load_max
    stress_max = bolt_max / at
    sigma_a = c * (load_max - load_min) / (2 * at)
    sigma_m = (fi + c * (load_max + load_min) / 2) / at
    # Load line starts at the minimum stress and rises with slope 1
    # (Shigley eq. 8-38 generalised to load_min >= 0). Goodman intersection:
    sigma_min = sigma_m - sigma_a
    if sigma_a > 0:
        s_a = se * (st.ultimate - sigma_min) / (st.ultimate + se)
        n_f = s_a / sigma_a
    else:
        n_f = math.inf
    external_max = load_max * (1 - c)
    n_sep = fi / external_max if joint and external_max > 0 else math.inf

    def factor(s):
        return s / stress_max if stress_max > 0 else math.inf

    return Result(at, pitch, st, se, se_note, fi, c, bolt_max, stress_max,
                  sigma_a, sigma_m, factor(st.yield_), factor(st.proof),
                  factor(st.ultimate), n_f, n_sep, stiffness)


# --- Command line -----------------------------------------------------------


def report(r, system):
    su, fu, au, lu = (("psi", "lbf", "in^2", "in") if system == "inch"
                      else ("MPa", "N", "mm^2", "mm"))

    def verdict(n):
        return "OK" if n >= 1.0 else "FAILS"

    def fmt(n):
        return "  inf" if math.isinf(n) else f"{n:5.2f}"

    lines = [
        f"Tensile stress area At : {r.at:.4g} {au} (pitch {r.pitch:.4g} {lu})",
        f"Proof strength Sp      : {r.strength.proof:,.0f} {su}",
        f"Yield strength Sy      : {r.strength.yield_:,.0f} {su}",
        f"Ultimate strength Sut  : {r.strength.ultimate:,.0f} {su}",
        f"Endurance strength Se  : {r.se:,.0f} {su} ({r.se_note})",
        "",
        f"Preload Fi             : {r.preload:,.0f} {fu}",
    ]
    if r.stiffness:
        k = r.stiffness
        ku = "lbf/in" if system == "inch" else "N/mm"
        lines += [
            f"Grip: shank {k.ld:.4g} {lu}, threads {k.lt:.4g} {lu}",
            f"Bolt stiffness kb      : {k.kb:,.0f} {ku}",
            f"Member stiffness km    : {k.km:,.0f} {ku}",
        ]
    lines += [
        f"Joint constant C       : {r.c:.3g}"
        f"{' (calculated)' if r.stiffness else ''}",
        f"Max bolt load          : {r.bolt_load_max:,.0f} {fu}",
        f"Max bolt stress        : {r.stress_max:,.0f} {su}",
        f"Alternating stress     : {r.sigma_a:,.0f} {su}",
        f"Mean stress            : {r.sigma_m:,.0f} {su}",
        "",
        "Safety factors (>= 1.0 required; use your own design margin):",
        f"  vs yield     {fmt(r.n_yield)}  {verdict(r.n_yield)}",
        f"  vs proof     {fmt(r.n_proof)}  {verdict(r.n_proof)}",
        f"  vs ultimate  {fmt(r.n_ultimate)}  {verdict(r.n_ultimate)}",
        f"  fatigue      {fmt(r.n_fatigue)}  {verdict(r.n_fatigue)}"
        "  (Goodman, infinite life)",
        f"  separation   {fmt(r.n_separation)}  {verdict(r.n_separation)}",
    ]
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Bolt in tension: static strength and fatigue "
                    "(Shigley Ch. 8).")
    p.add_argument("--size", required=True,
                   help="'1/2', '1-1/4' (inch) or 'M12' (metric)")
    p.add_argument("--grade", required=True,
                   help="SAE 1/2/5/7/8 or ISO 4.6/4.8/5.8/8.8/9.8/10.9/12.9")
    p.add_argument("--series", choices=["coarse", "fine"], default="coarse",
                   help="coarse = UNC / metric coarse, fine = UNF / metric fine")
    p.add_argument("--threads", choices=["rolled", "cut"], default="rolled")
    p.add_argument("--load-max", type=float, required=True,
                   help="max external tensile load (lbf or N)")
    p.add_argument("--load-min", type=float, default=0.0,
                   help="min external tensile load (default 0)")
    p.add_argument("--preload", type=float,
                   help="preload Fi (default: 0.75 x proof load)")
    p.add_argument("--preload-fraction", type=float, default=0.75,
                   help="Fi as fraction of proof load (0.75 reusable, "
                        "0.90 permanent)")
    p.add_argument("--grip", type=float,
                   help="clamped thickness incl. washers (in or mm); "
                        "with --bolt-length, calculates C")
    p.add_argument("--bolt-length", type=float,
                   help="bolt length under the head (in or mm)")
    p.add_argument("--member", choices=list(MEMBERS), default="steel",
                   help="clamped member material (default steel)")
    p.add_argument("--c", type=float, default=0.25,
                   help="joint constant kb/(kb+km), default 0.25 (ASSUMED)")
    p.add_argument("--no-joint", action="store_true",
                   help="bare bolt: no preload, bolt carries full load")
    a = p.parse_args(argv)
    args = argv if argv is not None else sys.argv[1:]
    c_given = any(x == "--c" or x.startswith("--c=") for x in args)
    if c_given and a.grip is not None:
        p.error("Give either --c or --grip/--bolt-length, not both.")

    try:
        r = analyze(a.size, a.grade, a.series, a.threads, a.load_max,
                    a.load_min, a.preload, a.preload_fraction, a.c,
                    joint=not a.no_joint, grip=a.grip,
                    bolt_length=a.bolt_length, member=a.member)
    except ValueError as e:
        p.error(str(e))
    print(report(r, parse_size(a.size)[1]))
    if not a.no_joint and not c_given and r.stiffness is None:
        print("\nNote: C = 0.25 is an assumed default. Calculate it with "
              "--grip and --bolt-length, or give --c.")


if __name__ == "__main__":
    main()
