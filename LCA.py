
"""Structure for estimating Well-to-Wheels Technology Warming Potential vs. time for a bioenergy scenario, considering:
- displacement of 1 MJ of gasoline with 1 MJ of pyrolysis-derived renewable gasoline
- one-time pulse emissions and emissions timeseries from

Structural notes:
* make use of libraries for tracking emissions from various sources
* how to differentiate initial pulse emissions from timeseries?  is there away to avoid filing out huge numbers of
  trailing zeros?
    perhaps never specify a set length; assume that you always start a the beginning (i.e., you may need to fill in
    leading zeros), and adjust the length of the time vector on the fly to match the emissions vector when making plots
    (probably best structured as a really simple function?)
* can species be added in the descriptor for each timeseries?
* separate libraries for the bioenergy case and the reference case??

"""

import csv
from math import exp
import matplotlib.pyplot as plt
import numpy as np


def LCA(ecosystem_Cflux_timeseries):
    # library structure: {variable: [name_string, color_map, [[species1, [timeseries1]], [species2, [timeseries2]]...]}
    # annual emissions fluxes of various species in grams per MJ of fuel created by the supply chain
    # color maps from http://matplotlib.org/examples/color/colormaps_reference.html
    # or http://matplotlib.org/1.2.1/_images/show_colormaps.png
    bioenergy_emissions = {'harvest': ['Feedstock harvest & transport', 'Blues',
                                       [['CO2', [4.83]]]],
                           'biorefinery': ['Biorefinery energy', 'BuPu',
                                           [['CO2', [13.5]]]],
                           'misc': ['Misc. inputs & factors', 'YlOrBr',
                                    [['CO2', [14.9]]]],
                           'ecosystem': ['Ecosystem carbon balance', 'BuGn',
                                         [['CO2', ecosystem_Cflux_timeseries]]]
                           }

    reference_emissions = {'extract': ['Oil extraction/transport/refining', 'Blues',
                                       [['CO2', [19.3]]]],
                           'tailpipe': ['Tailpipe emissions', 'YlOrBr',
                                        [['CO2', [68.5]]]]
                           }

    test_emissions = {'test': ['Test emissions', 'BuGn',
                               [['CO2', [1, 1.2, 1.4, 1.6, 1.8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2]]]]
                      }

    # format: [(a0, t0), (a1, t1)...] for c(t) = a0 * exp((-1.0*t)/t0) + a1 * exp((-1.0*t)/t1) + ...
    ghg_decay_params = {'CO2': [(0.217, 0),
                                (0.259, 172.9),
                                (0.338, 18.52),
                                (0.186, 1.186)],
                        }

    # format: (radiative forcing alpha term in W/m2*ppb, emission mass to atmospheric conversion constant in ppbv/Mg)
    ghg_forcing_params = {'CO2': (0.000014, 1.29E-7)
                          }


    def decay(species, initial, duration):
        param_sets = ghg_decay_params[species]
        amounts = []
        for year in range(duration):
            remaining = 0
            for param_set in param_sets:
                (a_i, t_i) = param_set
                if t_i:   # conditional to avoid divide by zero errors
                    remaining += initial * a_i * exp((-1.0*year)/t_i)
                else:
                    remaining += initial * a_i
            amounts.append(remaining)
        return amounts


    def gradient(figure_object, axis_object, xs, ys, start_year, TWP_length, cmap, key_count):
        """Based on http://matplotlib.org/examples/pylab_examples/multicolored_line.html
        and http://stackoverflow.com/questions/19132402/set-a-colormap-under-a-graph
        """
        from matplotlib.collections import LineCollection

        # plot a color_map line fading to white
        points = np.array([xs, ys]).T.reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)
        lc = LineCollection(segments, cmap=plt.get_cmap('gray'), norm=plt.Normalize(start_year, start_year+TWP_length),
                            linewidth=0.2, zorder=1)   # norm sets the color min:max range
        lc.set_array(np.array(xs))
        axis_object.add_collection(lc)

        # add fading color_map fill as well
        xs.append(max(xs))
        xs.append(min(xs))
        ys.append(0)
        ys.append(0)
        poly, = axis_object.fill(xs, ys, facecolor='none', edgecolor='none')
        img_data = np.arange(0, 100, 1)
        img_data = img_data.reshape(1, img_data.size)
        im = axis_object.imshow(img_data, aspect='auto', origin='lower', cmap=plt.get_cmap(cmap),
                                extent=[start_year+TWP_length, start_year, 1000, -1000], vmin=0., vmax=100., zorder=-(start_year+1)*key_count)
        im.set_clip_path(poly)
        # print start_year*key_count


    # main routine
    TWP_length = 300   # years
    years = range(1, TWP_length+1)
    fig, axes = plt.subplots(3, sharex=True)
    dictionaries = [bioenergy_emissions, reference_emissions]
    y_max = 100
    ymins = []
    ymaxes = []
    nets = []
    for e, dictionary in enumerate(dictionaries):
        # initialize cumulative radiative forcing arrays
        total_additions_timeseries = []
        total_subtractions_timeseries = []
        for x in range(TWP_length+1):
            total_additions_timeseries.append(0)
            total_subtractions_timeseries.append(0)

        # iterate through all source categories
        key_count = 0
        for key in dictionary.keys():
            key_count += 1
            source = dictionary[key][0]
            print "Evaluating forcing source ", source
            my_cmap = dictionary[key][1]
            color = plt.get_cmap(my_cmap)(0.7)
            axes[e].plot(0, 0, color=color, marker=None, label=source, linewidth=5)

            for emissions in dictionary[key][2]:
                species = emissions[0]
                alpha, mass_conc = ghg_forcing_params[species]
                flux_timeseries = emissions[1]

                # adjust flux_timeseries list length for consistency with TWP range
                if len(flux_timeseries) > TWP_length:
                    flux_timeseries = flux_timeseries[TWP_length:]
                elif len(flux_timeseries) < TWP_length:
                    for x in range(TWP_length-len(flux_timeseries)):
                        flux_timeseries.append(0)

                # iterate through flux_timeseries, compute out concentration vs. time and forcing vs. time for each flux,
                # add to plot, and add to total_forcing
                for i, flux in enumerate(flux_timeseries):   # this will always have length = TWP_length
                    if flux:   # don't go through the calculations if there is no flux
                        time = range(i, TWP_length)
                        flux_decay_timseries = np.array(decay(species, flux, TWP_length-i))
                        forcing_timeseries = flux_decay_timseries * mass_conc * alpha * (24*365) * 1E-6  # uWh/m2
                        plot_forcing_timeseries = []
                        for j, year in enumerate(time):
                            if flux > 0:
                                plot_forcing_timeseries.append(forcing_timeseries[j] + total_additions_timeseries[year])
                                total_additions_timeseries[year] += forcing_timeseries[j]
                            else:
                                plot_forcing_timeseries.append(forcing_timeseries[j] + total_subtractions_timeseries[year])
                                total_subtractions_timeseries[year] += forcing_timeseries[j]
                        gradient(fig, axes[e], time, plot_forcing_timeseries, i, TWP_length, my_cmap, key_count)

        total_additions_timeseries = np.array(total_additions_timeseries)
        total_subtractions_timeseries = np.array(total_subtractions_timeseries)
        net_forcing = total_additions_timeseries + total_subtractions_timeseries
        axes[e].plot(range(TWP_length), net_forcing[:-1], color='k', label='Net forcing', linewidth=3.0, zorder=1)
        ymins.append(min(total_subtractions_timeseries))
        ymaxes.append(max(total_additions_timeseries))
        nets.append(net_forcing)

    bioenergy_net = np.array(nets[0])
    reference_net = np.array(nets[1])
    TWP = bioenergy_net/reference_net
    axes[2].clear()
    axes[2].plot(range(TWP_length), TWP[:-1], color='k', linewidth=3.0, zorder=2)

    axes[0].set_title('Forcing- biomass harvest, biofuel production & use')
    axes[0].set_ylim(min(ymins), max(ymaxes))
    axes[0].set_ylabel('uWh/MJ')
    l = axes[0].legend(loc=1, prop={'size': 7})
    l.set_zorder(3)
    axes[0].plot([0, TWP_length-1], [0, 0], marker=None, linestyle='--', color='k', linewidth=2.0, zorder=2)

    axes[1].set_title('Forcing- reference gasoline production & use')
    axes[1].set_ylim(min(ymins), max(ymaxes))
    axes[1].set_ylabel('uWh/MJ')
    l = axes[1].legend(loc=1, prop={'size': 7})
    l.set_zorder(3)
    axes[1].plot([0, TWP_length-1], [0, 0], marker=None, linestyle='--', color='k', linewidth=2.0, zorder=2)

    axes[2].set_title('Technology Warming Potential')
    axes[2].set_xlim(0, TWP_length)
    axes[2].set_ylabel('ratio')
    axes[2].set_xlabel('Time elapsed after stand harvest, fuel production & use')
    axes[2].plot([0, TWP_length-1], [1, 1], marker=None, linestyle='--', color='k', linewidth=2.0, zorder=2)
    axes[2].grid()

    plt.savefig('TWP.png', dpi=300)


lines = csv.reader(open('fluxes.csv', 'rU'))
fluxes = []
for line in lines:
    fluxes.append(float(line[0]))
print fluxes
LCA(fluxes)
# LCA([100, 5, 15, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -40, 20, -15, 0, 0, 0, 0])