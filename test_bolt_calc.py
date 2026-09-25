import math
import unittest

from bolt_calc import (analyze, joint_constant, parse_size,
                       tensile_stress_area, thread_length)


class TensileStressArea(unittest.TestCase):
    # Reference values: Shigley Tables 8-1 and 8-2.
    def test_inch(self):
        self.assertAlmostEqual(tensile_stress_area(0.5, "inch", "coarse")[0],
                               0.1419, places=4)
        self.assertAlmostEqual(tensile_stress_area(0.5, "inch", "fine")[0],
                               0.1599, places=3)
        self.assertAlmostEqual(tensile_stress_area(1.0, "inch", "coarse")[0],
                               0.606, places=3)

    def test_metric(self):
        self.assertAlmostEqual(tensile_stress_area(12, "metric", "coarse")[0],
                               84.3, places=1)
        self.assertAlmostEqual(tensile_stress_area(20, "metric", "coarse")[0],
                               245, places=0)

    def test_unknown_size(self):
        with self.assertRaises(ValueError):
            tensile_stress_area(0.6, "inch", "coarse")


class ParseSize(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(parse_size("1/2"), (0.5, "inch"))
        self.assertEqual(parse_size("1-1/4"), (1.25, "inch"))
        self.assertEqual(parse_size("0.75"), (0.75, "inch"))
        self.assertEqual(parse_size("m12"), (12.0, "metric"))


class JointStiffness(unittest.TestCase):
    def test_thread_length(self):
        # Shigley Table 8-7.
        self.assertEqual(thread_length(0.5, 2.0, "inch"), 1.25)
        self.assertEqual(thread_length(0.5, 8.0, "inch"), 1.5)
        self.assertEqual(thread_length(12, 45, "metric"), 30)
        self.assertEqual(thread_length(12, 150, "metric"), 36)
        self.assertEqual(thread_length(12, 250, "metric"), 49)

    def test_half_inch_steel(self):
        # Hand calculation: 1/2-13, grip 1.5 in, bolt 2.0 in, steel.
        # LT = 1.25 -> ld = 0.75, lt = 0.75
        # kb = Ad*At*E/(Ad*lt + At*ld) = 3.295e6 lbf/in       (eq. 8-17)
        # km = E*d*A*exp(B*d/l) = 30e6*0.5*0.78715*e^0.20958 = 1.456e7
        at = tensile_stress_area(0.5, "inch", "coarse")[0]
        k = joint_constant(0.5, at, "inch", grip=1.5, bolt_length=2.0)
        self.assertAlmostEqual(k.ld, 0.75)
        self.assertAlmostEqual(k.lt, 0.75)
        self.assertAlmostEqual(k.kb / 1e6, 3.295, places=3)
        self.assertAlmostEqual(k.km / 1e6, 14.56, places=2)
        self.assertAlmostEqual(k.c, 0.1845, places=3)

    def test_fully_threaded_in_grip(self):
        # Short bolt: thread length exceeds bolt length, so no shank in grip.
        k = joint_constant(0.5, 0.1419, "inch", grip=1.0, bolt_length=1.25)
        self.assertEqual(k.ld, 0)
        self.assertEqual(k.lt, 1.0)

    def test_softer_members_raise_c(self):
        at = tensile_stress_area(12, "metric", "coarse")[0]
        steel = joint_constant(12, at, "metric", 30, 45, "steel")
        alum = joint_constant(12, at, "metric", 30, 45, "aluminum")
        self.assertGreater(alum.c, steel.c)

    def test_bad_inputs(self):
        with self.assertRaises(ValueError):
            joint_constant(0.5, 0.1419, "inch", grip=2.0, bolt_length=1.5)
        with self.assertRaises(ValueError):
            joint_constant(0.5, 0.1419, "inch", 1.5, 2.0, member="wood")
        with self.assertRaises(ValueError):
            analyze("1/2", "5", load_max=5000, grip=1.5)


class Analysis(unittest.TestCase):
    def test_calculated_c_is_used(self):
        r = analyze("1/2", "5", load_max=5000, c=0.9,
                    grip=1.5, bolt_length=2.0)
        self.assertAlmostEqual(r.c, r.stiffness.c)
        self.assertAlmostEqual(r.c, 0.1845, places=3)

    def test_preloaded_joint_half_inch_grade5(self):
        # Hand calculation (Shigley 8-11 method):
        # At = 0.1419, Fi = 0.75*85000*0.1419 = 9046 lbf
        # sigma_a = 0.25*5000/(2*0.1419) = 4404 psi, sigma_i = 63750 psi
        # Sa = 18600*(120000-63750)/(120000+18600) = 7548 -> nf = 1.714
        # n0 = 9046 / (5000*0.75) = 2.41
        r = analyze("1/2", "5", load_max=5000, c=0.25)
        self.assertAlmostEqual(r.preload, 9046, delta=2)
        self.assertAlmostEqual(r.sigma_a, 4404, delta=2)
        self.assertAlmostEqual(r.n_fatigue, 1.714, places=2)
        self.assertAlmostEqual(r.n_separation, 2.41, places=2)
        self.assertAlmostEqual(r.n_proof, 85000 / r.stress_max, places=6)

    def test_bare_bolt_metric(self):
        # M12 class 8.8 without preload, 0..20 kN:
        # sigma_a = sigma_m = 20000/(2*84.27) = 118.7 MPa
        # Goodman with load line through origin: nf = 1/(sa/Se + sm/Sut)
        r = analyze("M12", "8.8", load_max=20000, joint=False)
        sa = 20000 / (2 * r.at)
        self.assertAlmostEqual(r.sigma_a, sa, places=6)
        expected = 1 / (sa / 129 + sa / 800)
        self.assertAlmostEqual(r.n_fatigue, expected, places=6)
        self.assertTrue(math.isinf(r.n_separation))

    def test_cut_threads_are_weaker(self):
        rolled = analyze("1/2", "8", load_max=5000)
        cut = analyze("1/2", "8", threads="cut", load_max=5000)
        self.assertAlmostEqual(cut.se, rolled.se * 3.0 / 3.8, places=6)
        self.assertLess(cut.n_fatigue, rolled.n_fatigue)

    def test_grade_size_range(self):
        big = analyze("1-1/4", "5", load_max=1000)
        self.assertEqual(big.strength.proof, 74e3)
        self.assertEqual(big.se, 16.3e3)

    def test_unknown_grade(self):
        with self.assertRaises(ValueError):
            analyze("1/2", "9", load_max=1000)


if __name__ == "__main__":
    unittest.main()
