""" This module develops a simple conceptual model for exploring forest carbon storage dynamics
considering stand growth and response to stochastic fire, insect, and harvest disturbances.

"""


import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
from random import *


print """
*************************************************************************************************
 This interactive routine presents a simple conceptual model exploring the dynamics of forest
 carbon storage considering:
    * generalized stand dynamics using select equations from the Physiological Principles
      in Predicting Growth (3-PG) model
    * disturbance due to beetle infestation, regenerative harvest, or wildfire
 at the level of either individual even-aged stands or entire landscapes
*************************************************************************************************
"""

# define default values for all model parameters in structure [float(value), str(units), str(description)]
params = {'age_max': [150, 'years', 'estimated maximum stand age'],
          'n_age': [4, '-', 'hydraulic conductivity age modifier exponent'],
          'phi_s': [5.5, 'kWh/m2/day', 'annually-averaged incoming short-wave radiation'],   # Denver http://www.apricus.com/upload/userfiles/images/Insolation-levels-USA.jpg
          'f_DT': [0.5, '-', 'annually-averaged temperature/moisture modifier value'],
          'sigma_f': [3.2, 'm2/kg', 'specific leaf area'],   # Chen et al. CJFR 1996 Fig. 3c
          'beers_k': [0.4, '-', 'Beers Law light extinction coefficient'],   # Binkley et al. FEM 2013 Fig. 4c; POOR MODEL FOR LODGEPOLE!
          'microbial_efficiency': [0.25, '-', 'Fraction of C entering soil that gets stabilized']
          }


def beers_law_scalar(beers_k, LAI):
    return np.exp(-1 * beers_k * LAI)   # http://www2.geog.ucl.ac.uk/~mdisney/teaching/GEOGG121/diff/prac/


def age_modifier(age, age_max, n_age):
    relative_age = float(age)/age_max
    return 1.0 / (1 + (relative_age/0.95)**n_age)   # Landsberg & Waring 1997 Eq. 3


def three_PG(age, params, states):
    # read parameter values
    age_max = params['age_max'][0]
    n_age = params['n_age'][0]
    phi_s = params['phi_s'][0]
    f_DT = params['f_DT'][0]
    sigma_f = params['sigma_f'][0]
    beers_k = params['beers_k'][0]
    microbial_efficiency = params['microbial_efficiency'][0]

    # read most current values of state variables
    w_f = states['w_f'][-1]
    w_s = states['w_s'][-1]
    w_r = states['w_r'][-1]
    w_l = states['w_l'][-1]
    w_c = states['w_c'][-1]
    w_o = states['w_o'][-1]

    # calculate LAI, canopy light interception fraction
    sigma_f_conv = 0.1 * sigma_f   # specific leaf area conversion to ha/Mg
    LAI = w_f * sigma_f_conv   # leaf area index, m2/m2
    intercept_fraction = 1 - beers_law_scalar(beers_k, LAI)

    # calculate average annual insolation, age modifier, and annual total biomass increment
    phi_s_conv = phi_s * 3.6   # average short-wave insolation conversion to MJ/m2/day
    phi_p = phi_s_conv * 0.5   # photosynthetically-active radiation is 45% of total shortwave
    phi_pa = phi_p * intercept_fraction   # absorbed PAR
    alpha_c = 1.8   # universal canopy quantum efficiency coefficient, gC/MJ
    f_age = age_modifier(age, age_max, n_age)
    avg_daily_C_increment = phi_pa * alpha_c * f_DT * f_age   # gC/m2/day
    net_daily_C = avg_daily_C_increment * 0.45
    # c_concentration = 0.45
    annual_c_increment = net_daily_C * 365 * 0.01  # Mg/ha/y

    # calculate all turnover & transfer quantities
    # ToDo: update litterfall routine with attenuation for young stands
    litterfall = w_f * 0.20
    litter_time_constant = 2   # years
    litter_k = (-1 * np.log(0.5)) / litter_time_constant
    litter_turnover = w_l * (1 - np.exp(-1 * litter_k))
    branchfall = w_s * 0.10
    coarse_fuel_time_constant = 20   # years
    coarse_k = (-1 * np.log(0.5)) / coarse_fuel_time_constant
    coarse_turnover = w_c * (1 - np.exp(-1 * coarse_k))
    som_time_constant = 10   # years
    som_k = (-1 * np.log(0.5)) / som_time_constant
    som_turnover = w_o * (1 - np.exp(-1 * som_k))
    root_turnover = 0.25 * w_r

    # implement mass balance for all carbon pools
    # ToDo: update this with actual allometric equations
    w_f += (0.33 * annual_c_increment) - litterfall
    w_s += (0.33 * annual_c_increment) - branchfall   # - (0.25 * w_s)
    w_r += 0.33 * annual_c_increment - root_turnover
    w_l += litterfall + (0.9 * branchfall) - litter_turnover
    w_c += (0.1 * branchfall) - coarse_turnover
    w_o += ((root_turnover + litter_turnover + coarse_turnover) * microbial_efficiency) - som_turnover

    # update state variable time series
    states['age'].append(age)
    states['w_f'].append(w_f)
    states['w_s'].append(w_s)
    states['w_r'].append(w_r)
    states['w_l'].append(w_l)
    states['w_c'].append(w_c)
    states['w_o'].append(w_o)
    states['LAI'].append(LAI)
    states['interception'].append(intercept_fraction)


