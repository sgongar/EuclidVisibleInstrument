"""
Bias Calibration
================

This simple script can be used to study the number of bias frames required to meet the VIS calibration requirements.

The following requirements related to the bias calibration has been taken from GDPRD.

R-GDP-CAL-052:
The contribution of the residuals of VIS bias subtraction to the *error on the determination of each ellipticity
component* of the local PSF shall not exceed 3x10-5 (one sigma).

R-GDP-CAL-062:
The contribution of the residuals of VIS bias subtraction to the *relative error* \sigma(R2)/R2 on the determination of
the local PSF R2 shall not exceed 1x10-4 (one sigma).

:requires: PyFITS
:requires: NumPy
:requires: matplotlib
:requires: VISsim-Python

:author: Sami-Matias Niemi
:contact: smn2@mssl.ucl.ac.uk
"""
import matplotlib
matplotlib.rc('text', usetex=True)
matplotlib.rcParams['font.size'] = 17
matplotlib.rc('xtick', labelsize=14)
matplotlib.rc('axes', linewidth=1.1)
matplotlib.rcParams['legend.fontsize'] = 11
matplotlib.rcParams['legend.handlelength'] = 3
matplotlib.rcParams['xtick.major.size'] = 5
matplotlib.rcParams['ytick.major.size'] = 5
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from matplotlib import cm
import pyfits as pf
import numpy as np
import math, datetime, cPickle, itertools
from analysis import shape
from support import logger as lg
from support import surfaceFitting as sf
from support import bleedingtest as write
from support import files as fileIO


