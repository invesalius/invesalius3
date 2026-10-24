import pytest
import math
from invesalius.utils import frange, next_copy_name


class TestNextCopyName:
    """
    Test cases for duplication logic defined in next_copy_name.
    """

    @pytest.mark.parametrize(
        "original_name, existing_names, expected_next_name",
        [
            # Case 1- Empty list/initial duplicate
            ("Mask", [], "Mask copy"),
            # Case 2- testing normal copy cases defined in the logic
            ("Mask", ["Mask", "Mask copy"], "Mask copy#1"),
            ("Mask", ["Mask", "Mask copy", "Mask copy#1"], "Mask copy#2"),
            # Case 3- Copying a name that already has copy 
            ("Mask copy", ["Mask", "Mask copy"], "Mask copy#1"),
            ("Mask copy#1", ["Mask", "Mask copy", "Mask copy#1"], "Mask copy#2"),
            # Case 4- Checks higher indices
            (
                "Mask",
                ["Mask", "Mask copy"] + [f"Mask copy#{i}" for i in range(1, 10)],
                "Mask copy#10",
            ),
            # Case 5- Fills gaps by picking lowest missed index
            ("Mask", ["Mask", "Mask copy", "Mask copy#2"], "Mask copy#1"),
            # Case 6- Unrelated names in the list are ignored
            ("Mask", ["Bone", "Skin", "Slice 1", "Mask"], "Mask copy"),
            ("Mask", ["Bone", "Mask", "Mask copy", "Other copy 2"], "Mask copy#1"),
            ("Mask", ["Bone", "Bone copy", "Surface"], "Mask copy"),
        ],
    )
    def test_next_copy_name_progression(
        self, original_name, existing_names, expected_next_name
    ):
        """
        Verifies initial copy, #index increments, and unrelated name handling.
        """
        assert next_copy_name(original_name, existing_names) == expected_next_name

    def test_name_with_spaces_and_symbols(self):
        """
        Checking logic when spaces, parentheses or symbols are present.
        """
        name = "Bone (200 - 800 HU)"
        existing = [name, f"{name} copy"]
        assert next_copy_name(name, existing) == f"{name} copy#1"

    def test_non_sequential_gap_handling(self):
        """
        Checks behaviour when missing numbers exist in the copy sequence.
        """
        existing = ["Surface", "Surface copy", "Surface copy#1", "Surface copy#3"]
        assert next_copy_name("Surface", existing) == "Surface copy#2"



class TestFRange:
    """Test suite for frange utility function"""

    # type 1- testing all cases when different number of arguements are passed 
    def test_single_argument_stop_only(self):
        """Single argument frange(end) starts at 0.0 with step 1.0"""
        result = frange(4.0)
        assert result == [0.0, 1.0, 2.0, 3.0]

    def test_two_arguments_start_and_end(self):
        """Two arguments frange(start, end) defaults to step 1.0"""
        result = frange(1.5, 4.5)
        assert result == [1.5, 2.5, 3.5]

    def test_three_arguments_explicit_step(self):
        """Three arguments frange(start, end, inc)"""
        result = frange(0.0, 1.0, 0.2)
        expected = [0.0, 0.2, 0.4, 0.6, 0.8]
        assert len(result) == len(expected)
        for actual, exp in zip(result, expected):
            assert round(abs(actual - exp), 7) == 0

    # type 2- 3 arguements, testing the variation in directions
    
    def test_negative_step_decrementing(self):
        """Negative increment steps downward until end boundary."""
        result = frange(5.0, 1.0, -1.0)
        assert result == [5.0, 4.0, 3.0, 2.0]

    def test_negative_step_fractional(self):
        """Negative fractional increment."""
        result = frange(1.0, 0.0, -0.25)
        expected = [1.0, 0.75, 0.5, 0.25]
        assert result == expected

    def test_zero_increment_defaults_to_one(self):
        """inc=0 falls back to inc=1.0 per implementation design."""
        result = frange(1.0, 4.0, 0)
        assert result == [1.0, 2.0, 3.0]

    def test_explicit_none_increment_defaults_to_one(self):
        """inc=None falls back to inc=1.0."""
        result = frange(2.0, 5.0, None)
        assert result == [2.0, 3.0, 4.0]

    #type 3- Cases where same start and end, invalid increment or start/end, doesnt include last boundary case
   
    def test_start_equals_end_returns_empty(self):
        """Start equal to end returns an empty list."""
        assert frange(5.0, 5.0) == []
        assert frange(0.0) == []
        assert frange(-3.0) == []

    def test_mismatched_step_and_range_direction(self):
        """Positive increment when start > end returns empty list."""
        assert frange(10.0, 0.0, 1.0) == []

    def test_negative_increment_when_start_less_than_end(self):
        """Negative increment when start < end returns empty list."""
        assert frange(0.0, 10.0, -1.0) == []

    def test_exact_boundary_non_inclusion(self):
        """Ensure boundary value is strictly non-inclusive."""
        result = frange(0.0, 2.0, 0.5)
        assert result == [0.0, 0.5, 1.0, 1.5]
        assert 2.0 not in result

    #type 4- checking the floating point drift and inclusion of negative values
    def test_no_cumulative_floating_point_drift(self):
        """Check that multiplying step index avoids cumulative float drift."""
        result = frange(0.0, 0.5, 0.1)
        expected = [0.0, 0.1, 0.2, 0.3, 0.4]
        assert len(result) == 5
        for actual, exp in zip(result, expected):
            assert round(abs(actual - exp), 7) == 0

    def test_negative_values_and_crossing_zero(self):
        """Ensure smooth traversal across negative values into positive space."""
        result = frange(-1.5, 1.5, 1.0)
        assert result == [-1.5, -0.5, 0.5]

    #type 5- Testing if int values pass, instead of floats
    def test_integer_inputs_compatibility(self):
        """Ensure passing ints works smoothly without raising TypeError."""
        result = frange(1, 5, 2)
        assert result == [1, 3]

    #type 6- if step interferes with boundary
    def test_non_integer_step_division_stopping_before_end(self):
        """Boundary stops strictly before end when step doesn't divide evenly."""
        result = frange(0.0, 2.3, 0.5)
        expected = [0.0, 0.5, 1.0, 1.5, 2.0]
        assert len(result) == len(expected)
        for actual, exp in zip(result, expected):
            assert round(abs(actual - exp), 7) == 0

    #type 7- extending the test for real world larger end
    def test_large_range_count(self):
        """Validates accuracy across larger item counts."""
        result = frange(0.0, 100.0, 0.1)
        assert len(result) == 1000
        assert round(abs(result[0] - 0.0), 7) == 0
        assert round(abs(result[-1] - 99.9), 7) == 0