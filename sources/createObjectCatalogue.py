"""
Generating Object Catalogue
===========================

These simple functions can be used to generate different types of object catalogues that can then be used
as an input for the VIS simulator.

Please note that the script requires files from the data folder. Thus, you should
place the script to an empty directory and either copy or link to the data directory.

:requires: NumPy
:requires: SciPy
:requires: matplotlib

:author: Sami-Matias Niemi
:contact: s.niemi@ucl.ac.uk
"""
import numpy as np
import scipy.interpolate as interpolate
import matplotlib.pyplot as plt


def drawFromCumulativeDistributionFunction(cpdf, x, number):
    """
    Draw a number of random x values from a cumulative distribution function.

    :param cpdf: cumulative distribution function
    :type cpdf: numpy array
    :param x: values of the abscissa
    :type x: numpy array
    :param number: number of draws
    :type number: int

    :return: randomly drawn x value
    :rtype: ndarray
    """
    luck = np.random.random(number)
    tck = interpolate.splrep(cpdf, x)
    out = interpolate.splev(luck, tck)
    return out


def plotDistributionFunction(datax, datay, fitx, fity, output):
    """
    Generates a simple plot showing the observed data points and the fit
    that was generated based on these data.
    """
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.semilogy(datax, datay, 'bo', label='Data')
    ax.semilogy(fitx, fity, 'r-', label='Fit')
    ax.set_xlabel('R+I Magnitude')
    ax.set_ylabel('Cumulative Number Density [sq degree]')
    plt.legend(fancybox=True, shadow=True, numpoints=1, loc=2)
    plt.savefig(output)


def plotCatalog(catalog):
    """
    Plot the number of objects in the generated catalog. Will generate both cumulative and normal
    distributions for galaxies and stars separately.

    :param catalog: name of the catalogue file
    :type catalog: str

    :return: None
    """
    data = np.loadtxt(catalog)
    mag = data[:, 2]
    type = data[:, 3]
    stars = type < 1

    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.hist(mag[~stars], bins=20, label='Galaxies', alpha=0.3)
    ax.hist(mag[stars], bins=20, label='Stars', alpha=0.5)
    ax.semilogy()
    ax.set_xlabel('R+I Magnitude')
    ax.set_ylabel('# objects')
    plt.legend(fancybox=True, shadow=True, numpoints=1, loc=2)
    plt.savefig(catalog + 'counts.pdf')
    plt.close()

    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.hist(mag[~stars], bins=20, label='Galaxies', cumulative=True, alpha=0.3)
    ax.hist(mag[stars], bins=20, label='Stars', cumulative=True, alpha=0.5)
    ax.semilogy()
    ax.set_xlabel('R+I Magnitude')
    ax.set_ylabel('# objects')
    plt.legend(fancybox=True, shadow=True, numpoints=1, loc=2)
    plt.savefig(catalog + 'countsCum.pdf')
    plt.close()


def generateCatalog(**kwargs):
    """
    Generate a catalogue of stars and galaxies that follow
    realistic number density functions.

    :param deg: galactic latitude, either 30, 60, 90
    """
    settings = dict(ncatalogs=1, outputprefix='catalog', besancon=True,
                    nx=4096, ny=4132, sqdeg=1.0, fov=1.0, fudge=40.0,
                    galaxies='data/cdf_galaxies.dat',
                    types=np.asarray([8, 9, 10, 11, 12, 13, 14, 15]),
                    deg=30)

    settings.update(kwargs)

    #cumulative distribution of galaxies
    d = np.loadtxt(settings['galaxies'], usecols=(0, 1))
    gmags = d[:, 0]
    gcounts = d[:, 1]
    #nums = int(np.max(gcounts) / 3600. * settings['fudge'] * settings['fov'])  #3600=from sq deg to sq arcsec
    nums = int(np.max(gcounts) / 3600. / 3600. * settings['nx'] * settings['ny'] / 10. / 10.)

    z = np.polyfit(gmags, np.log10(gcounts), 4)
    p = np.poly1d(z)
    galaxymags = np.arange(10.0, 30.2, 0.2)
    galaxycounts = 10**p(galaxymags)
    plotDistributionFunction(gmags, gcounts, galaxymags, galaxycounts, settings['outputprefix'] + 'GalaxyDist.pdf')
    cumulative = (galaxycounts - np.min(galaxycounts))/ (np.max(galaxycounts) - np.min(galaxycounts))

    #stars
    if settings['besancon']:
        print 'Using Besancon model for stars'
        bs = np.loadtxt('data/besancon.dat', usecols=(0, 1))
        bsdist = bs[:, 0]
        bsmag = bs[:, 1]
        bsmag += 5. * np.log10(bsdist/0.01)

        #number of stars to include
        nstars = int(len(bsmag) * 5. * settings['nx'] * settings['ny'] / 600**2 / (3600. * settings['sqdeg']))
    else:
        #cumulative distribution of stars
        if settings['deg'] == 30:
            print 'Selecting stars for 30deg'
            tmp = 1
            sfudge = 0.79
        elif settings['deg'] == 60:
            print 'Selecting stars for 60deg'
            tmp = 2
            sfudge = 0.79
        else:
            print 'Selecting stars for 90deg'
            tmp = 3
            sfudge = 0.78

        #read in data
        d = np.loadtxt('data/stars.dat', usecols=(0, tmp))
        stmags = d[:, 0]
        stcounts = d[:, 1]

        #fit a function and generate finer sample
        z = np.polyfit(stmags, np.log10(stcounts), 4)
        p = np.poly1d(z)
        starmags = np.arange(1, 30.2, 0.2)
        starcounts = 10**p(starmags)
        plotDistributionFunction(stmags, stcounts, starmags, starcounts, settings['outputprefix'] + 'StarDist.pdf')

        cpdf = (starcounts - np.min(starcounts))/ (np.max(starcounts) - np.min(starcounts))
        starcounts /=  3600. #convert to square arcseconds
        nstars = int(np.max(starcounts) * settings['fudge'] * sfudge * settings['fov'] *
                     settings['nx'] * settings['ny'] / 4096. / 4132.)

    print '%i stars and %i galaxies' % (nstars, nums)

    for n in range(settings['ncatalogs']):
        #open output
        fh = open(settings['outputprefix'] + str(n) + '.dat', 'w')
        #write SExtractor type header
        fh.write('#   1 X                Object position along x                                    [pixel]\n')
        fh.write('#   2 Y                Object position along y                                    [pixel]\n')
        fh.write('#   3 MAG              Object magnitude                                           [AB]\n')
        fh.write('#   4 TYPE             Object type                                                [0=star, others=FITS]\n')
        fh.write('#   5 ORIENTATION      Objects orientation                                        [deg]\n')

        #find random positions for stars
        if nstars > 0:
            x = np.random.random(nstars) * settings['nx']
            y = np.random.random(nstars) * settings['ny']

            if settings['besancon']:
                luck = np.random.random(len(bsmag))
                mag = bsmag[np.argsort(luck)]
            else:
                mag = drawFromCumulativeDistributionFunction(cpdf, starmags, nstars)

            for a, b, c in zip(x, y, mag):
                fh.write('%f %f %f 0 0.00000\n' % (a, b, c))

        #find random positions, rotation, and type for galaxies
        xc = np.random.random(nums) * settings['nx']
        yc = np.random.random(nums) * settings['ny']
        theta = np.random.random(nums) * 360.0
        typ = np.random.random_integers(low=np.min(settings['types']), high=np.max(settings['types']), size=nums)
        mag = drawFromCumulativeDistributionFunction(cumulative, galaxymags, nums)

        #write out galaxies
        for x, y, m, t, ang in zip(xc, yc, mag, typ, theta):
            fh.write('%f %f %f %i %f \n' % (x, y, m, t, ang))

        fh.close()


