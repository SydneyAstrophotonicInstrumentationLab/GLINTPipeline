#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Apr 10 11:59:49 2019

@author: mam
"""

import numpy as np
import cupy as cp
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit, leastsq, least_squares
from timeit import default_timer as time
import h5py
import os

interpolate_kernel = cp.ElementwiseKernel(
    'float32 x_new, raw float32 xp, int32 xp_size, raw float32 yp', 
    'raw float32 y_new',
    
    '''  
    int high = xp_size - 1;
    int low = 0;
    int mid = 0;
    
    while(high - low > 1)
    {
        mid = (high + low)/2;
        
        if (xp[mid] <= x_new)
        {
            low = mid;
        }
        else
        {
            high = mid;
        }
    }
    y_new[i] = yp[low] + (x_new - xp[low])  * (yp[low+1] - yp[low]) / (xp[low+1] - xp[low]);

    if (x_new < xp[0])
    {
         y_new[i] = yp[0];
    }
    else if (x_new > xp[xp_size-1])
    {
         y_new[i] = yp[xp_size-1];
    }
        
    '''
    )
    
def rv_generator(bins_cent, pdf, nsamp):
    '''
    bins_cent : x-axis of the histogram
    pdf : normalized arbitrary pdf to use to generate rv
    '''

    bin_width = bins_cent[1] - bins_cent[0]
    cdf = cp.cumsum(pdf, dtype=cp.float32) * bin_width
    cdf, mask = cp.unique(cdf, True)
    
    cdf_bins_cent = bins_cent[mask]
    cdf_bins_cent = cdf_bins_cent +  bin_width/2.

    rv_uniform = cp.random.rand(nsamp, dtype=cp.float32)
    output_samples = cp.zeros(rv_uniform.shape, dtype=cp.float32)
    interpolate_kernel(rv_uniform, cdf, cdf.size, cdf_bins_cent, output_samples)
    
    return output_samples


def load_dark(data):
    data_file = h5py.File(data)
    hist = np.array(data_file['dark/histogram'])
    bin_edges = np.array(data_file['dark/bins_edges'])
    del data
    
    return hist, bin_edges
    
def load_data(data):
    null_data = [[],[],[],[],[],[]]
    null_err_data = [[],[],[],[],[],[]]
    photo_data = [[],[],[],[]]
    photo_err_data = [[],[],[],[]]
    wl_scale = []
    
    for d in data:
        with h5py.File(d) as data_file:
            wl_scale.append(np.array(data_file['null1/wl_scale']))
            
            for i in range(6):
                null_data[i].append(np.array(data_file['null%s/null'%(i+1)]))
                null_err_data[i].append(np.array(data_file['null%s/null_err'%(i+1)]))
                
            photo_data[0].append(np.array(data_file['null1/pA'])) # Fill with beam 1 intensity
            photo_data[1].append(np.array(data_file['null1/pB'])) # Fill with beam 2 intensity
            photo_data[2].append(np.array(data_file['null4/pA'])) # Fill with beam 3 intensity
            photo_data[3].append(np.array(data_file['null4/pB'])) # Fill with beam 4 intensity
            photo_err_data[0].append(np.array(data_file['null1/pA_err'])) # Fill with beam 1 error
            photo_err_data[1].append(np.array(data_file['null1/pB_err'])) # Fill with beam 2 error
            photo_err_data[2].append(np.array(data_file['null4/pA_err'])) # Fill with beam 3 error
            photo_err_data[3].append(np.array(data_file['null4/pB_err'])) # Fill with beam 4 error          
            
    # Merge data along frame axis
    for i in range(6):
        null_data[i] = [selt for elt in null_data[i] for selt in elt]
        null_err_data[i] = [selt for elt in null_err_data[i] for selt in elt]
        
        if i < 4:
            photo_data[i] = [selt for elt in photo_data[i] for selt in elt]
            photo_err_data[i] = [selt for elt in photo_err_data[i] for selt in elt]
            
    null_data = np.array(null_data)
    null_err_data = np.array(null_err_data)
    photo_data = np.array(photo_data)
    photo_err_data = np.array(photo_err_data)
    wl_scale = np.array(wl_scale)
    
    return {'null':null_data, 'photo':photo_data, 'wl_scale':wl_scale, 'null_err':null_err_data, 'photo_err':photo_err_data}

def getHistogram(data, bins, density, target='cpu'):
    pdf, bin_edges = np.histogram(data, bins=bins, density=density)
    bins_cent = bin_edges[:-1] + np.diff(bin_edges[:2])/2.
    
    if target == 'gpu':
        pdf, bins_cent = cp.asarray(pdf, dtype=cp.float32), cp.asarray(bins_cent, dtype=cp.float32)
        
    return pdf, bins_cent

def computeNullDepth0(I1, I2, phase, visibility, dark_null, dark_antinull):
    Iminus = I1 + I2 - 2 * np.sqrt(I1 * I2) * visibility * np.cos(phase) + dark_null
    Iplus = I1 + I2 + 2 * np.sqrt(I1 * I2) * visibility * np.cos(phase) + dark_antinull
    null = Iminus / Iplus
    return null

def computeNullDepth(I1, I2, phase, visibility, dark_null, dark_antinull):
    Iminus = I1 + I2 - 2 * np.sqrt(I1 * I2) * visibility * np.cos(phase) + dark_null
    Iplus = I1 + I2 + 2 * np.sqrt(I1 * I2) * visibility * np.cos(phase) + dark_antinull
    null = Iminus / Iplus
    return null