def testBiasCalibrationDelta(log, numdata=2066, floor=995, xsize=2048, ysize=2066, order=3, biases=15, surfaces=100,
                        file='psf1x.fits', psfs=500, psfscale=1.e3, debug=False, plots=False):
    """
    Derive the PSF ellipticities for a given number of random surfaces with random PSF positions
    and a given number of biases median combined and compare to the nominal PSF ellipticity.

    This function can be used to derive the error (delta) in determining ellipticity and size given
    a reference PSF.

    Choices that need to be made and effect the results:

        #. bias surface that is assumed (amplitude, complexity, etc.)
        #. whether the order of the polynomial surface to be fitted is known or not
        #. size of the Gaussian weighting function when calculating the ellipticity components

    There are also other choices such as the number of PSFs and scaling and the random numbers generated for
    the surface that also affect the results, however, to a lesser degree.

    Generates a set of plots that can be used to inspect the simulation.
    """
    log.info('Processing file %s' % file)
    #read in data without noise or bias level and scale it to 20k electrons
    data = pf.getdata(file)
    data /= np.max(data)
    data *= psfscale

    #derive the reference value from the scaled data
    sh = shape.shapeMeasurement(data.copy(), log)
    results = sh.measureRefinedEllipticity()
    #sh.writeFITS(results['GaussianWeighted'], file.replace('.fits', 'Gweighted.fits'))
    #rescale to not loose numerical accuracy
    reference1 = results['e1']
    reference2 = results['e2']
    refR2 = results['R2']
    reference = math.sqrt(reference1*reference1 + reference2*reference2)

    print 'Reference Ellipticities and R2 :'
    print reference1, reference2, reference, refR2

    #generate a random quadrant surface representing BIAS without noise
    #modify zclean if a different order surface is needed
    x = np.random.random(numdata)
    y = np.random.random(numdata)
    xx, yy = np.meshgrid(np.linspace(x.min(), x.max(), xsize),
                         np.linspace(y.min(), y.max(), ysize))
    zclean = yy - xx + 0.78*xx**2 + 15.0*yy**2 - 1.75*xx*yy + 10.0*xx**3 + 0.3*yy**3 + floor

    #random positions for the PSFs, these positions are the lower corners
    xpositions = np.random.random_integers(0, zclean.shape[1] - data.shape[1], psfs)
    ypositions = np.random.random_integers(0, zclean.shape[0] - data.shape[0], psfs)

    if plots:
        # generate 2D plot
        im = plt.imshow(zclean, extent=(0, ysize, xsize, 0))
        plt.scatter(xpositions/data.shape[1]/2, ypositions/data.shape[0]/2)
        c1 = plt.colorbar(im)
        c1.set_label('BIAS [ADUs]')
        plt.xlim(0, ysize)
        plt.ylim(0, xsize)
        plt.xlabel('Y [pixels]')
        plt.ylabel('X [pixels]')
        plt.savefig('NoNoise2D.png')
        plt.close()
        #and 3D
        fig = plt.figure()
        ax = Axes3D(fig)
        ax.plot_surface(xx*xsize, yy*ysize, zclean, rstride=100, cstride=100, alpha=0.6, cmap=cm.jet)
        ax.set_xlabel('X [pixels]')
        ax.set_ylabel('Y [pixels]')
        ax.set_zlabel('BIAS [ADUs]')
        plt.savefig('NoNoise.png')
        plt.close()

    out = {}
    #number of biases to median combine
    for a in xrange(biases):
        print 'Number of Biases: %i / %i' % (a+1, biases)

        #data storage
        de1 = []
        de2 = []
        de = []
        R2 = []
        R2abs = []

        #number of random readnoised surfaces to loop over
        for b in xrange(surfaces):

            print 'Surface: %i / %i' % (b+1, surfaces)

            #add readout noise based on a+1 median combined biases
            z = addReadoutNoise(zclean.copy(), number=a+1)

            if plots:
                # generate 2D plot
                im = plt.imshow(z, extent=(0, ysize, xsize, 0))
                c1 = plt.colorbar(im)
                c1.set_label('BIAS [ADUs]')
                plt.xlim(0, ysize)
                plt.ylim(0, xsize)
                plt.xlabel('Y [pixels]')
                plt.ylabel('X [pixels]')
                plt.savefig('Readnoised%i%i.png' % (a+1, b+1))
                plt.close()
                #and 3D
                fig = plt.figure()
                ax = Axes3D(fig)
                ax.plot_surface(xx*xsize, yy*ysize, z, rstride=100, cstride=100, alpha=0.6, cmap=cm.jet)
                ax.set_xlabel('X [pixels]')
                ax.set_ylabel('Y [pixels]')
                ax.set_zlabel('BIAS [ADUs]')
                plt.savefig('Readnoised3D%i%i.png' % (a+1, b+1))
                plt.close()

            # Fit 2d polynomial to the noised data
            m = sf.polyfit2d(xx.ravel(), yy.ravel(), z.ravel(), order=order)
            # Evaluate it on a rectangular grid
            fitted = sf.polyval2d(xx, yy, m)

            if plots:
                # generate 2D plot
                im = plt.imshow(fitted, extent=(0, ysize, xsize, 0))
                c1 = plt.colorbar(im)
                c1.set_label('BIAS [ADUs]')
                plt.xlim(0, ysize)
                plt.ylim(0, xsize)
                plt.xlabel('Y [pixels]')
                plt.ylabel('X [pixels]')
                plt.savefig('Fitted2D%i.png' % (a+1))
                plt.close()
                #and 3D
                fig = plt.figure()
                ax = Axes3D(fig)
                ax.plot_surface(xx*xsize, yy*ysize, fitted, rstride=100, cstride=100, alpha=0.6, cmap=cm.jet)
                ax.set_xlabel('X [pixels]')
                ax.set_ylabel('Y [pixels]')
                ax.set_zlabel('BIAS [ADUs]')
                plt.savefig('Fitted3D%i.png' % (a+1))
                plt.close()

            #subtract the no noise surface from the fit
            fitted -= zclean #- 0.5

            if plots:
                # generate 2D plot
                im = plt.imshow(fitted, extent=(0, ysize, xsize, 0))
                c1 = plt.colorbar(im)
                c1.set_label(r'$\Delta$BIAS [ADUs]')
                plt.xlim(0, ysize)
                plt.ylim(0, xsize)
                plt.xlabel('Y [pixels]')
                plt.ylabel('X [pixels]')
                plt.savefig('Residual2D%i%i.png' % (a+1, b+1))
                plt.close()
                #and 3D
                fig = plt.figure()
                ax = Axes3D(fig)
                ax.plot_surface(xx*xsize, yy*ysize, fitted, rstride=100, cstride=100, alpha=0.6, cmap=cm.jet)
                ax.set_xlabel('X [pixels]')
                ax.set_ylabel('Y [pixels]')
                ax.set_zlabel(r'$\Delta$BIAS [ADUs]')
                ax.set_zlim(-0.01, 0.01)
                plt.savefig('Residual3D%i%i.png' % (a+1, b+1))
                plt.close()

            #loop over the PSFs
            for xpos, ypos in zip(xpositions, ypositions):
                #measure e and R2 from the postage stamp image
                small = fitted[ypos:ypos+data.shape[0], xpos:xpos+data.shape[1]].copy()
                small += data.copy()
                sh = shape.shapeMeasurement(small.copy(), log)
                results = sh.measureRefinedEllipticity()

                #save delta values
                de1.append(results['e1'] - reference1)
                de2.append(results['e2'] - reference2)
                de.append(math.sqrt(results['e1']*results['e1'] + results['e2']*results['e2']) - reference)
                R2.append((results['R2'] - refR2) / refR2)
                R2abs.append((results['R2'] - refR2))

                if debug:
                    print xpos, ypos
                    write.writeFITSfile(small/data, 'testResidualDelta.fits')
                    print 'DEBUG mode -- exiting now'
                    import sys; sys.exit()
        if plots:
            plotDeltaEs(de1, de2, de, 'MultipleBiases%i.pdf' % (a+1), title='%i Biases median combined' % (a+1))

        out[a+1] = [de1, de2, de, R2, R2abs]

    return out


