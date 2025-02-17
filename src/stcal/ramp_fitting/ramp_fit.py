#! /usr/bin/env python
#
#  ramp_fit.py - calculate weighted mean of slope, based on Massimo
#                Robberto's "On the Optimal Strategy to fit MULTIACCUM
#                ramps in the presence of cosmic rays."
#                (JWST-STScI-0001490,SM-12; 07/25/08).   The derivation
#                is a generalization for >1 cosmic rays, calculating
#                the slope and variance of the slope for each section
#                of the ramp (in between cosmic rays). The intervals are
#                determined from the input data quality arrays.
#
# Note:
# In this module, comments on the 'first group','second group', etc are
#    1-based, unless noted otherwise.

import numpy as np
import logging

# from . import gls_fit           # used only if algorithm is "GLS"
from . import ols_fit           # used only if algorithm is "OLS"
from . import ramp_fit_class

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

BUFSIZE = 1024 * 300000  # 300Mb cache size for data section


def create_ramp_fit_class(model, dqflags=None):
    """
    Create an internal ramp fit class from a data model.

    Parameters
    ----------
    model : data model
        input data model, assumed to be of type RampModel

    dqflags : dict
        The data quality flags needed for ramp fitting.

    Return
    ------
    ramp_data : ramp_fit_class.RampData
        The internal ramp class.
    """
    ramp_data = ramp_fit_class.RampData()

    # Attribute may not be supported by all pipelines.  Default is NoneType.
    if hasattr(model, 'int_times'):
        int_times = model.int_times
    else:
        int_times = None
    ramp_data.set_arrays(
        model.data, model.err, model.groupdq, model.pixeldq, int_times)

    # Attribute may not be supported by all pipelines.  Default is NoneType.
    if hasattr(model, 'drop_frames1'):
        drop_frames1 = model.exposure.drop_frames1
    else:
        drop_frames1 = None
    ramp_data.set_meta(
        name=model.meta.instrument.name,
        frame_time=model.meta.exposure.frame_time,
        group_time=model.meta.exposure.group_time,
        groupgap=model.meta.exposure.groupgap,
        nframes=model.meta.exposure.nframes,
        drop_frames1=drop_frames1)

    ramp_data.set_dqflags(dqflags)

    return ramp_data


def ramp_fit(model, buffsize, save_opt, readnoise_2d, gain_2d,
             algorithm, weighting, max_cores, dqflags):
    """
    Calculate the count rate for each pixel in all data cube sections and all
    integrations, equal to the slope for all sections (intervals between
    cosmic rays) of the pixel's ramp divided by the effective integration time.
    The weighting parameter must currently be set to 'optim', to use the optimal
    weighting (paper by Fixsen, ref. TBA) will be used in the fitting; this is
    currently the only supported weighting scheme.

    Parameters
    ----------
    model : data model
        input data model, assumed to be of type RampModel

    buffsize : int
        size of data section (buffer) in bytes

    save_opt : bool
       calculate optional fitting results

    readnoise_2d : ndarray
        2-D array readnoise for all pixels

    gain_2d : ndarray
        2-D array gain for all pixels

    algorithm : str
        'OLS' specifies that ordinary least squares should be used;
        'GLS' specifies that generalized least squares should be used.

    weighting : str
        'optimal' specifies that optimal weighting should be used;
         currently the only weighting supported.

    max_cores : str
        Number of cores to use for multiprocessing. If set to 'none' (the
        default), then no multiprocessing will be done. The other allowable
        values are 'quarter', 'half', and 'all'. This is the fraction of cores
        to use for multi-proc. The total number of cores includes the SMT cores
        (Hyper Threading for Intel).

    dqflags : dict
        A dictionary with at least the following keywords:
        DO_NOT_USE, SATURATED, JUMP_DET, NO_GAIN_VALUE, UNRELIABLE_SLOPE

    Returns
    -------
    image_info : tuple
        The tuple of computed ramp fitting arrays.

    integ_info : tuple
        The tuple of computed integration fitting arrays.

    opt_info : tuple
        The tuple of computed optional results arrays for fitting.

    gls_opt_model : GLS_RampFitModel object or None (Unused for now)
        Object containing optional GLS-specific ramp fitting data for the
        exposure
    """
    # Create an instance of the internal ramp class, using only values needed
    # for ramp fitting from the to remove further ramp fitting dependence on
    # data models.
    ramp_data = create_ramp_fit_class(model, dqflags)

    return ramp_fit_data(
        ramp_data, buffsize, save_opt, readnoise_2d, gain_2d,
        algorithm, weighting, max_cores, dqflags)


def ramp_fit_data(ramp_data, buffsize, save_opt, readnoise_2d, gain_2d,
                  algorithm, weighting, max_cores, dqflags):
    """
    This function begins the ramp fit computation after the creation of the
    RampData class.  It determines the proper path for computation to take
    depending on the choice of ramp fitting algorithms (which is only ordinary
    least squares right now) and the choice of single or muliprocessing.


    ramp_data : RampData
        Input data necessary for computing ramp fitting.

    buffsize : int
        size of data section (buffer) in bytes

    save_opt : bool
       calculate optional fitting results

    readnoise_2d : ndarray
        2-D array readnoise for all pixels

    gain_2d : ndarray
        2-D array gain for all pixels

    algorithm : str
        'OLS' specifies that ordinary least squares should be used;
        'GLS' specifies that generalized least squares should be used.

    weighting : str
        'optimal' specifies that optimal weighting should be used;
         currently the only weighting supported.

    max_cores : str
        Number of cores to use for multiprocessing. If set to 'none' (the
        default), then no multiprocessing will be done. The other allowable
        values are 'quarter', 'half', and 'all'. This is the fraction of cores
        to use for multi-proc. The total number of cores includes the SMT cores
        (Hyper Threading for Intel).

    dqflags : dict
        A dictionary with at least the following keywords:
        DO_NOT_USE, SATURATED, JUMP_DET, NO_GAIN_VALUE, UNRELIABLE_SLOPE

    Returns
    -------
    image_info : tuple
        The tuple of computed ramp fitting arrays.

    integ_info : tuple
        The tuple of computed integration fitting arrays.

    opt_info : tuple
        The tuple of computed optional results arrays for fitting.

    gls_opt_model : GLS_RampFitModel object or None (Unused for now)
        Object containing optional GLS-specific ramp fitting data for the
        exposure
    """
    if algorithm.upper() == "GLS":
        # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        # !!!!! Reference to ReadModel and GainModel changed to simple ndarrays !!!!!
        # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        # new_model, int_model, gls_opt_model = gls_fit.gls_ramp_fit(
        #     model, buffsize, save_opt, readnoise_model, gain_model, max_cores)
        image_info, integ_info, gls_opt_model = None, None, None
        opt_info = None
    else:
        # Get readnoise array for calculation of variance of noiseless ramps, and
        #   gain array in case optimal weighting is to be done
        nframes = ramp_data.nframes
        readnoise_2d *= gain_2d / np.sqrt(2. * nframes)

        # Compute ramp fitting using ordinary least squares.
        image_info, integ_info, opt_info = ols_fit.ols_ramp_fit_multi(
            ramp_data, buffsize, save_opt, readnoise_2d, gain_2d, weighting, max_cores)
        gls_opt_model = None

    return image_info, integ_info, opt_info, gls_opt_model