def c_plot(plot_object, w_c_array, w_l_array, w_s_array, w_f_array, w_r_array, w_o_array, time_vector, y_label):
        w_c_plot = w_c_array
        w_l_plot = w_c_plot + w_l_array
        w_s_plot = w_l_plot + w_s_array
        w_f_plot = w_s_plot + w_f_array
        w_r_plot = 0 - w_r_array
        w_o_plot = w_r_plot - w_o_array

        plot_object.bar(time_vector, w_f_plot, label='Foliage', color='g', edgecolor='g')
        plot_object.bar(time_vector, w_s_plot, label='Stems', color='y', edgecolor='y')
        plot_object.bar(time_vector, w_l_plot, label='Litter', color='k', edgecolor='k')
        plot_object.bar(time_vector, w_c_plot, label='Coarse', color='r', edgecolor='r')
        plot_object.bar(time_vector, w_o_plot, label='SOM', color='m', edgecolor='m')
        plot_object.bar(time_vector, w_r_plot, label='Roots', color='b', edgecolor='b')
        plot_object.legend(loc=9, bbox_to_anchor=(1.0, 1.0), prop={'size': 10})


def unharvested_infestation(param_dictionary, state_dictionary):
    """All foliage transferred to litter, all stems transferred to coarse fuels,
    roots transferred to SOM after microbial efficiency adjustment,
    'LAI' and 'interception' are independently calculated at every time step, so arbitrarily set to zero here
    """
    microbial_efficiency = param_dictionary['microbial_efficiency'][0]
    state_dictionary['age'].append(0)
    state_dictionary['w_f'].append(0.1)
    state_dictionary['w_s'].append(0.1)
    state_dictionary['w_r'].append(0.1)
    state_dictionary['w_l'].append(state_dictionary['w_l'][-1] + state_dictionary['w_f'][-2])
    state_dictionary['w_c'].append(state_dictionary['w_c'][-1] + state_dictionary['w_s'][-2])
    state_dictionary['w_o'].append(state_dictionary['w_o'][-1] + (state_dictionary['w_r'][-2] * microbial_efficiency))
    state_dictionary['LAI'].append(0)
    state_dictionary['interception'].append(0)


def harvested_infestation(param_dictionary, state_dictionary):
    """All foliage transferred to litter, all stems removed for harvest,
    roots transferred to SOM after microbial efficiency adjustment,
    'LAI' and 'interception' are independently calculated at every time step, so arbitrarily set to zero here
    """
    microbial_efficiency = param_dictionary['microbial_efficiency'][0]
    state_dictionary['age'].append(0)
    state_dictionary['w_f'].append(0.1)
    state_dictionary['w_s'].append(0.1)
    state_dictionary['w_r'].append(0.1)
    state_dictionary['w_l'].append(state_dictionary['w_l'][-1] + state_dictionary['w_f'][-2])
    state_dictionary['w_c'].append(state_dictionary['w_c'][-1])
    state_dictionary['w_o'].append(state_dictionary['w_o'][-1] + (state_dictionary['w_r'][-2] * microbial_efficiency))
    state_dictionary['LAI'].append(0)
    state_dictionary['interception'].append(0)
    return state_dictionary['w_s'][-2]