def testBiasCalibrationSigma(log, numdata=2066, floor=1000, xsize=2048, ysize=2066, order=3, biases=15, surfaces=100,
                             file='psf1x.fits', psfs=500, psfscale=7.e4, gain=3.5,
                             debug=False, plots=True):
    """
    Derive the PSF ellipticities for a given number of random surfaces with random PSF positions
    and a given number of biases median combined.

    This function is to derive the the actual values so that the knowledge (variance) can be studied.

    Choices that need to be made and effect the results:

        #. bias surface that is assumed (amplitude, complexity, etc.)
        #. whether the order of the polynomial surface to be fitted is known or not
        #. size of the Gaussian weighting function when calculating the ellipticity components

    There are also other choices such as the number of PSFs and scaling and the random numbers generated for
    the surface that also affect the results, however, to a lesser degree.

    Generates a set of plots that can be used to inspect the simulation.
    """
    log.info('Processing file %s' % file)

    #read in data without noise or bias level and renormalize it
    data = pf.getdata(file)
    data /= np.max(data)

    #generate a random quadrant surface representing BIAS without noise
    #modify zclean if a different order surface is needed
    x = np.random.random(numdata)
    y = np.random.random(numdata)
    xx, yy = np.meshgrid(np.linspace(x.min(), x.max(), xsize),
                         np.linspace(y.min(), y.max(), ysize))
    zclean = yy - xx + 0.78*xx**2 + 15.0*yy**2 - 1.75*xx*yy + 10.0*xx**3 + 0.3*yy**3 + (floor * gain)

    #random positions for the PSFs, these positions are the lower corners
    xpositions = np.random.random_integers(0, zclean.shape[1] - data.shape[1], psfs)
    ypositions = np.random.random_integers(0, zclean.shape[0] - data.shape[0], psfs)
    #random scalings for the PSFs, cannot be used because then scaling changes e and R2
    #psfscales = np.random.rand(psfs) * (psfscalemax - psfscalemin) + psfscalemin
    psfscales = np.ones(psfs) * psfscale

    # generate 2D plot
    if plots:
        im = plt.imshow(zclean, extent=(0, ysize, xsize, 0))
        plt.scatter(xpositions + (data.shape[1]/2), ypositions + (data.shape[0]/2), color='white')
        c1 = plt.colorbar(im)
        c1.set_label('BIAS [electrons]')
        plt.xlim(0, ysize)
        plt.ylim(0, xsize)
        plt.xlabel('Y [pixels]')
        plt.ylabel('X [pixels]')
        plt.savefig('NoNoise2D.png')
        plt.close()
        #and 3D
        fig = plt.figure()
        ax = Axes3D(fig)
        ax.plot_surface(xx*xsize, yy*ysize, zclean, rstride=100, cstride=100, alpha=0.6, cmap=cm.jet)
        ax.set_xlabel('X [pixels]')
        ax.set_ylabel('Y [pixels]')
        ax.set_zlabel('BIAS [electrons]')
        plt.savefig('NoNoise.png')
        plt.close()

    out = {}
    #number of biases to median combine
    for a in xrange(biases):
        print 'Number of Biases: %i / %i' % (a+1, biases)

        #data storage
        de1 = []
        de2 = []
        de = []
        R2 = []
        R2abs = []

        #number of random readnoised surfaces to loop over
        for b in xrange(surfaces):

            print 'Number of Random Realisations: %i / %i' % (b+1, surfaces)

            #add readout noise based on a+1 median combined bias
            #this surface needs to be integer, because it resembles a recorded one
            z = addReadoutNoise(zclean.copy(), number=a+1)

            if plots:
                # generate 2D plot
                im = plt.imshow(z, extent=(0, ysize, xsize, 0))
                c1 = plt.colorbar(im)
                c1.set_label('BIAS [electrons]')
                plt.xlim(0, ysize)
                plt.ylim(0, xsize)
                plt.xlabel('Y [pixels]')
                plt.ylabel('X [pixels]')
                plt.savefig('Readnoised%i%i.png' % (a+1, b+1))
                plt.close()
                #and 3D
                fig = plt.figure()
                ax = Axes3D(fig)
                ax.plot_surface(xx*xsize, yy*ysize, z, rstride=100, cstride=100, alpha=0.6, cmap=cm.jet)
                ax.set_xlabel('X [pixels]')
                ax.set_ylabel('Y [pixels]')
                ax.set_zlabel('BIAS [electrons]')
                plt.savefig('Readnoised3D%i%i.png' % (a+1, b+1))
                plt.close()

            # Fit 2d polynomial to the noised data
            m = sf.polyfit2d(xx.ravel(), yy.ravel(), z.ravel(), order=order)
            # Evaluate it on a rectangular grid
            fitted = sf.polyval2d(xx, yy, m)

            if plots:
                # generate 2D plot
                im = plt.imshow(fitted, extent=(0, ysize, xsize, 0))
                c1 = plt.colorbar(im)
                c1.set_label('BIAS [electrons]')
                plt.xlim(0, ysize)
                plt.ylim(0, xsize)
                plt.xlabel('Y [pixels]')
                plt.ylabel('X [pixels]')
                plt.savefig('Fitted2D%i.png' % (a+1))
                plt.close()
                #and 3D
                fig = plt.figure()
                ax = Axes3D(fig)
                ax.plot_surface(xx*xsize, yy*ysize, fitted, rstride=100, cstride=100, alpha=0.6, cmap=cm.jet)
                ax.set_xlabel('X [pixels]')
                ax.set_ylabel('Y [pixels]')
                ax.set_zlabel('BIAS [electrons]')
                plt.savefig('Fitted3D%i.png' % (a+1))
                plt.close()

            #subtract the no noise surface from the fit, adjust for integer conversion done earlier
            fitted -= zclean.copy()

            if plots:
                # generate 2D plot
                im = plt.imshow(fitted, extent=(0, ysize, xsize, 0))
                c1 = plt.colorbar(im)
                c1.set_label(r'$\Delta$BIAS [electrons]')
                plt.xlim(0, ysize)
                plt.ylim(0, xsize)
                plt.xlabel('Y [pixels]')
                plt.ylabel('X [pixels]')
                plt.savefig('Residual2D%i%i.png' % (a+1, b+1))
                plt.close()
                #and 3D
                fig = plt.figure()
                ax = Axes3D(fig)
                ax.plot_surface(xx*xsize, yy*ysize, fitted, rstride=100, cstride=100, alpha=0.6, cmap=cm.jet)
                ax.set_xlabel('X [pixels]')
                ax.set_ylabel('Y [pixels]')
                ax.set_zlabel(r'$\Delta$BIAS [electrons]')
                ax.set_zlim(-0.1, 0.1)
                plt.savefig('Residual3D%i%i.png' % (a+1, b+1))
                plt.close()

            #loop over the PSFs
            for xpos, ypos, scale in zip(xpositions, ypositions, psfscales):
                tmp = data.copy() * scale
                #measure e and R2 from the postage stamp image
                small = fitted[ypos:ypos+data.shape[0], xpos:xpos+data.shape[1]].copy()
                #print np.sum(small), np.average(small), np.median(small), small.shape
                small += tmp
                sh = shape.shapeMeasurement(small.copy(), log)
                results = sh.measureRefinedEllipticity()

                #save values
                de1.append(results['e1'])
                de2.append(results['e2'])
                de.append(math.sqrt(results['ellipticity']))
                R2.append(results['R2'])
                R2abs.append(results['R2'])

                if debug:
                    print xpos, ypos
                    write.writeFITSfile(small/data, 'testResidualSigma.fits')
                    print 'DEBUG mode -- exiting now'
                    import sys; sys.exit()
        if plots:
            plotEs(de1, de2, de, 'MBiases%i.png' % (a+1), title='%i Biases median combined' % (a+1))

        out[a+1] = [de1, de2, de, R2, R2abs]

    return out


