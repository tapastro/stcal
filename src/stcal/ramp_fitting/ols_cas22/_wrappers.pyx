import numpy as np
cimport numpy as np

from libcpp cimport bool
from libcpp.stack cimport stack
from libcpp.deque cimport deque

from stcal.ramp_fitting.ols_cas22._core cimport RampIndex, DerivedData, Thresh
from stcal.ramp_fitting.ols_cas22._core cimport read_data as c_read_data
from stcal.ramp_fitting.ols_cas22._core cimport init_ramps as c_init_ramps
from stcal.ramp_fitting.ols_cas22._core cimport make_threshold as c_make_threshold

from stcal.ramp_fitting.ols_cas22._fixed cimport make_fixed as c_make_fixed

def read_data(list[list[int]] read_pattern, float read_time):
    return c_read_data(read_pattern, read_time)


def init_ramps(np.ndarray[int, ndim=2] dq):
    cdef deque[stack[RampIndex]] raw = c_init_ramps(dq)

    # Have to turn deque and stack into python compatible objects
    cdef RampIndex index
    cdef stack[RampIndex] ramp
    cdef list out = []
    cdef list stack_out
    for ramp in raw:
        stack_out = []
        while not ramp.empty():
            index = ramp.top()
            ramp.pop()
            # So top of stack is first item of list
            stack_out = [index] + stack_out

        out.append(stack_out)

    return out


def make_threshold(float intercept, float constant):
    return c_make_threshold(intercept, constant)


def run_threshold(Thresh threshold, float slope):
    return threshold.run(slope)


def make_fixed(np.ndarray[float, ndim=1] t_bar,
               np.ndarray[float, ndim=1] tau,
               np.ndarray[int, ndim=1] n_reads,
               float intercept,
               float constant,
               bool use_jump):

    cdef DerivedData data = DerivedData(t_bar, tau, n_reads)
    cdef Thresh threshold = c_make_threshold(intercept, constant)

    return c_make_fixed(data, threshold, use_jump)
