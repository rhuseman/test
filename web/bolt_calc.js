// JavaScript port of bolt_calc.py for the web page.
// Must give the same results as the Python version: test_web_port.py checks
// every case in golden.json (generated from Python by make_golden.py).
(function (root) {
  "use strict";

  const UNC = { 0.25: 20, 0.3125: 18, 0.375: 16, 0.4375: 14, 0.5: 13, 0.5625: 12,
    0.625: 11, 0.75: 10, 0.875: 9, 1: 8, 1.125: 7, 1.25: 7, 1.375: 6, 1.5: 6 };
  const UNF = { 0.25: 28, 0.3125: 24, 0.375: 24, 0.4375: 20, 0.5: 20, 0.5625: 18,
    0.625: 18, 0.75: 16, 0.875: 14, 1: 12, 1.125: 12, 1.25: 12, 1.375: 12, 1.5: 12 };
  const METRIC_COARSE = { 5: 0.8, 6: 1.0, 8: 1.25, 10: 1.5, 12: 1.75, 14: 2.0,
    16: 2.0, 20: 2.5, 24: 3.0, 30: 3.5, 36: 4.0 };
  const METRIC_FINE = { 8: 1.0, 10: 1.25, 12: 1.25, 14: 1.5, 16: 1.5, 20: 1.5,
    24: 2.0, 30: 2.0, 36: 3.0 };

  const S = (d_min, d_max, proof, yield_, ultimate) =>
    ({ d_min, d_max, proof, yield_, ultimate });
  // Shigley Table 8-9 (SAE J429), psi.
  const SAE_GRADES = {
    "1": [S(0.25, 1.5, 33e3, 36e3, 60e3)],
    "2": [S(0.25, 0.75, 55e3, 57e3, 74e3), S(0.875, 1.5, 33e3, 36e3, 60e3)],
    "5": [S(0.25, 1.0, 85e3, 92e3, 120e3), S(1.125, 1.5, 74e3, 81e3, 105e3)],
    "7": [S(0.25, 1.5, 105e3, 115e3, 133e3)],
    "8": [S(0.25, 1.5, 120e3, 130e3, 150e3)],
  };
  // Shigley Table 8-11 / ISO 898-1, MPa.
  const ISO_CLASSES = {
    "4.6": [S(5, 36, 225, 240, 400)],
    "4.8": [S(1.6, 16, 310, 340, 420)],
    "5.8": [S(5, 24, 380, 420, 520)],
    "8.8": [S(1.6, 15.99, 580, 640, 800), S(16, 36, 600, 660, 830)],
    "9.8": [S(1.6, 16, 650, 720, 900)],
    "10.9": [S(5, 36, 830, 940, 1040)],
    "12.9": [S(1.6, 36, 970, 1100, 1220)],
  };
  // Shigley Table 8-17, rolled threads.
  const ENDURANCE_ROLLED = {
    "5|small": 18.6e3, "5|large": 16.3e3, "7|": 20.6e3, "8|": 23.2e3,
    "8.8|": 129, "9.8|": 140, "10.9|": 162, "12.9|": 190,
  };
  // Shigley Table 8-16.
  const KF = { "true|rolled": 2.2, "true|cut": 2.8, "false|rolled": 3.0, "false|cut": 3.8 };
  const LOW_STRENGTH = new Set(["1", "2", "4.6", "4.8", "5.8"]);
  const SE_RATIO_AT_KF3 = 0.155;
  // Shigley Table 8-8: [E psi, E MPa, A, B].
  const MEMBERS = {
    "steel": [30.0e6, 206.8e3, 0.78715, 0.62873],
    "aluminum": [10.3e6, 71.0e3, 0.79670, 0.63816],
    "copper": [17.3e6, 118.6e3, 0.79568, 0.63553],
    "cast-iron": [14.5e6, 100.0e3, 0.77871, 0.61616],
  };
  const BOLT_E = { inch: 30.0e6, metric: 206.8e3 };

  function parseSize(size) {
    let s = String(size).trim().toUpperCase();
    if (s.startsWith("M")) return [parseFloat(s.slice(1)), "metric"];
    s = s.replace(/"/g, "").replace(/ /g, "-");
    if (!s.includes("/")) return [parseFloat(s), "inch"];
    const i = s.lastIndexOf("-");
    const whole = i >= 0 ? parseFloat(s.slice(0, i)) : 0;
    const [n, d] = s.slice(i + 1).split("/").map(Number);
    return [whole + n / d, "inch"];
  }

  function tensileStressArea(d, system, series) {
    const table = system === "inch"
      ? (series === "coarse" ? UNC : UNF)
      : (series === "coarse" ? METRIC_COARSE : METRIC_FINE);
    if (!(d in table)) {
      const name = system === "inch" ? `d = ${d} in` : `M${d}`;
      throw new Error(`No ${series} thread for ${name}.`);
    }
    if (system === "inch") {
      const p = 1 / table[d];
      return [Math.PI / 4 * (d - 0.9743 * p) ** 2, p];
    }
    const p = table[d];
    return [Math.PI / 4 * (d - 0.9382 * p) ** 2, p];
  }

  function materialStrength(grade, d, system) {
    const grades = system === "inch" ? SAE_GRADES : ISO_CLASSES;
    if (!(grade in grades)) throw new Error(`Unknown grade '${grade}'.`);
    for (const s of grades[grade]) if (s.d_min <= d && d <= s.d_max) return s;
    throw new Error(`Grade ${grade} is not specified for this size.`);
  }

  function enduranceStrength(grade, d, threads, sut) {
    const low = LOW_STRENGTH.has(grade);
    const key = grade + "|" + (grade === "5" ? (d <= 1.0 ? "small" : "large") : "");
    let se, note;
    if (key in ENDURANCE_ROLLED) {
      se = ENDURANCE_ROLLED[key];
      note = "Shigley Table 8-17";
    } else {
      se = SE_RATIO_AT_KF3 * sut * KF["false|rolled"] / KF[low + "|rolled"];
      note = "estimated from Sut (grade not in Table 8-17)";
    }
    if (threads === "cut") {
      se *= KF[low + "|rolled"] / KF[low + "|cut"];
      note += ", scaled for cut threads by Kf ratio";
    }
    return [se, note];
  }

  function threadLength(d, L, system) {
    if (system === "inch") return 2 * d + (L <= 6 ? 0.25 : 0.5);
    if (L <= 125) return 2 * d + 6;
    return 2 * d + (L <= 200 ? 12 : 25);
  }

  function jointConstant(d, at, system, grip, boltLength, member = "steel") {
    if (!(member in MEMBERS)) throw new Error(`Unknown member material '${member}'.`);
    if (!(grip > 0) || boltLength < grip) throw new Error("Need grip > 0 and bolt length >= grip.");
    const ad = Math.PI / 4 * d ** 2;
    const ld = Math.min(Math.max(boltLength - threadLength(d, boltLength, system), 0), grip);
    const lt = grip - ld;
    const kb = ad * at * BOLT_E[system] / (ad * lt + at * ld);
    const [ePsi, eMpa, a, b] = MEMBERS[member];
    const e = system === "inch" ? ePsi : eMpa;
    const km = e * d * a * Math.exp(b * d / grip);
    return { kb, km, c: kb / (kb + km), ld, lt };
  }

  // Same arguments and defaults as bolt_calc.analyze(), as an object.
  function analyze(o) {
    const {
      size, grade, series = "coarse", threads = "rolled", load_max = 0,
      load_min = 0, preload = null, preload_fraction = 0.75, joint = true,
      grip = null, bolt_length = null, member = "steel",
    } = o;
    let c = o.c ?? 0.25;
    const [d, system] = parseSize(size);
    const [at, pitch] = tensileStressArea(d, system, series);
    const st = materialStrength(grade, d, system);
    const [se, se_note] = enduranceStrength(grade, system === "inch" ? d : 0, threads, st.ultimate);
    let stiffness = null, fi;
    if (!joint) {
      c = 1; fi = 0;
    } else {
      if (grip != null || bolt_length != null) {
        if (grip == null || bolt_length == null) throw new Error("Give both grip and bolt length.");
        stiffness = jointConstant(d, at, system, grip, bolt_length, member);
        c = stiffness.c;
      }
      fi = preload != null ? preload : preload_fraction * st.proof * at;
    }
    const bolt_load_max = fi + c * load_max;
    const stress_max = bolt_load_max / at;
    const sigma_a = c * (load_max - load_min) / (2 * at);
    const sigma_m = (fi + c * (load_max + load_min) / 2) / at;
    const sigma_min = sigma_m - sigma_a;
    const n_fatigue = sigma_a > 0
      ? se * (st.ultimate - sigma_min) / (st.ultimate + se) / sigma_a
      : Infinity;
    const external_max = load_max * (1 - c);
    const n_separation = joint && external_max > 0 ? fi / external_max : Infinity;
    const bolt_share = c * load_max;
    const n_load = bolt_share > 0 ? (st.proof * at - fi) / bolt_share : Infinity;
    const factor = s => stress_max > 0 ? s / stress_max : Infinity;
    return {
      system, d, at, pitch, strength: st, se, se_note, preload: fi, c,
      bolt_load_max, stress_max, sigma_a, sigma_m,
      n_yield: factor(st.yield_), n_proof: factor(st.proof),
      n_ultimate: factor(st.ultimate), n_fatigue, n_separation, n_load, stiffness,
    };
  }

  const api = {
    UNC, UNF, METRIC_COARSE, METRIC_FINE, SAE_GRADES, ISO_CLASSES, MEMBERS,
    parseSize, tensileStressArea, materialStrength, enduranceStrength,
    threadLength, jointConstant, analyze,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.BoltCalc = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
