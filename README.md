# Bolt tension calculator

Static strength and fatigue check for a bolt in tension, following
Shigley's *Mechanical Engineering Design*, Chapter 8. Educational tool:
verify results before using them for design.

## Usage

```
python3 bolt_calc.py --size 1/2 --grade 5 --load-max 5000
python3 bolt_calc.py --size M12 --grade 8.8 --load-max 20000 --no-joint
python3 bolt_calc.py --size 1/2 --grade 5 --load-max 5000 --grip 1.5 --bolt-length 2
python3 bolt_calc.py --help
```

| Input | Options |
|---|---|
| `--size` | `1/4` to `1-1/2` in, or `M5` to `M36` |
| `--grade` | SAE 1, 2, 5, 7, 8 or ISO 4.6, 4.8, 5.8, 8.8, 9.8, 10.9, 12.9 |
| `--series` | `coarse` (UNC / metric coarse) or `fine` (UNF / metric fine) |
| `--threads` | `rolled` or `cut` |
| `--load-max`, `--load-min` | External tensile load range (lbf or N) |
| `--preload`, `--preload-fraction` | Preload; default 0.75 x proof load |
| `--c` | Joint constant kb/(kb+km); default 0.25 is an assumption |
| `--grip`, `--bolt-length` | Clamped thickness incl. washers, and bolt length under head; calculates C instead of `--c` |
| `--member` | Clamped material: `steel`, `aluminum`, `copper`, `cast-iron` |
| `--no-joint` | Bare bolt: no preload, bolt carries the full load |

Output: tensile stress area, proof/yield/ultimate/endurance strengths,
and safety factors against yield, proof, ultimate, fatigue (Goodman,
infinite life) and joint separation.

## Limitations

- Endurance strengths for SAE 1/2 and ISO 4.6/4.8/5.8, and all cut-thread
  values, are estimates scaled from Shigley Tables 8-16/8-17.
- Calculated C uses Shigley eq. 8-17 (bolt) and Wileman eq. 8-23 (members):
  through-bolt with nut, both members the same material, standard thread
  length (Table 8-7). Not valid for tapped holes or mixed materials.
- Tension only: no shear, bending, or finite-life fatigue.

## Web version

`web/index.html` is an interactive page that uses `web/bolt_calc.js`, a
JavaScript port of the same math. `test_web_port.py` regenerates reference
results from the Python code (`web/make_golden.py`, about 6,000 cases) and
fails if the JavaScript gives a different answer. Requires Node.js.

## Tests

```
python3 -m unittest -v
```