def fire(param_dictionary, state_dictionary):
    """All aboveground live, litter, coarse disappear, roots transferred to SOM after microbial efficiency adjustment
    'LAI' and 'interception' are independently calculated at every time step, so arbitrarily set to zero here
    """
    microbial_efficiency = param_dictionary['microbial_efficiency'][0]
    state_dictionary['age'].append(0)
    state_dictionary['w_f'].append(0.1)
    state_dictionary['w_s'].append(0.1)
    state_dictionary['w_r'].append(0.1)
    state_dictionary['w_l'].append(0.1)
    state_dictionary['w_c'].append(0.1)
    state_dictionary['w_o'].append(state_dictionary['w_o'][-1] + (state_dictionary['w_r'][-2] * microbial_efficiency))
    state_dictionary['LAI'].append(0)
    state_dictionary['interception'].append(0)


def land(iteration, tot_iterations, detail=False):
    # time parameters
    runs = 1000
    start_year = 1915
    simulation_length = 200
    simulation_years = range(start_year, start_year+simulation_length)
    plot_years = range(start_year, start_year+simulation_length+1)
    fire_frequency = 200   # years to a stand-replacing fire
    infest_start = 2005
    infest_end = 2015

    # defining plot structure
    if detail:
        gs = gridspec.GridSpec(13, 1)
        ax1 = plt.subplot(gs[0, :])
        plt.axvspan(infest_start, infest_end, color='r', alpha=0.5, lw=0)
        ax1.set_title("No harvest")
        ax2 = plt.subplot(gs[1:4, :])
        plt.axvspan(infest_start, infest_end, color='r', alpha=0.5, lw=0)
        ax3 = plt.subplot(gs[5, :])
        plt.axvspan(infest_start, infest_end, color='r', alpha=0.5, lw=0)
        ax3.set_title("Post-infestation harvest")
        ax4 = plt.subplot(gs[6:9, :])
        plt.axvspan(infest_start, infest_end, color='r', alpha=0.5, lw=0)
        ax5 = plt.subplot(gs[10:, :])
        plt.axvspan(infest_start, infest_end, color='r', alpha=0.5, lw=0)
        ax5.set_title("Difference")
        axis_objs = [[ax1, ax2], [ax3, ax4]]

    # define loops for simulating unharvested and harvested beetle infestation
    descrip = ['unharvested scenario', 'harvest scenario']
    landscape_totals = []
    max_fire_freq = []
    print
    print 'Executing simulations for analysis iteration %i/%i - ' % (iteration, tot_iterations)
    for i in (0, 1):
        # initialize lists for total landscape carbon fractions
        total_w_f = [0]
        total_w_s = [0]
        total_w_r = [0]
        total_w_l = [0]
        total_w_c = [0]
        total_w_o = [0]
        fires = [0]
        infestations = [0]
        harvests = [0]
        for k in range(simulation_length):
            total_w_f.append(0)
            total_w_s.append(0)
            total_w_r.append(0)
            total_w_l.append(0)
            total_w_c.append(0)
            total_w_o.append(0)
            fires.append(0)
            infestations.append(0)
            harvests.append(0)

        # for each specified stand run, create & initialize a new state variable dictionary, and run through simulation
        # years computing 3-PG model steps and adding stochastic fire, beetle, and/or harvest events where appropriate
        for run in range(runs):
            print '\r   Step %i/2: simulating %s for stand %i/%i' % (i+1, descrip[i], run+1, runs),
            # make a new initialized state variable dictionary
            local_states = {'age': [states['age'][0]],
                            'w_f': [states['w_f'][0]],
                            'w_s': [states['w_s'][0]],
                            'w_r': [states['w_r'][0]],
                            'w_l': [states['w_l'][0]],
                            'w_c': [states['w_c'][0]],
                            'w_o': [states['w_o'][0]],
                            'LAI': [states['LAI'][0]],
                            'interception': [states['interception'][0]]
                            }
            # define stand starting age and stochstic variables
            age = 0
            infest_risk = 0.8 / (infest_end - infest_start)
            infested = False
            j = 0
            for year in simulation_years:
                # implement infestation where appropriate.  No growth or fire occur in infestation years
                rand = random()
                # ToDo: include a limit on minimum stand size/age for beetle infestation
                if not infested and (infest_start <= year <= infest_end) and (rand <= infest_risk):
                    age = 0
                    if i == 0:
                        unharvested_infestation(params, local_states)
                    elif i == 1:
                        harvest = harvested_infestation(params, local_states)
                        harvests[j] -= harvest
                    infestations[j] += 1
                else:
                    # if no infestation, proceed normally with stochastic fire events or 3-PG growth step
                    fire_risk = (1.0/fire_frequency) * (((local_states['w_l'][-1] * 0.1) + local_states['w_c'][-1])/20)
                    rand = random()
                    if rand <= fire_risk:
                        age = 0
                        fire(params, local_states)
                        fires[j] += 1
                    else:
                        three_PG(age, params, local_states)
                    age += 1
                j += 1
            total_w_f += np.array(local_states['w_f'])
            total_w_s += np.array(local_states['w_s'])
            total_w_r += np.array(local_states['w_r'])
            total_w_l += np.array(local_states['w_l'])
            total_w_c += np.array(local_states['w_c'])
            total_w_o += np.array(local_states['w_o'])

        if detail:
            axis_objs[i][0].bar(plot_years, fires)
            max_fire_freq.append(max(fires))
            axis_objs[i][0].set_xlim((simulation_years[0], simulation_years[-1]))
            axis_objs[i][0].set_xticklabels([])
            axis_objs[i][0].yaxis.tick_right()
            axis_objs[i][0].set_ylabel("Fires\n\n")

            c_plot(axis_objs[i][1], total_w_c, total_w_l, total_w_s, total_w_f, total_w_r, total_w_o, plot_years, "")
            axis_objs[i][1].set_xlim((simulation_years[0], simulation_years[-1]))
            axis_objs[i][1].set_xticklabels([])
            axis_objs[i][1].set_ylabel("Landscape MgC")

        landscape_total = total_w_f + total_w_s + total_w_r + total_w_l + total_w_c + total_w_o
        landscape_totals.append(landscape_total)
        print

    difference = landscape_totals[1] - landscape_totals[0]
    if detail:
        ax5.plot(plot_years, difference, color='r', linewidth=2.0, label='System C deficit')
        ax5.plot(plot_years, np.cumsum(harvests), color='b', linewidth=2.0, label='Cumulative C removed')
        ax5.legend(loc=3, prop={'size': 11})
        ax5.plot((simulation_years[0], simulation_years[-1]), (0, 0), color='k')
        ax5.set_ylabel("Landscape MgC")
        ax5.set_xlim((simulation_years[0], simulation_years[-1]))
        ax1.yaxis.set_ticks([0, max(max_fire_freq)])
        ax3.yaxis.set_ticks([0, max(max_fire_freq)])

    return plot_years, difference, np.cumsum(harvests)


