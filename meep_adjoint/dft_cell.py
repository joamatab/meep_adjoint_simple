"""Mostly convenience wrappers around various objects in core pymeep.

   Grid repackages 'array metadata' with some convenient redundancy

   Subregion replaces the 6 separate pymeep data structures used
   to describe grid subregions ('FluxRegion', 'FieldsRegion', etc.)

   DFTCell similarly replaces the 5 separate data structures used
   to describe sets of frequency-domain field components.
"""

import numpy as np
import meep as mp
import warnings
from collections import namedtuple

######################################################################
# general-purpose constants and utility routines
######################################################################
ORIGIN           = np.zeros(3)
XHAT, YHAT, ZHAT = [ np.array(a) for a in [[1.,0,0], [0,1.,0], [0,0,1.]] ]
E_CPTS           = [mp.Ex, mp.Ey, mp.Ez]
H_CPTS           = [mp.Hx, mp.Hy, mp.Hz]
EH_CPTS          = E_CPTS + H_CPTS
EH_TRANSVERSE    = [ [mp.Ey, mp.Ez, mp.Hy, mp.Hz],
                     [mp.Ez, mp.Ex, mp.Hz, mp.Hx],
                     [mp.Ex, mp.Ey, mp.Hx, mp.Hy] ]

######################################################################
# fix a bug in libmeep
######################################################################
def fix_array_metadata(xyzw, center, size):
    """fixes for the perenially buggy get_array_metadata routine in core meep."""
    for d in range(0,3):
        if size[d]==0.0 and xyzw[d][0]!=center[d]:
            xyzw[d]=np.array([center[d]])
        else:
            xyzw[d]=np.array(xyzw[d])


######################################################################
# 'Grid' is a convenience extension of 'array metadata'
######################################################################
Grid = namedtuple('Grid', ['xtics', 'ytics', 'ztics', 'points', 'weights', 'shape'])

def make_grid(size, center=np.zeros(3), dims=None, length=None):
    """Construct a Grid for a rectangular subregion.

    Parameters
    ----------
    size : [list or numpy array]
        size of region
    center : [list or numpy array], optional
        center of region, by default np.zeros(3)
    dims : [list of integer], optional
        numbers of grid points in each dimension, by default None
    length : [float], optional
        discretization lengthscale, by default None

    Returns
    -------
    New instance of Grid.
    """

    nd = len(np.flatnonzero(size))
    center, size = np.array(center)[0:nd], np.array(size)[0:nd]
    if length is not None:
        dims = [max(1,int(np.ceil(s/length))) for s in size]
    if dims is None:
        dims = [(10 if s>0 else 1) for s in size]
    pmin, pmax = center-0.5*size, center+0.5*size
    tics = [np.linspace(a, b, n) for (a, b, n) in zip(pmin, pmax, dims)]
    if len(tics)==2:
        tics.append([0])
    points = [np.array([x, y, z]) for x in tics[0] for y in tics[1] for z in tics[2] ]
    vol, ntot = np.prod([s for s in size if s>0]), np.prod(dims)
    weights = (vol/ntot) * np.ones(ntot)
    shape = [len(t) for t in tics if len(t)>1]
    return Grid(tics[0], tics[1], tics[2], points, weights, shape)


def xyzw2grid(xyzw):
    """Construct Grid from lists of points and weights."""
    return Grid(xyzw[0], xyzw[1], xyzw[2],
                [mp.Vector3(x,y,z) for x in xyzw[0] for y in xyzw[1] for z in xyzw[2]],
                 xyzw[3].flatten(), xyzw[3].shape)


