"""Handling of objective functions and objective quantities."""

from abc import ABC, abstractmethod
import numpy as np
import meep as mp
from autograd import elementwise_grad as egrad  # for functions that vectorize over inputs
from .filter_source import FilteredSource
from matplotlib import pyplot as plt

class ObjectiveQuantitiy(ABC):
    @abstractmethod
    def __init__(self):
        return
    @abstractmethod
    def register_monitors(self):
        return
    @abstractmethod
    def place_adjoint_source(self):
        return

class EigenmodeCoefficient(ObjectiveQuantitiy):
    def __init__(self,sim,volume,mode,forward=True,k0=None,**kwargs):
        '''
        time_src ............... time dependence of source
        '''
        self.sim = sim
        self.volume=volume
        self.mode=mode
        self.forward = 0 if forward else 1
        self.normal_direction = None
        self.k0 = k0
        self.eval = None
        self.EigenMode_kwargs = kwargs
        return
    
    def register_monitors(self,fcen,df,nf):
        self.fcen=fcen
        self.df=df
        self.nf=nf

        self.monitor = self.sim.add_flux(self.fcen,self.df,self.nf,mp.FluxRegion(center=self.volume.center,size=self.volume.size))
        self.normal_direction = self.monitor.normal_direction
        return self.monitor
    
    def place_adjoint_source(self,dJ,dt,time):
        '''
        dJ ........ the user needs to pass the dJ/dMonitor evaluation
        dt ........ the timestep size from sim.fields.dt of the forward sim
        time ...... the forward simulation time in meeep units
        '''
        dJ = np.atleast_1d(dJ)
        # determine starting kpoint for reverse mode eigenmode source
        direction_scalar = 1 if self.forward else -1
        if self.k0 is None:
            if self.normal_direction == 0:
                k0 = direction_scalar * mp.Vector3(x=1)
            elif self.normal_direction == 1:
                k0 = direction_scalar * mp.Vector3(y=1)
            elif self.normal_direction == 2:
                k0 == direction_scalar * mp.Vector3(z=1)
        else:
            k0 = direction_scalar * self.k0
        
        # -------------------------------------- #
        # Get scaling factor 
        # -------------------------------------- #
        da_dE = 0.5*(1/self.sim.resolution * 1/self.sim.resolution * self.cscale) 
        scale = da_dE * dJ * 1j * 2 * np.pi * self.freqs / np.array([self.time_src.fourier_transform(f) for f in self.freqs]) # final scale factor
        
        if self.freqs.size == 1:
            # Single frequency simulations. We need to drive it with a time profile.
            src = self.time_src
            amp = scale
        else:
            # Multifrequency simulations just use the desired frequency profile to generate the time profile.
            src = FilteredSource(self.time_src.frequency,self.freqs,scale,dt,time,self.time_src) # generate source from braodband response
            amp = 1
        # generate source object
        self.source = mp.EigenModeSource(src,
                    eig_band=self.mode,
                    direction=mp.NO_DIRECTION,
                    eig_kpoint=k0,
                    amplitude=amp,
                    size=self.volume.size,
                    center=self.volume.center,
                    **self.EigenMode_kwargs)
        
        return self.source

    def __call__(self):
        # For single frequency simulations, we just need a workable time profile. 
        # so just grab the first available time profile and use that.
        self.time_src = self.sim.sources[0].src

        # Eigenmode data
        ob = self.sim.get_eigenmode_coefficients(self.monitor,[self.mode],**self.EigenMode_kwargs)
        self.eval = np.squeeze(ob.alpha[:,:,self.forward]) # record eigenmode coefficients for scaling   
        self.cscale = ob.cscale # pull scaling factor

        # record all freqs of interest
        self.freqs = np.atleast_1d(mp.get_eigenmode_freqs(self.monitor))

        # get f0 frequency index
        self.fcen_idx = np.argmin(np.abs(self.freqs-self.fcen))

        return self.eval