def plotDeltaEs(deltae1, deltae2, deltae, output, title='', ymax=8, req=3):
    """
    Generates a simple plot showing the errors in the ellipticity components.
    """
    deltae1 = np.asarray(deltae1)
    deltae2 = np.asarray(deltae2)
    deltae = np.asarray(deltae)

    #plot histograms
    fig = plt.figure()
    ax = fig.add_subplot(111)
    plt.title(title)

    bins = np.arange(-6, 6.1, 0.1)
    ax.hist(deltae, bins=bins, label=r'$e$', alpha=0.3, normed=False)
    ax.hist(deltae1, bins=bins, label=r'$e_{1}$', alpha=0.2, normed=False)
    ax.hist(deltae2, bins=bins, label=r'$e_{2}$', alpha=0.1, normed=False)
    ax.axvline(x=req, c='g', ls='--', label='Requirement')
    ax.axvline(x=-req, c='g', ls='--')
    ax.set_xlim(-6, 6)

    ax.set_xlabel(r'$\Delta e_{i}\ , \ \ \ i \in [1,2] \ \ \ \ [10^{-5}]$')
    ax.set_ylabel('Probability Density')

    plt.legend(shadow=True, fancybox=True)
    plt.savefig('hist' + output)
    plt.close()

    #make scatter plots
    fig = plt.figure()
    ax = fig.add_subplot(111)
    plt.title(title)

    ax.plot(deltae, 'mD', label=r'$e$')
    ax.plot(deltae2, 'ys', label=r'$e_{2}$')
    ax.plot(deltae1, 'bo', label=r'$e_{1}$')
    ax.fill_between(np.arange(len(deltae1)), np.ones(len(deltae1))*req, ymax, facecolor='red', alpha=0.08)
    ax.fill_between(np.arange(len(deltae1)), -np.ones(len(deltae1))*req, -ymax, facecolor='red', alpha=0.08)
    ax.axhline(y=req, c='g', ls='--', label='Requirement')
    ax.axhline(y=-req, c='g', ls='--')

    ax.set_ylim(-ymax, ymax)
    ax.set_xlabel('Number of Iterations')
    ax.set_ylabel(r'$\Delta e_{i}\ , \ \ \ i \in [1,2] \ \ \ \ [10^{-5}]$')

    plt.text(0.5, 0.1,
             r'Average error in $e_{1}=$ %f and $e_{2}=$ %f' % (np.mean(deltae1), np.mean(deltae2)),
             ha='center',
             va='center',
             transform=ax.transAxes)

    plt.legend(shadow=True, fancybox=True, numpoints=1, ncol=2)
    plt.savefig(output)
    plt.close()


