
"""
Unit tests for ramp-fitting functions.
"""
import astropy.units as u
import numpy as np
import pytest

from stcal.ramp_fitting import ols_cas22_fit as ramp

# Read Time in seconds
#   For Roman, the read time of the detectors is a fixed value and is currently
#   backed into code. Will need to refactor to consider the more general case.
#   Used to deconstruct the MultiAccum tables into integration times.
ROMAN_READ_TIME = 3.04


@pytest.mark.parametrize("use_unit", [True, False])
def test_simulated_ramps(use_unit):
    ntrial = 100000
    read_pattern, flux, read_noise, resultants = simulate_many_ramps(ntrial=ntrial)

    if use_unit:
        resultants = resultants * u.electron

    dq = np.zeros(resultants.shape, dtype=np.int32)
    read_noise = np.ones(resultants.shape[1], dtype=np.float32) * read_noise

    output = ramp.fit_ramps_casertano(
        resultants, dq, read_noise, ROMAN_READ_TIME, read_pattern)

    if use_unit:
        assert output.parameters.unit == u.electron
        parameters = output.parameters.value
    else:
        parameters = output.parameters

    chi2dof_slope = np.sum((parameters[:, 1] - flux)**2 / output.variances[:, 2]) / ntrial
    assert np.abs(chi2dof_slope - 1) < 0.03

    # now let's mark a bunch of the ramps as compromised.
    bad = np.random.uniform(size=resultants.shape) > 0.7
    dq |= bad
    output = ramp.fit_ramps_casertano(
        resultants, dq, read_noise, ROMAN_READ_TIME, read_pattern,
        threshold_constant=0, threshold_intercept=0)  # set the threshold parameters
                                                      #   to demo the interface. This
                                                      #   will raise an error if
                                                      #   the interface changes, but
                                                      #   does not effect the computation
                                                      #   since jump detection is off in
                                                      #   this case.
    # only use okay ramps
    # ramps passing the below criterion have at least two adjacent valid reads
    # i.e., we can make a measurement from them.
    m = np.sum((dq[1:, :] == 0) & (dq[:-1, :] == 0), axis=0) != 0

    if use_unit:
        assert output.parameters.unit == u.electron
        parameters = output.parameters.value
    else:
        parameters = output.parameters

    chi2dof_slope = np.sum((parameters[m, 1] - flux)**2 / output.variances[m, 2]) / np.sum(m)
    assert np.abs(chi2dof_slope - 1) < 0.03
    assert np.all(parameters[~m, 1] == 0)
    assert np.all(output.variances[~m, 1] == 0)


# #########
# Utilities
# #########
def simulate_many_ramps(ntrial=100, flux=100, readnoise=5, read_pattern=None):
    """Simulate many ramps with a particular flux, read noise, and ma_table.

    To test ramp fitting, it's useful to be able to simulate a large number
    of ramps that are identical up to noise.  This function does that.

    Parameters
    ----------
    ntrial : int
        number of ramps to simulate
    flux : float
        flux in electrons / s
    read_noise : float
        read noise in electrons
    read_pattern : list[list] (int)
        An optional read pattern

    Returns
    -------
    ma_table : list[list] (int)
        ma_table used
    flux : float
        flux used
    readnoise : float
        read noise used
    resultants : np.ndarray[n_resultant, ntrial] (float)
        simulated resultants
"""
    if read_pattern is None:
        read_pattern = [[1, 2, 3, 4],
                        [5],
                        [6, 7, 8],
                        [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
                        [19, 20, 21],
                        [22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36]]
    nread = np.array([len(x) for x in read_pattern])
    resultants = np.zeros((len(read_pattern), ntrial), dtype='f4')
    buf = np.zeros(ntrial, dtype='i4')
    for i, reads in enumerate(read_pattern):
        subbuf = np.zeros(ntrial, dtype='i4')
        for _ in reads:
            buf += np.random.poisson(ROMAN_READ_TIME * flux, ntrial)
            subbuf += buf
        resultants[i] = (subbuf / len(reads)).astype('f4')
    resultants += np.random.randn(len(read_pattern), ntrial) * (
        readnoise / np.sqrt(nread)).reshape(len(read_pattern), 1)
    return (read_pattern, flux, readnoise, resultants)