class Subregion(object):
    """Subregion of computational cell.

    A Subregion is a finite hyperrectangular region of space contained
    within the extents of the FDTD computational grid.

    A Subregion may be of codimension 1 (i.e. it is a line in 2D
    or a plane in 3D), in which case it has a normal direction.
    Codim-1 subregions are used to define eigenmode sources and
    to evaluate Poynting fluxes and eigenmode expansion coefficients.

    Alternatively, the subregion may be of codimension 0 [i.e.
    it is a full rectangle (2D) or box (3D)], or of dimension 0 [i.e.
    it is a point]. The normal direction is undefined in these cases.

    A Subregion has a name (str), which is user-assigned or autogenerated
    if left unspecified.

    Note
    ----
    ``Subregion`` is a common replacement for ``FluxRegion``, ``EnergyRegion``,
    and the other similar data structures in :program:`libmeep`.
    Its advantages are that (a) it eliminates redundant code and cumbersome API conventions
    imposed by the coexistence of multiple distinct data structures all describing the
    same thing, and that (b) it adds a user-assignable name field, which would be
    convenient to have already in core :program:`pymeep`
    but is essential in ``meep_adjoint`` to allow objective quantities to be
    assigned names that identify the objective region for which they are defined.



    Parameters
    ----------
        xmin : array-like, optional
            minimal corner, by default None
        xmax : array-like, optional
            maximal corner, by default None
        center : array-like, optional
            center, by default ``ORIGIN``
        size : array-like, optional
            size, by default None
        normal : array-like, optional
            normal direction for codim-1 regions, by default None
        name : str, optional
            arbitrary caller-chosen label; autogenerated if not specified
    """
    def __init__(self, fcen, df=0, nfreq=1, xmin=None, xmax=None, center=mp.Vector3(), size=None,
                       normal=None, dir=None, name=None):
        self.fcen = fcen
        self.df = df
        self.nfreq = nfreq

        if (xmin is not None) and (xmax is not None):
            (self.xmin, self.xmax)   = (v3(xmin), v3(xmax))
            (self.center, self.size) = (0.5*(self.xmax+self.xmin)), ((self.xmax-self.xmin))
        elif size is not None:
           (self.center, self.size) = (center, size)
           self.xmin, self.xmax   = [self.center + sgn*self.size  for sgn in [-1,1] ]
        self.normal, self.name = (dir if normal is None else normal), name


dft_cell_names=[]