def plotEs(deltae1, deltae2, deltae, output, title=''):
    """
    Generates a simple plot showing the ellipticity components.
    """
    deltae1 = np.asarray(deltae1)
    deltae2 = np.asarray(deltae2)
    deltae = np.asarray(deltae)

    #plot histograms
    fig = plt.figure()
    ax = fig.add_subplot(111)
    plt.title(title)

    bins = 10
    # bins = np.arange(0.0, 0.2, 0.02)
    ax.hist(deltae, bins=bins, label=r'$e$', alpha=0.3, normed=False)
    ax.hist(deltae1, bins=bins, label=r'$e_{1}$', alpha=0.2, normed=False)
    ax.hist(deltae2, bins=bins, label=r'$e_{2}$', alpha=0.1, normed=False)
    #ax.axvline(x=req, c='g', ls='--', label='Requirement')
    #ax.axvline(x=-req, c='g', ls='--')
    #ax.set_xlim(-6, 6)

    ax.set_xlabel(r'$e_{i}\ , \ \ \ i \in [1,2] \ \ \ \ [10^{-5}]$')
    ax.set_ylabel('Probability Density')

    plt.legend(shadow=True, fancybox=True)
    plt.savefig('hist2' + output)
    plt.close()

    #make scatter plots
    fig = plt.figure()
    ax = fig.add_subplot(111)
    plt.title(title)

    ax.plot(deltae, 'mD', label=r'$e$')
    ax.plot(deltae2, 'ys', label=r'$e_{2}$')
    ax.plot(deltae1, 'bo', label=r'$e_{1}$')
    #ax.fill_between(np.arange(len(deltae1)), np.ones(len(deltae1))*req, ymax, facecolor='red', alpha=0.08)
    #ax.fill_between(np.arange(len(deltae1)), -np.ones(len(deltae1))*req, -ymax, facecolor='red', alpha=0.08)

    #ax.set_ylim(0.0, 0.2)
    ax.set_xlabel('Number of Iterations')
    ax.set_ylabel(r'$e_{i}\ , \ \ \ i \in [1,2] \ \ \ \ [10^{-5}]$')

    #plt.text(0.5, 0.1,
    #         r'Average error in $e_{1}=$ %f and $e_{2}=$ %f' % (np.mean(deltae1), np.mean(deltae2)),
    #         ha='center',
    #         va='center',
    #         transform=ax.transAxes)

    plt.legend(shadow=True, fancybox=True, numpoints=1)#, ncol=2)
    plt.savefig(output)
    plt.close()


