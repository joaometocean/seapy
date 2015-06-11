#!/usr/bin/env python
"""
  grid

  This module handles general model grid information, whether from ROMS or
  other models; however, it is mostly geared towards ROMS

  Written by Brian Powell on 10/09/13
  Copyright (c)2013 University of Hawaii under the BSD-License.
"""
from __future__ import print_function

import netCDF4
import datetime
import os
import re
import seapy
import numpy as np
from scipy.interpolate import griddata
import scipy.spatial
import matplotlib.path

def asgrid(grid):
    """
    Return either an existing or new grid object. This decorator will ensure that
    the variable being used is a seapy.model.grid. If it is not, it will attempt
    to construct a new grid with the variable passed.

    Parameters
    ----------
    grid: string or model.seapy.grid
        Input variable to cast. If it is already a grid, it will return it;
        otherwise, it attempts to construct a new grid.

    Returns
    -------
    seapy.model.grid

    """
    if grid is None:
        raise AttributeError("No grid was specified")
    if isinstance(grid,seapy.model.grid):
        return grid
    else:
        return seapy.model.grid(filename=grid)

class grid:
    def __init__(self, filename=None, lat=None, lon=None, z=None,
                 depths=True, cgrid=False):
        """
            Class to wrap around a numerical model grid for oceanography.
            It attempts to track latitude, longitude, z, and other
            parameters. A grid can be constructed by specifying a filename or
            by specifying lat, lon, and z.

            Parameters
            ----------
            filename : filename to load to build data structure [optional]
                or
            lat     : latitude values of grid
            lon     : longitude values of grid
            z       : z-level depths of grid

            Options
            -------
            depths  : Set the depths of the grid [True]
            cgrid   : Whether the grid is an Arakawa C-Grid [False]
        """
        self.filename = filename
        self.cgrid = cgrid

        if self.filename is not None:
            self._initfile()
            self._isroms = True if \
              (len(list(set(("s_rho","pm","pn","theta_s","theta_b",
                            "vtransform", "vstretching")).intersection(
                            set(self.__dict__)))) > 0) else False
            self.cgrid = True if self._isroms else self.cgrid
        else:
            self._nc = None
            self.lat_rho = lat
            self.lon_rho = lon
            self.z = z
            self.cgrid = False
        self._verify_shape()
        if depths:
            self.set_dims()
            self.set_depth()
            self.set_thickness()
        if self._nc is not None:
            self._nc.close()
            self._nc = None

    def _initfile(self):
        """
        Using an input file, try to load as much information
        as can be found in the given file.

        Parameters
        ----------
        None

        Returns
        -------
        None : sets attributes in grid

        """
        # Define a dictionary to go through and convert netcdf variables
        # to internal class attributes
        gvars = {"lat_rho": ["lat_rho", "lat", "latitude"],
                 "lon_rho": ["lon_rho", "lon", "longitude"],
                 "lat_u": ["lat_u"],
                 "lon_u": ["lon_u"],
                 "lat_v": ["lat_v"],
                 "lon_v": ["lon_v"],
                 "mask_rho": ["mask_rho", "mask"],
                 "mask_u": ["mask_u"],
                 "mask_v": ["mask_v"],
                 "angle": ["angle"],
                 "h": ["h"],
                 "n": ["N"],
                 "theta_s": ["theta_s"],
                 "theta_b": ["theta_b"],
                 "tcline": ["Tcline"],
                 "hc": ["hc"],
                 "vtransform": ["Vtransform"],
                 "vstretching": ["Vstretching"],
                 "s_rho": ["s_rho"],
                 "cs_r": ["Cs_r"],
                 "f": ["f"],
                 "pm": ["pm"],
                 "pn": ["pn"],
                 "z": ["z","depth","lev"]
                }

        # Open the file
        self._nc = netCDF4.Dataset(self.filename,"r")
        self.name = re.search("[^\.]*",
                              os.path.basename(self.filename)).group();
        for var in gvars:
            for inp in gvars[var]:
                if inp in self._nc.variables:
                    self.__dict__[var] = self._nc.variables[inp][:]

    def _verify_shape(self):
        """
        Verify the dimensionality of the system, create variables that
        can be generated from the others if they aren't already loaded

        Parameters
        ----------
        None

        Returns
        -------
        None : sets attributes in grid
        """
        # Check that we have the minimum required data
        if ("lat_rho" or "lon_rho") not in self.__dict__:
            raise AttributeError(
                "grid does not have attribute lat_rho or lon_rho")

        # Check that it is formatted into 2-D
        self.spatial_dims=self.lat_rho.ndim
        if self.lat_rho.ndim==1 and self.lon_rho.ndim==1:
            [self.lon_rho, self.lat_rho] = np.meshgrid(self.lon_rho,
                                                       self.lat_rho)

        # Compute the dimensions
        self.ln = int(self.lat_rho.shape[0])
        self.lm = int(self.lat_rho.shape[1])
        self.shape = (self.ln, self.lm)

    def __repr__(self):
        return str(self)

    def __str__(self):
        return "\n".join((self.filename if self.filename else "Constructed",
            "{:d}x{:d}x{:d}: {:s} with {:s}".format(self.n,self.ln,self.lm,
                "C-Grid" if self.cgrid else "A-Grid",
                "S-level" if self._isroms else "Z-Level"),
            "Available: " + ",".join(sorted(list(self.__dict__.keys())))))

    def set_dims(self):
        """
        Compute the dimension attributes of the grid based upon the information provided.

        Parameters
        ----------
        None

        Returns
        -------
        None : sets attributes in grid
        """
        # If C-Grid, set the dimensions for consistency
        if self.cgrid:
            self.eta_rho = self.ln
            self.eta_u = self.ln
            self.eta_v = self.ln-1
            self.xi_rho = self.lm
            self.xi_u = self.lm-1
            self.xi_v = self.lm

        # Set the number of layers
        if "n" not in self.__dict__:
            if "s_rho" in self.__dict__:
                self.n = int(self.s_rho.size)
            elif "z" in self.__dict__:
                self.n = int(self.z.size)
        else:
            self.n = int(self.n)

        # Generate the u- and v-grids
        if ("lat_u" or "lon_u") not in self.__dict__:
            if self.cgrid:
                self.lat_u = 0.5*(self.lat_rho[:,1:] - self.lat_rho[:,0:-1])
                self.lon_u = 0.5*(self.lon_rho[:,1:] - self.lon_rho[:,0:-1])
            else:
                self.lat_u = self.lat_rho
                self.lon_u = self.lon_rho
        if ("lat_v" or "lon_v") not in self.__dict__:
            if self.cgrid:
                self.lat_v = 0.5*(self.lat_rho[1:,:] - self.lat_rho[0:-1,:])
                self.lon_v = 0.5*(self.lon_rho[1:,:] - self.lon_rho[0:-1,:])
            else:
                self.lat_v = self.lat_rho
                self.lon_v = self.lon_rho
        if "mask_rho" in self.__dict__:
            if "mask_u" not in self.__dict__:
                if self.cgrid:
                    self.mask_u = self.mask_rho[:,1:] * self.mask_rho[:,0:-1]
                else:
                    self.mask_u = self.mask_rho
            if "mask_v" not in self.__dict__:
                if self.cgrid:
                    self.mask_v = self.mask_rho[1:,:] * self.mask_rho[0:-1,:]
                else:
                    self.mask_v = self.mask_rho

        # Compute the resolution
        if "pm" in self.__dict__:
            self.dm = 1.0/self.pm
        else:
            self.dm = np.ones(self.lon_rho.shape,dtype=np.float32)
            self.dm[:,0:-1] = seapy.earth_distance( self.lon_rho[:,1:],
                                      self.lat_rho[:,1:],
                                      self.lon_rho[:,0:-1],
                                      self.lat_rho[:,0:-1]).astype(np.float32)
            self.dm[:,-1] = self.dm[:,-2]
        if "pn" in self.__dict__:
            self.dn = 1.0/self.pn
        else:
            self.dn = np.ones(self.lat_rho.shape,dtype=np.float32)
            self.dn[0:-1,:] = seapy.earth_distance( self.lon_rho[1:,:],
                                      self.lat_rho[1:,:],
                                      self.lon_rho[0:-1,:],
                                      self.lat_rho[0:-1,:] ).astype(np.float32)
            self.dn[-1,:] = self.dn[-2,:]

        # Compute the Coriolis
        if "f" not in self.__dict__:
            omega=2*np.pi/86400;
            self.f=2*omega*np.sin(np.radians(self.lat_rho))

        # Set the grid index coordinates
        self.I, self.J=np.meshgrid(np.arange(0,self.lm),np.arange(0,self.ln))

    def set_mask_h(self, fld=None):
        """
        Compute the mask and h array from a z-level model

        Parameters
        ----------
        fld : np.array
            3D array of values (such as temperature) to analyze to determine
            where the bottom and land lie

        Returns
        -------
        None : sets mask and h attributes in grid

        """
        if fld is None and self.filename is not None:
            if self._nc is None:
                self._nc = netCDF4.Dataset(self.filename)

            # Try to load a field from the file
            for f in ["temp","temperature"]:
                if f in self._nc.variables:
                    fld = self._nc.variables[f][0,:,:,:]
                    fld = np.ma.array(fld, mask=np.isnan(fld))
                    break

            # Close the file
            self._nc.close()

        # If we don't have a field to examine, then we cannot compute the
        # mask and bathymetry
        if fld is None:
            raise AttributeError("Missing 3D field to evaluate")

        # Next, we go over the field to examine the depths and mask
        self.h = np.zeros(self.lat_rho.shape)
        self.mask_rho = np.zeros(self.lat_rho.shape)
        for k in range(0,self.z.size):
            water = np.nonzero( np.logical_not(fld.mask[k,:,:]) )
            self.h[water] = self.z[k]
            if k==0:
                self.mask_rho[water] = 1.0
        self.mask_u = self.mask_v = self.mask_rho


    def set_depth(self):
        """
        Compute the depth of each cell for the model grid.

        Parameters
        ----------
        None

        Returns
        -------
        None : sets depth attributes in grid
        """
        if self._isroms:
            if "s_rho" not in self.__dict__:
                self.s_rho, self.cs_r = seapy.roms.stretching(
                    self.vstretching, self.theta_s, self.theta_b,
                    self.hc, self.n)
            self.depth_rho = seapy.roms.depth(
                self.vtransform, self.h, self.hc, self.s_rho, self.cs_r)
            self.depth_u=seapy.model.rho2u(self.depth_rho)
            self.depth_v=seapy.model.rho2v(self.depth_rho)
        else:
            d = self.z.copy()
            l = np.nonzero(d>0)
            d[l]=-d[l]
            self.depth_rho = np.kron( np.kron(
                                    d, np.ones(self.lon_rho.shape[1])),
                                    np.ones(self.lon_rho.shape[0])).reshape(
                                    [self.z.size,self.lon_rho.shape[0],
                                     self.lon_rho.shape[1]])
            if self.cgrid:
                self.depth_u=seapy.model.rho2u(self.depth_rho)
                self.depth_v=seapy.model.rho2v(self.depth_rho)
            else:
                self.depth_u = self.depth_rho
                self.depth_v = self.depth_rho

    def set_thickness(self):
        """
        Compute the thickness of each cell for the model grid.

        Parameters
        ----------
        None

        Returns
        -------
        None : sets thick attributes in grid
        """
        if "n" not in self.__dict__:
            self.set_dims()
        if self._isroms:
            s_w, cs_w = seapy.roms.stretching(
                self.vstretching, self.theta_s, self.theta_b, self.hc,
                self.n, w_grid=True)
            self.thick_rho = seapy.roms.thickness(
                self.vtransform, self.h, self.hc, s_w, cs_w)
            self.thick_u=seapy.model.rho2u(self.thick_rho)
            self.thick_v=seapy.model.rho2v(self.thick_rho)
        else:
            d=np.abs(self.z.copy())
            w=d*0
            # Check which way the depths are going
            if d[0] < d[-1]:
                w[0]=d[0]
                w[1:]=d[1:]-d[0:-1]
            else:
                w[-1]=d[-1]
                w[0:-1]=d[0:-1]-d[1:]

            self.thick_rho = np.kron( np.kron( w,
                                    np.ones(self.lon_rho.shape[1])),
                                    np.ones(self.lon_rho.shape[0])).reshape(
                                    [self.z.size,self.lon_rho.shape[0],
                                     self.lon_rho.shape[1]])
            if self.cgrid:
                self.thick_u=seapy.model.rho2u(self.thick_rho)
                self.thick_v=seapy.model.rho2v(self.thick_rho)
            else:
                self.thick_u = self.thick_rho
                self.thick_v = self.thick_rho


    def plot_trace(self, basemap, **kwargs):
        """
        Trace the boundary of the grid onto a map projection

        Parameters
        ----------
        basemap: basemap instance
            The basemap instance to use for drawing
        **kwargs: optional
            Arguments to pass to the plot routine

        Returns
        -------
        None
        """
        lon=np.concatenate([self.lon_rho[0,:], self.lon_rho[:,-1],
                            self.lon_rho[-1,::-1], self.lon_rho[::-1,0]])
        lat=np.concatenate([self.lat_rho[0,:], self.lat_rho[:,-1],
                            self.lat_rho[-1,::-1], self.lat_rho[::-1,0]])
        x,y=basemap(lon,lat)
        basemap.plot(x,y,**kwargs)

    def to_netcdf(self, nc):
        """
        Write all available grid information into the records present in the netcdf file.
        This is used to pre-fill boundary, initial, etc. files that require some of the
        grid information.

        Parameters
        ----------
        nc : netCDF4
            File to fill all known records from the grid information

        Returns
        -------
        None
        """
        for var in nc.variables:
            if hasattr(self,var.lower()):
                nc.variables[var][:]=getattr(self,var.lower())

    def nearest(self, lon, lat, grid="rho"):
        """
        Find the indices nearest to each point in the given list of
        longitudes and latitudes.

        Parameters
        ----------
        lon : ndarray,
            longitude of points to find
        lat : ndarray
            latitude of points to find
        grid : string, optional,
            "rho", "u", or "v" grid to search

        Returns
        -------
        indices : tuple of ndarray
            The indices for each dimension of the grid that are closest
            to the lon/lat points specified
        """

        glat = getattr(self,"lat_"+grid)
        glon = getattr(self,"lon_"+grid)
        xy = np.dstack([glat.ravel(), glon.ravel()])[0]
        pts = np.dstack([np.atleast_1d(lat), np.atleast_1d(lon)])[0]
        grid_tree = scipy.spatial.cKDTree(xy)
        dist, idx = grid_tree.query(pts)
        return np.unravel_index(idx,glat.shape)

    def ij(self, points, asint=False):
        """
        Compute the fractional i,j indices of the grid from a
        set of lat, lon points.

        Parameters
        ----------
        points : list of tuples
            longitude, latitude points to compute i,j indicies
        asint : bool, optional,
            if True, return the integer index rather than fractional

        Returns
        -------
        out : tuple of ndarray (with netcdf-type indexing),
            list of i,j indices for the given lat/lon points

        Examples
        --------
        >>> a = [(-158, 20), (-160.5, 22.443)]
        >>> idx = g.ij(a)
        """

        # Interpolate the lat/lons onto the I, J
        xgrid = griddata((self.lon_rho.ravel(),self.lat_rho.ravel()),
                         self.I.ravel(),points,method="linear")
        ygrid = griddata((self.lon_rho.ravel(),self.lat_rho.ravel()),
                         self.J.ravel(),points,method="linear")

        if asint:
            return (np.floor(ygrid).astype(int), np.floor(xgrid).astype(int))
        else:
            return (ygrid,xgrid)

    def mask_poly(self, vertices, lat_lon=False, radius=0.0):
        """
        Create an np.masked_array of the same shape as the grid with values
        masked if they are not within the given polygon vertices

        Parameters
        ----------
        vertices: list of tuples,
            points that define the vertices of the polygon
        lat_lon : bool, optional,
            If True, the vertices are a list of lon, lat points rather
            than indexes

        Returns
        -------
        mask : np.masked_array
            mask of values that are located within the polygon

        Examples
        --------
        >>> vertices = [ (1,2), (4,5), (1,3) ]
        >>> mask = grid.mask_poly(vertices)
        """
        # If lat/lon vertices are given, we need to put these onto
        # the grid coordinates
        if lat_lon:
            points = self.ij(vertices,asint=True)
            vertices = list(zip(points[0],points[1]))

        # Now, with grid coordinates, test the grid against the vertices
        poly=matplotlib.path.Path(vertices)
        inside=poly.contains_points(np.vstack((self.J.flatten(),
                                               self.I.flatten())).T,
                                    radius=radius)
        return np.ma.masked_where(inside.reshape(self.lat_rho.shape),
                                  np.ones(self.lat_rho.shape))



