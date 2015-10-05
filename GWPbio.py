
def bern(t):

    from math import exp

    # BERN CO2 decay model parameters
    a0 = 0.217
    a1 = 0.259
    a2 = 0.338
    a3 = 0.186

    t1 = 172.9
    t2 = 18.52
    t3 = 1.186

    f = a0 + a1 * exp((-1.0*t)/t1) + a2 * exp((-1.0*t)/t2) + a3 * exp((-1.0*t)/t3)

    return f


def GWPbio(fluxes, basis, start_year=0, flux_plot_name='', cumulative_plot_name=''):

    import numpy as np
    import matplotlib.pyplot as plt

    light_blue = (0/255.0, 205/255.0, 255/255.0)
    dark_blue = (0/255.0, 58/255.0, 73/255.0)

    alpha_co2 = 0.000014   # W/m2*ppb
    mass_c_conv_co2 = 1.29E-7   # ppbv/Mg

    # initialize a CO2 amount timeseries array
    co2s = []   # MgCO2
    for i in range(basis+len(fluxes)):
        co2s.append(0)
    if flux_plot_name:
        plt.bar(range(start_year, start_year+len(fluxes)), fluxes, color=light_blue, linewidth=0.0)
        plt.xlabel("Year")
        plt.ylabel("Annual carbon dioxide fluxes (MgCO2) and attenuation")

    # iterate through flux timeseries, and add BERN-corrected CO2 totals to appropriate elements of CO2 array
    for i, flux in enumerate(fluxes):
        t_elapsed = 0
        time = []
        trace = []
        for j in range(i, basis+len(fluxes)):   # alternately, range(i, i+basis)
            current_co2 = flux * bern(t_elapsed)
            co2s[j] += current_co2
            time.append(start_year+j)
            trace.append(current_co2)
            t_elapsed += 1
        if flux_plot_name:
            plt.plot(time, trace, color=dark_blue, linewidth=0.2)
    if flux_plot_name:
        plt.savefig(flux_plot_name)
        plt.close()

    # cumulative co2 plots
    if cumulative_plot_name:
        plot_fluxes = []
        for i in range(basis+len(fluxes)):
            try:
                plot_fluxes.append(fluxes[i])
            except:
                plot_fluxes.append(0)
        plt.plot(range(start_year, start_year+len(plot_fluxes)), np.cumsum(plot_fluxes), label='No attenuation')
        plt.plot(range(start_year, start_year+len(co2s)), co2s, label='Attenuated based on BERN model')
        plt.legend(prop={'size': 12})
        plt.xlabel("Year")
        plt.ylabel("Cumulative carbon dioxide addition (MgCO2)")
        plt.savefig(cumulative_plot_name)
        plt.close()
    # translate CO2 amount timeseries to a radiative forcing timeseries
    forcings = []
    for i, co2 in enumerate(co2s):
        forcing = co2 * mass_c_conv_co2 * alpha_co2 * (24*365)   # Wh/m2
        forcings.append(forcing)
    cumulative_forcing = np.sum(np.array(forcings))

    return cumulative_forcing   # Wh/m2


# fluxes = [0, 10, 12, 8, 6, 2, -1, -4, -3]   # MgCO2/y
# GWPbio(fluxes, 100, flux_plot_name='flux_test.png', cumulative_plot_name='cumulative_test.png')