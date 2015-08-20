""" This module develops a simple conceptual model for exploring forest carbon storage dynamics
considering stand growth and response to stochastic fire, insect, and harvest disturbances.

"""


import matplotlib.pyplot as plt
import numpy as np


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
params = {'age_max': [200, 'years', 'estimated maximum stand age'],
          'n_age': [4, '-', 'hydraulic conductivity age modifier exponent'],
          'phi_s': [5.5, 'kWh/m2/day', 'annually-averaged incoming short-wave radiation'],   # Denver http://www.apricus.com/upload/userfiles/images/Insolation-levels-USA.jpg
          'f_DT': [0.5, '-', 'annually-averaged temperature/moisture modifier value'],
          'sigma_f': [3.2, 'm2/kg', 'specific leaf area'],   # Chen et al. CJFR 1996 Fig. 3c
          'beers_k': [0.4, '-', 'Beers Law light extinction coefficient']   # Binkley et al. FEM 2013 Fig. 4c; POOR MODEL FOR LODGEPOLE!
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

    # read most current values of state variables
    w_f = states['w_f'][-1]
    w_s = states['w_s'][-1]
    w_r = states['w_r'][-1]

    # calculate LAI, canopy light interception fraction
    sigma_f_conv = 0.1 * sigma_f   # specific leaf area conversion to ha/Mg
    LAI = w_f * sigma_f_conv   # leaf area index, m2/m2
    intercept_fraction = 1 - beers_law_scalar(beers_k, LAI)

    # calculate average annual insolation, age modifier, and annual total biomass increment
    phi_s_conv = phi_s * 3.6   # average short-wave insolation conversion to MJ/m2/day
    phi_p = phi_s_conv * 0.45   # photosynthetically-active radiation is 45% of total shortwave
    phi_pa = phi_p * intercept_fraction   # absorbed PAR
    alpha_c = 1.8   # universal canopy quantum efficiency coefficient, gC/MJ
    f_age = age_modifier(age, age_max, n_age)
    avg_daily_C_increment = phi_pa * alpha_c * f_DT * f_age   # gC/m2/day
    c_concentration = 0.45
    annual_biomass_increment = (avg_daily_C_increment/c_concentration) * 365 * 0.01  # Mg/ha/y

    # allocation and biomass turnover
    # ToDo: update this with actual allometric equations
    # ToDo: update litterfall routine with attenuation for young stands
    w_f += (0.33 * annual_biomass_increment) - (0.25 * w_f)
    w_s += (0.33 * annual_biomass_increment) - (0.25 * w_s)
    w_r += 0.33 * annual_biomass_increment
    AGB = w_f + w_s

    # update state variable time series
    states['age'].append(age)
    states['w_f'].append(w_f)
    states['w_s'].append(w_s)
    states['w_r'].append(w_r)
    states['AGB'].append(AGB)
    states['LAI'].append(LAI)
    states['interception'].append(intercept_fraction)


# main control loop
while True:
    # define state variable time series initial values
    states = {'age': [0],   # stand age since last disturbance
              'w_f': [0.1],   # foliage weight, Mg/ha
              'w_s': [0.1],   # stem weight, Mg/ha
              'w_r': [0.1],   # root weight, Mg/ha
              'AGB': [0.2],   # aboveground biomass, Mg/ha, for display purposes only
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
    print "*************************************************************************************************"
    command = raw_input("Please enter the name of the parameter or initial state value to update, 'stand' to plot stand-\nlevel results, 'land' to plot landscape-level consortium runs, or 'q' to quit:\n")
    print

    if command in params.keys():
        value = raw_input("Please specify a new value for this parameter: ")
        params[command][0] = float(value)

    elif command in states.keys():
        value = raw_input("Please specify a new initial value for this state variable: ")
        params[command][0] = float(value)

    elif command == 'stand':
        # step through a sequence of simulation years and apply the 3-PG growth model each year
        simulation_years = range(0, 120)
        age = 0
        for year in simulation_years:
            three_PG(age, params, states)
            age += 1
        # plot results
        simulation_years.insert(0, 0)   # insert a value corresponding to initial conditions
        plt.subplot(3, 1, 1)
        plt.plot(simulation_years, states['LAI'])
        plt.ylabel("LAI\n(m2/m2)")
        plt.subplot(3, 1, 2)
        plt.plot(simulation_years, states['interception'])
        plt.ylabel("Canopy light\ninterception fraction")
        plt.subplot(3, 1, 3)
        plt.plot(simulation_years, states['AGB'])
        plt.xlabel("Time (years)")
        plt.ylabel("Aboveground live biomass\n(Mg/ha)")
        plt.show()

    elif command == 'land':
        # determine a random distribution of starting stand ages
        runs = 100
        start_ages = np.random.normal(100, 20, runs)   # assuming median stand age corresponds to railroad logging boom
        print "Initial stand age distribution:"
        print start_ages
        print
        simulation_length = 100
        total_AGB = [0]
        for i in range(simulation_length):
            total_AGB.append(0)
        run = 1
        plt.subplot(2, 1, 1)
        for start_age in start_ages:
            print "Simulating stand %i of %i" % (run, runs)
            start_age = int(start_age)
            # print "Starting age:"
            # print start_age
            print
            # step through a sequence of simulation years and apply the 3-PG growth model each year
            simulation_years = range(0, start_age+simulation_length)
            local_states = {'age': [states['age'][0]],
                            'w_f': [states['w_f'][0]],
                            'w_s': [states['w_s'][0]],
                            'w_r': [states['w_r'][0]],
                            'AGB': [states['AGB'][0]],
                            'LAI': [states['LAI'][0]],
                            'interception': [states['interception'][0]]
                            }
            # print "Master copy of initial state variables:"
            # print states
            # print
            # print "Local copy(?) of state variables:"
            # print local_states
            # print
            age = 0
            for year in simulation_years:
                three_PG(age, params, local_states)
                age += 1
            # drop the 'spin-up' results
            simulation_years.insert(0, 0)   # insert a value corresponding to initial conditions
            # print "Full results:"
            # print local_states['age']
            for key in local_states.keys():
                for i in range(start_age):
                    del local_states[key][0]
            # print
            # print "Truncated results:"
            # print local_states['age']
            # print
            # plot results
            plt.plot(range(simulation_length+1), local_states['AGB'], color="g")
            for i in range(len(total_AGB)):
                total_AGB[i] += local_states['AGB'][i]
            run += 1

        plt.ylabel("Aboveground live biomass\n(Mg/ha)")
        plt.subplot(2, 1, 2)
        plt.plot(range(simulation_length+1), total_AGB)
        plt.ylabel("Total landscape AG live\nbiomass (Mg)")
        plt.xlabel("Time (years)")
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