def plotNumberOfFramesDelta(results):
    """
    Creates a simple plot to combine and show the results for errors (delta).

    :param results: results to be plotted
    :type results: dict
    """
    txt = '%s' % datetime.datetime.isoformat(datetime.datetime.now())

    print '\nDelta results:'
    #loop over the number of bias frames combined
    for key in results:
        fig = plt.figure()
        ax = fig.add_subplot(111)

        if key == 1:
            plt.title(r'VIS Bias Calibration (%i exposure): $\delta e$' % key)
        else:
            plt.title(r'VIS Bias Calibration (%i exposures): $\delta e$' % key)

        de1 = np.asarray(results[key][0])
        de2 = np.asarray(results[key][1])
        de = np.asarray(results[key][2])

        avg1 = np.mean(de1)**2
        avg2 = np.mean(de2)**2
        avg = np.mean(de)**2

        #write down the values
        print key, avg, avg1, avg2
        plt.text(0.08, 0.9, r'$\left< \delta e_{1} \right>^{2} = %e$' %avg1, fontsize=10, transform=ax.transAxes)
        plt.text(0.08, 0.85, r'$\left< \delta e_{2}\right>^{2} = %e$' %avg2, fontsize=10, transform=ax.transAxes)
        plt.text(0.08, 0.8, r'$\left< \delta | \bar{e} |\right>^{2} = %e$' %avg, fontsize=10, transform=ax.transAxes)

        ax.hist(de, bins=10, color='y', alpha=0.2, label=r'$\delta | \bar{e} |$', normed=True)
        ax.hist(de1, bins=10, color='b', alpha=0.5, label=r'$\delta e_{1}$', normed=True)
        ax.hist(de2, bins=10, color='g', alpha=0.3, label=r'$\delta e_{2}$', normed=True)

        ax.axvline(x=0, ls=':', c='k')

        ax.set_ylabel('Probability Density')
        ax.set_xlabel(r'$\delta e_{i}\ , \ \ \ i \in [1,2]$')

        plt.text(0.83, 1.12, txt, ha='left', va='top', fontsize=9, transform=ax.transAxes, alpha=0.2)

        plt.legend(shadow=True, fancybox=True, numpoints=1, scatterpoints=1, markerscale=2.0, ncol=2)
        plt.savefig('BiasCalibrationEDelta%i.pdf' % key)
        plt.close()


    #same for R2s
    for key in results:
        fig = plt.figure()
        if key == 1:
            plt.title(r'VIS Bias Calibration (%i exposure): $\frac{\delta R^{2}}{R_{ref}^{2}}$' % key)
        else:
            plt.title(r'VIS Bias Calibration (%i exposures): $\frac{\delta R^{2}}{R_{ref}^{2}}$' % key)

        ax = fig.add_subplot(111)

        dR2 = np.asarray(results[key][3])
        avg = np.mean(dR2)**2

        ax.hist(dR2, bins=10, color='y', alpha=0.1, label=r'$\frac{\delta R^{2}}{R_{ref}^{2}}$', normed=True)

        print key, avg
        plt.text(0.1, 0.9, r'$\left<\frac{\delta R^{2}}{R^{2}_{ref}}\right>^{2} = %e$' %avg, fontsize=10, transform=ax.transAxes)

        ax.axvline(x=0, ls=':', c='k')

        ax.set_ylabel('Probability Density')
        ax.set_xlabel(r'$\delta \frac{\delta R^{2}}{R_{ref}^{2}}$')

        plt.text(0.83, 1.12, txt, ha='left', va='top', fontsize=9, transform=ax.transAxes, alpha=0.2)

        plt.legend(shadow=True, fancybox=True, numpoints=1, scatterpoints=1, markerscale=1.8)
        plt.savefig('BiasCalibrationDeltaSize%i.pdf' % key)
        plt.close()