class DFTCell(object):
    """Simpler data structure for frequency-domain fields in MEEP

       The instantiating data of a DFTCell are a grid subregion, a set of
       field components, and a list of frequencies. These metadata fields
       remain constant throughout the lifetime of a DFTCell.
       In addition to the metadata, instances of DFTCell allocate
       internal arrays of DFT registers in which the specified components of the
       frequency-domain fields at the specified grid points and frequencies
       are accumulated over the course of a MEEP timestepping run. These
       registers are reset to zero at the beginning of the next timestepping
       run, but in the meantime you can use the ``save_fields`` method
       to save an internally cached snapshot of the fields computed on a
       given timestepping run.

       Note: for now, all arrays are stored in memory. For large calculations with
       many DFT frequencies it might make sense to implement a disk-caching scheme.

       The internally-stored frequency-domain fields at a single frequency
       may be fetched via the get_EH_slice (single component) or
       get_EH_slices (all components) methods. By default these routines
       return slices of the currently active fields (i.e. the fields computed
       on the most recent timestepping run), but they accept an optional
       parameter specifying the label of a data set stored by a call to
       ``save_fields`` after a previous timestepping run.

       For convenience, DFTCell also offers a get_eigenmode_slices() method that
       computes and returns eigenfield profiles in the same format as DFT fields.

       DFTCells also know how to crunch their internally-stored field-component
       data to compute various physical quantities of interest, such as
       Poynting fluxes and field energies. We consider this the primary
       functionality exported by DFTCell, and thus implement it as the
       __call__ method of the class.

       DFTCell replaces the DftFlux, DftFields, DftNear2Far, DftForce, DftLdos,
       and DftObj structures in core pymeep.

       Parameters
       ----------
       region : Subregion
           Subregion of computational cell in which to compute frequency-domain field components.
       components : list of meep components (i.e. [mp.Ex, mp.Hy]), optional
           Field components to compute.
       fcen, df, nfreq: float, float, int
           Set of frequencies at which to compute FD fields.
    """
    def __init__(self, region, components=None):
        self.region     = region
        self.normal     = region.normal
        self.celltype   = 'flux' if self.normal is not None else 'fields'
        self.components = components or (EH_TRANSVERSE[self.normal] if self.normal is not None else EH_CPTS)
        self.fcen       = region.fcen
        self.df         = region.df
        self.nfreq      = region.nfreq
        self.freqs      = [self.fcen] if self.nfreq==1 else np.linspace(self.fcen-0.5*self.df, self.fcen+0.5*self.df, self.nfreq)

        self.sim        = None  # mp.simulation for current simulation
        self.dft_obj    = None  # meep DFT object for current simulation

        self.EH_cache   = {}    # cache of frequency-domain field data computed in previous simulations
        self.eigencache = {}    # cache of eigenmode field data to avoid redundant recalculations

        global dft_cell_names
        if region.name is not None:
            self.name = '{}_{}'.format(region.name, self.celltype)
        else:
            self.name = '{}_{}'.format(self.celltype, len(dft_cell_names))

        dft_cell_names.append(self.name)

        # Although the subgrid covered by the cell is independent of any
        # mp.simulation, at present we can't compute subgrid metadata
        # without first instantiating a mp.Simulation, so we have to
        # wait to initialize the 'grid' field of DFTCell. TODO make the
        # grid metadata calculation independent of any mp.Simulation or meep::fields
        # object; it only depends on the resolution and extents of the Yee grid
        # and thus logically belongs in `vec.cpp` or another code module that
        # exists independently of fields, structures, etc.
        self.grid = None



    def register(self, sim):
        """ 'Register' the cell in a MEEP simulation to request computation of frequency-domain fields.

        Parameters
        ----------
        sim : mp.Simulation
        """
        self.sim = sim
        if self.celltype == 'flux':
            flux_region  = mp.FluxRegion(self.region.center,self.region.size,direction=self.normal)
            self.dft_obj = sim.add_flux(self.fcen,self.df,self.nfreq,flux_region)
        else:
            self.dft_obj = sim.add_dft_fields(self.components, self.freqs[0], self.freqs[-1], self.nfreq, center=self.region.center, size=self.region.size)

        # take this opportunity to initialize simulation-dependent fields
        if self.grid is None:
            xyzw=sim.get_array_metadata(center=self.region.center, size=self.region.size, collapse=True, snap=True)
            fix_array_metadata(xyzw, self.region.center, self.region.size)
            self.grid = xyzw2grid(xyzw)

    ######################################################################
    ######################################################################
    def get_EH_slice(self, c, nf=0):
        """Fetch array of frequency-domain amplitudes for a single field component.

        Compute an array of frequency-domain field amplitudes, i.e. a
        frequency-domain array slice, for a single field component at a
        single frequency in the current simulation. This is like
        mp.get_dft_array(), but 'zero-padded:' when the low-level DFT object
        does not have data for the requested component (perhaps because it vanishes
        identically by symmetry), this routine returns an array of the expected
        dimensions with all zero entries, instead of a rank-0 array that prints
        out as a single preposterously large or small floating-point number,
         which is the not-very-user-friendly behavior of mp.get_dft_array().

        Parameters
        ----------
        c : (mp.component)
            Field component to fetch.
        nf : int, optional
            Frequency index, by default 0

        Returns
        -------
        np.array
            Complex-valued array giving field amplitude at grid points.
        """
        EH = self.sim.get_dft_array(self.dft_obj, c, nf)
        return EH if np.ndim(EH)>0 else 0.0j*np.zeros(self.grid.shape)


    def get_EH_slices(self, label=None, nf=0):
        """Fetch arrays of frequency-domain field amplitudes for all stored components.

        Return a 1D array (list) of arrays of frequency-domain field amplitudes,
        one for each component in this DFTCell, at a single frequency in a
        single MEEP simulation. The simulation in question may be the present,
        ongoing simulation (if label==None), in which case the array slices are
        read directly from the currently active meep DFT object; or it may be a
        previous simulation (identified by label) for which
        DFTCell::save_fields(label) was called at the end of timestepping.

        Parameters
        ----------
        label : [str], optional
            Label of saved data to retrieve.
        nf : int, optional
            Frequency index, by default 0

        Returns
        -------
        list of np.array
            Arrays of field-component amplitudes at grid points

        Raises
        ------
        ValueError
            if no data exists for the specified label.
        """
        if label is None:
            return [ self.get_EH_slice(c, nf=nf) for c in self.components ]
        elif label in self.EH_cache:
            return self.EH_cache[label][nf]
        raise ValueError("DFTCell {} has no saved data for label '{}'".format(self.name, label))


    def subtract_incident_fields(self, EHT, nf=0):
        """Substract incident from total fields to yield scattered fields.

        Parameters
        ----------
        EHT : list of arrays of field component amplitudes, as
              returned by get_EH_slices, for the **total** fields
        nf : int, optional
             frequency index, by default 0
        """
        EHI = self.get_EH_slices(label='incident', nf=nf)
        for nc, c in enumerate(self.components):
            EHT[nc] -= EHI[nc]


    def save_fields(self, label):
        """ Save current values of grid fields internally for later use.

        This routine tells the DFTCell to create and save an archive of
        the frequency-domain array slices for the present simulation---i.e.
        to copy the frequency-domain field data out of the sim.dft_obj
        structure and into an appropriate data buffer in the DFTCell,
        before the sim.dft_obj data vanish when sim is reset for the next run.
        This routine should be called after timestepping is complete. The
        given label is used to identify the stored data for future retrieval.

        Parameters
        ----------
        label : str
            Label assigned to data set, used subsequently for retrieval.
        """
        self.EH_cache[label] = [self.get_EH_slices(nf=nf) for nf in range(len(self.freqs))]


    def get_eigenmode_slices(self, mode, nf=0):
        """Like get_EH_slices, but for eigenmode fields.

        Return a 1D array (list) of arrays of field amplitudes for all
        tangential E,H components at a single frequency---just like
        get_EH_slices()---except that the sliced E and H fields are the
        fields of eigenmode #mode.

        Parameters
        ----------
        mode : int
            Eigenmode index.
        nf : int, optional
            Frequency index, by default 0

        Returns
        ----------
        list of np.arrays (same format as returned by get_EH_slices)
        """

        # look for data in cache
        tag='M{}.F{}'.format(mode,nf)
        if self.eigencache and tag in self.eigencache:
            return self.eigencache[tag]

        # data not in cache; compute eigenmode and populate slice arrays
        freq, dir, k0 = self.freqs[nf], self.normal, mp.Vector3()
        vol = mp.Volume(center=self.region.center,size=self.region.size)
        eigenmode = self.sim.get_eigenmode(freq, dir, vol, mode, k0)

        def get_eigenslice(eigenmode, grid, c):
            return np.reshape( [eigenmode.amplitude(p,c) for p in grid.points], grid.shape )

        eh_slices=[get_eigenslice(eigenmode,self.grid,c) for c in self.components]

        # store in cache before returning
        if self.eigencache is not None:
            self.eigencache[tag]=eh_slices

        return eh_slices


    def __call__(self, qcode, mode=1, nf=0):
        """Compute and return the value of an objective quantity.

        Computes an objective quantity, i.e. an eigenmode
        coefficient or a scattered or total power.

        Parameters
        ----------
        qcode : [str]
            Objective quantity code.
        mode : int, optional
            Eigenmode index, by default 0
        nf : int, optional
            Frequency index, by default 0

        Returns
        -------
        float64 or complex128
            value of objective quantity
        """
        w  = np.reshape(self.grid.weights,self.grid.shape)
        EH = self.get_EH_slices(nf=nf)
        quantity=qcode.upper()
        if qcode.islower():
             self.subtract_incident_fields(EH,nf)
        if quantity=='S':
            return np.real(np.sum(w*( np.conj(EH[0])*EH[3] - np.conj(EH[1])*EH[2]) ))
        if quantity.upper() in 'PFMB':
            eh = self.get_eigenmode_slices(mode, nf)  # EHList of eigenmode fields
            eH = np.sum( w*(np.conj(eh[0])*EH[3] - np.conj(eh[1])*EH[2]) )
            hE = np.sum( w*(np.conj(eh[3])*EH[0] - np.conj(eh[2])*EH[1]) )
            sign=1.0 if qcode in ['P','F'] else -1.0
            temp = (eH + sign*hE)/4.0
            return temp

            #sign=0 if qcode in ['P','F'] else 1
            #ob = self.sim.get_eigenmode_coefficients(self.dft_obj,[mode])
            #return ob.alpha[mode-1,nf,sign]
        if quantity in ['UE', 'UH', 'UM', 'UEH', 'UEM', 'UT']:
           q=0.0
           if quantity in ['UE', 'UEH', 'UEM', 'UT']:
               eps = self.sim.get_dft_array(self.dft_obj, mp.Dielectric, nf)
               E2  = np.sum( [np.conj(EH[nc])*EH[nc] for nc,c in enumerate(self.components) if c in E_CPTS], axis=0 )
               q  += 0.5*np.sum(w*eps*E2)
           if quantity in ['UH', 'UM', 'UEH', 'UEM', 'UT']:
               mu  = self.sim.get_dft_array(self.dft_obj, mp.Permeability, nf)
               H2  = np.sum( [np.conj(EH[nc])*EH[nc] for nc,c in enumerate(self.components) if c in H_CPTS], axis=0 )
               q  += 0.5*np.sum(w*mu*H2)
           return q
        else: # TODO: support other types of objectives quantities?
            ValueError('DFTCell {}: unsupported quantity type {}'.format(self.name,qcode))


######################################################################
######################################################################
######################################################################
def rescale_sources(sources):
    """Scale the overall amplitude of a spatial source distribution to compensate
       for the frequency dependence of its temporal envelope.

       In a MEEP calculation driven by sources with a pulsed temporal envelope T(t),
       the amplitudes of all frequency-f DFT fields will be proportional to
       T^tilde (f), the Fourier transform of the envelope. Here we divide
       the overall amplitude of the source by T^tilde(f_c) (where f_c = center
       frequency), which exactly cancels the extra scale factor for DFT
       fields at f_c.

       Args:
           sources: list of mp.Sources

       Returns:
           none (the rescaling is done in-place)
    """
    for s in sources:
        envelope, fcen = s.src, s.src.frequency
        if callable(getattr(envelope, "fourier_transform", None)):
            s.amplitude /= envelope.fourier_transform(fcen)

