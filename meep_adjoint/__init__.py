"""
Adjoint-based sensitivity-analysis module for pymeep.
Authors: Homer Reid <homer@homerreid.com>, Alec Hammond <alec.hammond@gatech.edu>
Documentation: https://meep.readthedocs.io/en/latest/Python_Tutorials/AdjointSolver.md
"""
import sys

import meep as mp

######################################################################
######################################################################
######################################################################

from .dft_cell import (XHAT, YHAT, ZHAT, E_CPTS, H_CPTS, EH_CPTS,
                       Subregion, DFTCell, Grid, fix_array_metadata,
                       make_grid, dft_cell_names, rescale_sources, xyzw2grid)

from .objective import EigenmodeCoefficient

from .basis import (Basis, BilinearInterpolationBasis)

#from .finite_element_basis import (FiniteElementBasis, make_interpolation_matrix)

from .timestepper import TimeStepper

from .optimization_problem import OptimizationProblem

######################################################################
######################################################################
######################################################################