def plotNumberOfFramesSigma(results, reqe=3e-5, reqr2=1e-4, shift=0.1):
    """
    Creates a simple plot to combine and show the results.

    :param results: results to be plotted
    :type results: dict
    :param req: the requirement
    :type req: float
    :param ymax: maximum value to show on the y-axis
    :type ymax: int or float
    :param shift: the amount to shift the e2 results on the abscissa (for clarity)
    :type shift: float
    """
    print '\nSigma results:'
    txt = '%s' % datetime.datetime.isoformat(datetime.datetime.now())

    fig = plt.figure()
    plt.title(r'VIS Bias Calibration: $\sigma (e)$')
    ax = fig.add_subplot(111)

    x = 1
    #loop over the number of bias frames combined
    for key in results:
        e1 = np.asarray(results[key][0])
        e2 = np.asarray(results[key][1])
        e = np.asarray(results[key][2])

        std1 = np.std(e1)
        std2 = np.std(e2)
        std = np.std(e)

        ax.scatter(key-shift, std, c='m', marker='*')
        ax.scatter(key, std1, c='b', marker='o')
        ax.scatter(key, std2, c='y', marker='s')

        x += 1

        print key, std, std1, std2


    ax.scatter(key-shift, std, c='m', marker='*', label=r'$\sigma (e)$')
    ax.scatter(key, std1, c='b', marker='o', label=r'$\sigma (e_{1})$')
    ax.scatter(key, std2, c='y', marker='s', label=r'$\sigma (e_{2})$')

    ax.fill_between(np.arange(x+1), np.ones(x+1)*reqe, 1.0, facecolor='red', alpha=0.08)
    ax.axhline(y=reqe, c='g', ls='--', label='Requirement')

    ax.set_yscale('log')
    ax.set_ylim(1e-8, 1e-4)
    ax.set_xlim(0, x)
    ax.set_xlabel('Number of Bias Frames Median Combined')
    ax.set_ylabel(r'$\sigma (e_{i})\ , \ \ \ i \in [1,2]$')

    plt.text(0.83, 1.12, txt, ha='left', va='top', fontsize=9, transform=ax.transAxes, alpha=0.2)

    plt.legend(shadow=True, fancybox=True, numpoints=1, scatterpoints=1, markerscale=2.0, ncol=2)
    plt.savefig('BiasCalibrationsigmaE.pdf')
    plt.close()

    #same for R2s
    R4 = 1.44264123086 ** 2

    fig = plt.figure()
    plt.title(r'VIS Bias Calibration: $\frac{\sigma (R^{2})}{R_{ref}^{2}}$')
    ax = fig.add_subplot(111)

    ax.axhline(y=0, c='k', ls=':')

    x = 1
    #loop over the number of bias frames combined
    for key in results:
        dR2 = np.asarray(results[key][4])

        std = np.std(dR2) / (5.06722858929**2) #/ R4
        #var = np.var(dR2) / (5.06722858929**4) #/ R4

        print key, std

        ax.scatter(key, std, c='m', marker='*', s=35, zorder=10)
        #ax.scatter(key, var, c='b', marker='s', s=35, zorder=10)

        x += 1

    #for the legend
    ax.scatter(key, std, c='m', marker='*', label=r'$\frac{\sigma(R^{2})}{R_{ref}^{2}}$')
    #ax.scatter(key, var, c='b', marker='s', label=r'$\frac{\sigma^{2}(R^{2})}{R_{ref}^{4}}$')

    #show the requirement
    ax.fill_between(np.arange(x+1), np.ones(x+1)*reqr2, 1.0, facecolor='red', alpha=0.08)
    ax.axhline(y=reqr2, c='g', ls='--', label='Requirement')

    ax.set_yscale('log')
    ax.set_ylim(1e-6, 1e-3)
    ax.set_xlim(0, x)
    ax.set_xlabel('Number of Bias Frames Median Combined')
    ax.set_ylabel(r'$\frac{\sigma (R^{2})}{R_{ref}^{2}}$')

    plt.text(0.83, 1.12, txt, ha='left', va='top', fontsize=9, transform=ax.transAxes, alpha=0.2)

    plt.legend(shadow=True, fancybox=True, numpoints=1, scatterpoints=1, markerscale=1.8    )
    plt.savefig('BiasCalibrationSigmaR2.pdf')
    plt.close()