def starCatalog(stars=400, xmax=2048, ymax=2066, magmin=23, magmax=26):
    """
    Generate a catalog with stars at random positions.
    """
    xcoords = np.random.random(stars) * xmax
    ycoords = np.random.random(stars) * ymax
    mags = np.linspace(magmin, magmax, stars)

    fh = open('starsFaint.dat', 'w')
    fh.write('#   1 X                Object position along x                                    [pixel]\n')
    fh.write('#   2 Y                Object position along y                                    [pixel]\n')
    fh.write('#   3 MAG              Object magnitude                                           [AB]\n')
    fh.write('#   4 TYPE             Object type                                                [0=star, others=FITS]\n')
    fh.write('#   5 ORIENTATION      Objects orientation                                        [deg]\n')

    for x, y, m in zip(xcoords, ycoords, mags):
        fh.write('%f %f %f %i %f \n' % (x, y, m, 0, 0.0))
    fh.close()


def starCatalogFixedMagnitude(stars=400, xmax=2048, ymax=2066, mag=18, random=True, pergrid=51, out='starsSameMag.dat'):
    """
    Generate a catalog with stars of a given magnitude either at random positions or in a rectangular grid.
    """
    fh = open(out, 'w')
    fh.write('#   1 X                Object position along x                                    [pixel]\n')
    fh.write('#   2 Y                Object position along y                                    [pixel]\n')
    fh.write('#   3 MAG              Object magnitude                                           [AB]\n')
    fh.write('#   4 TYPE             Object type                                                [0=star, others=FITS]\n')
    fh.write('#   5 ORIENTATION      Objects orientation                                        [deg]\n')

    if random:
        #random positions
        xcoords = np.random.random(stars) * xmax
        ycoords = np.random.random(stars) * ymax

        for x, y in zip(xcoords, ycoords):
            fh.write('%f %f %f %i %f \n' % (x, y, mag, 0, 0.0))
    else:
        #grid
        xcoords = np.linspace(30, xmax-30, pergrid)
        ycoords = np.linspace(30, ymax-30, pergrid)
        for x in xcoords:
            for y in ycoords:
                fh.write('%f %f %f %i %f \n' % (x, y, mag, 0, 0.0))

    fh.close()


if __name__ == '__main__':
    #settings = dict(besancon=False, deg=30)
    #generateCatalog(**settings)

    #full FoV
    #settings = dict(besancon=False, deg=30, nx=60000, ny=60000, outputprefix='fullFoV',
    #                types=np.arange(17, 103))
    #generateCatalog(**settings)
    #plotCatalog('fullFoV0.dat')

    #single CCD (but extra so that ghosts can be simulated to CCD=1,1)
    settings = dict(besancon=False, deg=30, nx=10000, ny=10000, outputprefix='CCDcatalogue',
                    types=np.arange(17, 103))
    generateCatalog(**settings)

    #create 100 catalogs at deg=30
    #settings = dict(besancon=False, deg=30, ncatalogs=500)
    #generateCatalog(**settings)

    #starCatalog(stars=100)
    #starCatalog(stars=500)
    #starCatalogFixedMagnitude(mag=24.5, random=False, out='stars24.5.dat')