"""Tests unitarios del motor de calculo ISO/IEC 27005:2018 Annex E.2."""
import pytest

from app.services.risk_engine import (
    DEFAULT_MATRIX,
    band_for,
    calc_level,
    calc_residual,
    clamp,
    color_for,
    control_reduction,
)


class TestClamp:
    def test_within_range(self):
        assert clamp(2) == 2

    def test_below_min(self):
        assert clamp(-1) == 0

    def test_above_max(self):
        assert clamp(10) == 4

    def test_boundary_values(self):
        assert clamp(0) == 0
        assert clamp(4) == 4

    def test_none_treated_as_zero(self):
        assert clamp(None) == 0


class TestCalcLevel:
    def test_matrix_minimum(self):
        assert calc_level(0, 0) == 0

    def test_matrix_maximum(self):
        assert calc_level(4, 4) == 8

    def test_iso_annex_e2_diagonal(self):
        """La diagonal principal debe seguir la matriz ISO 27005 Tabla E.2."""
        assert calc_level(0, 0) == DEFAULT_MATRIX[0][0]
        assert calc_level(1, 1) == DEFAULT_MATRIX[1][1]
        assert calc_level(2, 2) == DEFAULT_MATRIX[2][2]
        assert calc_level(3, 3) == DEFAULT_MATRIX[3][3]
        assert calc_level(4, 4) == DEFAULT_MATRIX[4][4]

    def test_symmetry(self):
        """La matriz por defecto es simetrica."""
        for i in range(5):
            for j in range(5):
                assert calc_level(i, j) == calc_level(j, i)

    def test_custom_matrix(self):
        custom = [[i + j for j in range(5)] for i in range(5)]
        assert calc_level(2, 3, custom) == 5

    def test_out_of_range_clamped(self):
        assert calc_level(-1, 6) == calc_level(0, 4)


class TestBandFor:
    def test_low_band(self):
        for level in range(3):
            assert band_for(level) == "low"

    def test_medium_band(self):
        for level in range(3, 6):
            assert band_for(level) == "medium"

    def test_high_band(self):
        for level in range(6, 9):
            assert band_for(level) == "high"


class TestColorFor:
    def test_returns_brand_token(self):
        assert color_for(0) == "brand-low"
        assert color_for(4) == "brand-medium"
        assert color_for(7) == "brand-high"


class TestControlReduction:
    def test_no_controls(self):
        assert control_reduction([]) == 0.0

    def test_single_perfect_control(self):
        """Un control con madurez maxima y contribucion plena -> 100% reduccion."""
        reduction = control_reduction([{"maturity": 5, "contribution": 1.0}])
        assert reduction == pytest.approx(1.0)

    def test_single_zero_maturity(self):
        """Un control sin madurez no aporta nada."""
        assert control_reduction([{"maturity": 0, "contribution": 1.0}]) == 0.0

    def test_multiple_controls_combine(self):
        """Dos controles con 50% eficacia cada uno producen ~75% reduccion combinada."""
        c = [{"maturity": 3, "contribution": 0.833}, {"maturity": 3, "contribution": 0.833}]
        reduction = control_reduction(c)
        assert 0.0 < reduction < 1.0

    def test_reduction_bounded(self):
        many = [{"maturity": 5, "contribution": 1.0}] * 10
        assert 0.0 <= control_reduction(many) <= 1.0


class TestCalcResidual:
    def test_no_controls_equals_inherent(self):
        lik, cons, level = calc_residual(3, 3, [])
        assert lik == 3
        assert cons == 3
        assert level == calc_level(3, 3)

    def test_perfect_control_reduces_risk(self):
        lik, cons, level = calc_residual(4, 4, [{"maturity": 5, "contribution": 1.0}])
        assert lik < 4 or cons < 4
        assert level <= calc_level(4, 4)

    def test_residual_level_within_bounds(self):
        lik, cons, level = calc_residual(4, 4, [{"maturity": 3, "contribution": 0.8}])
        assert 0 <= level <= 8
        assert 0 <= lik <= 4
        assert 0 <= cons <= 4

    def test_boundary_zeros(self):
        lik, cons, level = calc_residual(0, 0, [{"maturity": 5, "contribution": 1.0}])
        assert lik == 0
        assert cons == 0
        assert level == 0