def addReadoutNoise(data, readnoise=4.5, number=1):
    """
    Add readout noise to the input data. The readout noise is the median of the number of frames.

    :param data: input data to which the readout noise will be added to
    :type data: ndarray
    :param readnoise: standard deviation of the read out noise [electrons]
    :type readnoise: float
    :param number: number of read outs to median combine before adding to the data [default = 1]
    :type number: int

    :return: data + read out noise
    :rtype: ndarray [same as input data]
    """
    shape = data.shape
    biases = np.random.normal(loc=0.0, scale=math.sqrt(readnoise), size=(number, shape[0], shape[1]))
    if number > 1:
        bias = np.median(biases.astype(np.int), axis=0, overwrite_input=True)
    elif number < 1:
        print 'ERROR - number of bias frames to create cannot be less than 1'
    else:
        bias = biases[0].astype(np.int)
    return data + bias


if __name__ == '__main__':
    run = True

    #start the script
    log = lg.setUpLogger('biasCalibration.log')
    log.info('Testing bias level calibration...')

    if run:
        print '\nSigma run:'
        resultsSigma = testBiasCalibrationSigma(log, biases=15, psfs=500, surfaces=100, plots=False, file='psf1xhighe.fits')
        fileIO.cPickleDumpDictionary(resultsSigma, 'biasResultsSigma.pk')
        print '\nDelta run:'
        resultsDelta = testBiasCalibrationDelta(log, biases=2, psfs=500, surfaces=100, plots=False, file='psf1xhighe.fits')
        fileIO.cPickleDumpDictionary(resultsDelta, 'biasResultsDelta.pk')
    else:
        resultsDelta = cPickle.load(open('biasResultsDelta.pk'))
        resultsSigma = cPickle.load(open('biasResultsSigma.pk'))

    plotNumberOfFramesSigma(resultsSigma)
    plotNumberOfFramesDelta(resultsDelta)

    log.info('Run finished...\n\n\n')