# main control loop
while True:
    # define state variable time series initial values
    states = {'age': [0],   # stand age since last disturbance
              'w_f': [0.1],   # foliage weight, Mg/ha
              'w_s': [0.1],   # stem weight, Mg/ha
              'w_r': [0.1],   # root weight, Mg/ha
              'w_l': [0.1],   # litter weight, Mg/ha
              'w_c': [0.1],   # coarse surface fuels weight, Mg/ha
              'w_o': [40],   # soil organic matter weight, Mg/ha
              'LAI': [0],   # for display only
              'interception': [0]   # for display only
              }
    print
    print "Current model parameters:"
    for key in params.keys():
        print "   %s = %.3f (%s)  %s" % (key, params[key][0], params[key][1], params[key][2])
    print
    print "Default initial values:"
    for key in states.keys():
        print "   %s = %.3f" % (key, states[key][0])
    print
    print "************************************************************************************************************"
    command = raw_input("""Please enter the name of the parameter or initial state value to update,
'stand' to run a stand-level simulation showing long-term growth trajectory and response to disturbance,
'land' to run a single stochastic landscape-level analysis showing ecosystem response to beetle attack
     under harvested and unharvested management,
'uncert' to run a set of stochastic landscape analyses in order to bound uncertainty in ecosystem response, or
'q' to quit:\n   """)
    print

    if command in params.keys():
        value = raw_input("Please specify a new value for this parameter: ")
        params[command][0] = float(value)

    elif command in states.keys():
        value = raw_input("Please specify a new initial value for this state variable: ")
        params[command][0] = float(value)

    elif command == 'stand':
        # step through a sequence of simulation years and apply the 3-PG growth model each year
        simulation_length = 120
        simulation_years = range(0, simulation_length)
        plot_years = range(0, simulation_length+1)
        age = 0
        local_states = {'age': [states['age'][0]],
                        'w_f': [states['w_f'][0]],
                        'w_s': [states['w_s'][0]],
                        'w_r': [states['w_r'][0]],
                        'w_l': [states['w_l'][0]],
                        'w_c': [states['w_c'][0]],
                        'w_o': [states['w_o'][0]],
                        'LAI': [states['LAI'][0]],
                        'interception': [states['interception'][0]]
                        }
        for year in simulation_years:
            three_PG(age, params, local_states)
            age += 1
        # plot results
        plt.subplot(4, 1, 1)
        plt.plot(plot_years, local_states['LAI'])
        plt.ylabel("LAI\n(m2/m2)")
        plt.xlim((0, simulation_length))
        plt.subplot(4, 1, 2)
        plt.plot(plot_years, local_states['interception'])
        plt.ylabel("Light\ninterception")
        plt.xlim((0, simulation_length))
        plt.subplot(4, 1, 3)
        w_s = np.array(local_states['w_s'])
        w_f = np.array(local_states['w_f'])
        w_r = np.array(local_states['w_r'])
        w_l = np.array(local_states['w_l'])
        w_c = np.array(local_states['w_c'])
        w_o = np.array(local_states['w_o'])
        c_plot(plt, w_c, w_l, w_s, w_f, w_r, w_o, plot_years, "C pools\n(MgC/ha)")
        plt.ylabel("Ecosystem C pools\n(MgC/ha)")
        plt.xlabel("Time (years)")
        plt.xlim((0, simulation_length))
        plt.legend(prop={'size': 11})
        # do another set of simulations with disturbance included this time
        age = 0
        local_states = {'age': [states['age'][0]],
                        'w_f': [states['w_f'][0]],
                        'w_s': [states['w_s'][0]],
                        'w_r': [states['w_r'][0]],
                        'w_l': [states['w_l'][0]],
                        'w_c': [states['w_c'][0]],
                        'w_o': [states['w_o'][0]],
                        'LAI': [states['LAI'][0]],
                        'interception': [states['interception'][0]]
                        }
        for year in simulation_years:
            if year == 40:
                age = 0
                fire(params, local_states)
            elif year == 80:
                age = 0
                unharvested_infestation(params, local_states)
            else:
                three_PG(age, params, local_states)
            age += 1
        plt.subplot(4, 1, 4)
        w_s = np.array(local_states['w_s'])
        w_f = np.array(local_states['w_f'])
        w_r = np.array(local_states['w_r'])
        w_l = np.array(local_states['w_l'])
        w_c = np.array(local_states['w_c'])
        w_o = np.array(local_states['w_o'])
        c_plot(plt, w_c, w_l, w_s, w_f, w_r, w_o, plot_years, "Disturbance")
        plt.text(40, -50, "Fire", horizontalalignment='center', verticalalignment='center')
        plt.text(80, -50, "Beetles", horizontalalignment='center', verticalalignment='center')
        plt.xlim((0, simulation_length))
        plt.show()

    elif command == 'land':
        land(1, 1, detail=True)
        plt.show()

    elif command == 'uncert':
        import pandas as pd
        import seaborn as sns
        c_deficits = []
        c_harvests = []
        iterations = 100
        for i in range(iterations):
            years, c_deficit, c_harvest = land(i+1, iterations)
            c_deficits.append(c_deficit)
            c_harvests.append(c_harvest)
        g = sns.tsplot(c_deficits, years, color='red', condition='System C deficit')
        h = sns.tsplot(c_harvests, years, color='blue', condition='Cumulative C harvest')
        g.set_xlabel('Year')
        g.set_ylabel('Landscape MgC')
        plt.show()

    elif command == 'q':
        print "   Quitting application..."
        print
        print
        break

    else:
        print
        print "ERROR: Command not recognized"
        print "Please try again."
        print