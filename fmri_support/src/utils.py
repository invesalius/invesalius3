import numpy as np
from nilearn.connectome import ConnectivityMeasure

def manual_flatten(vol):
    """ Flatten fmri volume manually in raster scan order """
    x,y,z,t = vol.shape
    ret = np.zeros((x*y*z, t))
    
    # iterate in raster fashion
    for nx in range(x):
        for ny in range(y):
            for nz in range(z):
                ret[nx*y*z + ny * z + nz,:] = vol[nx,ny,nz]
    return ret

def FC(series,verbose=False):
    """
    Information:
    ------------
    Compute the static functional connectivity matrix of a timeseries of fMRI

    Parameters
    ----------
    series::[2darray<float>]
        fMRI timeseries of dimension : (nb timepoints, nb regions)

    Returns
    -------
    fc::[2darray<float>]
        FC of interest of dimension : (nb regions, nb regions)
    """
    # Removal of NaN
    S = series[np.isnan(series).sum(axis=1) == 0]

    # Arbitrary cutoff for relevance of correlation
    if S.shape[0] < 10: 
        if verbose: print("Less than 10 timepoints for correlation")
        return 0 

    correlation_measure = ConnectivityMeasure(kind='correlation')
    fc = correlation_measure.fit_transform([S])[0]
    return fc