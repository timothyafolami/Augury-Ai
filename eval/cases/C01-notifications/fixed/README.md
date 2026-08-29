# The remediated versions

For each seeded defect, the file as it should have been written.

`tests/test_experiments_discriminate.py` overlays these on a copy of the case
repository and re-runs every experiment. An experiment reporting the same
number either way is not measuring the defect, and the test fails.
