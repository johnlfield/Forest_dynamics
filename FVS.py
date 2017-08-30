"""Routine to read tabular FVS model output
"""

import csv
from db_tools import list_to_sql
import matplotlib.pyplot as plt
import numpy as np
import os
import sqlite3 as lite


def type_assignment_upload(csv_fpath, db_fpath, table):

    # create temporary data storage structure and open .csv file
    data_table = []
    open_file = open(csv_fpath, "rU")
    csv_lines = csv.reader(open_file)

    # read the header, and create an associated list of data types
    text_columns = ['Stand ID', 'Mgmt ID', 'Species', 'Diam Class', 'Case ID']
    int_columns = ['Year']
    header = next(csv_lines)
    types = []
    for column in header:
        if column in text_columns:
            types.append('TEXT')
        if column in int_columns:
            types.append('INT')
        else:
            types.append('REAL')

    # remove any illegal characters from header (which will become SQLite column names) and text column list
    for i in range(len(header)):
        header[i] = header[i].translate(None, " ,.()-/")
    for i in range(len(text_columns)):
        text_columns[i] = text_columns[i].translate(None, " ,.()-/")

    # copy header, types, and data to storage structure, removing excess whitespace from all text entries
    data_table.append(header)
    data_table.append(types)
    for line in csv_lines:
        for text_column in text_columns:
            if text_column in header:
                text_index = header.index(text_column)
                line[text_index] = line[text_index].replace(" ", "")
        data_table.append(line)

    # transcribe temporary storage structure to SQLite database
    list_to_sql(data_table, db_fpath, table)
    return


def sql_to_nested_dictionaries(cursor_object, table, grouping_column):
        cursor_object.execute("SELECT DISTINCT %s FROM Master" % grouping_column)
        group_tuples = cur.fetchall()
        groups = zip(*group_tuples)[0]

        # import stand carbon timeseries into a dictionary-of-dictionaries structure
        outer_dictionary = {}
        cursor_object.execute("PRAGMA table_info(%s)" % table)
        column_tuples = cursor_object.fetchall()
        columns = zip(*column_tuples)[1]

        for group in groups:
            cursor_object.execute("SELECT * FROM %s WHERE %s='%s' " % (table, grouping_column, group))
            data_tuples = cur.fetchall()
            data = zip(*data_tuples)

            # load these results into a nested dictionary structure
            group_dictionary = {}
            for e, column_name in enumerate(columns):
                if column_name != grouping_column:
                    group_dictionary[column_name] = data[e]
            outer_dictionary[group] = group_dictionary

        return outer_dictionary


def nice_display(cursor, text):
    results = cursor.fetchall()
    print text
    for e, each_tuple in enumerate(results):
        string = str(e+1)
        for element in each_tuple:
            string += '\t'
            string += str(element)
        print string
    print


def deficit(years, systemC_control_list, systemC_RX_list):

        integrated_deficit = 0
        running_deficit = [0]

        previous_year = ''
        previous_control_C = ''
        previous_RX_C = ''

        for i, current_year in enumerate(years):
            current_control_C = systemC_control_list[i]
            current_RX_C = systemC_RX_list[i]

            # wait until second list element to start summing areas
            if previous_year:
                previous_deficit = previous_control_C-previous_RX_C
                current_deficit = current_control_C-current_RX_C
                area = ((previous_deficit+current_deficit) / 2.0) * (current_year-previous_year)
                integrated_deficit += area
                running_deficit.append(current_deficit)

            previous_year = current_year
            previous_control_C = current_control_C
            previous_RX_C = current_RX_C

        return integrated_deficit, running_deficit


### define working SQLite database, and FVS results filenames ##########################################################
db_fpath = 'FVS_analysis.db'
if os.path.exists(db_fpath):
    os.remove(db_fpath)

SS_table = 'SS_table.csv'
harvested_carbon = 'RX_NoClimate_CondReg150_carbon.csv'
control_carbon = 'NoRX_NoClimate_CondReg150_carbon.csv'
# harvested_summary = 'harvested_summary.csv'
# control_summary = 'control_summary.csv'

# load FVS results to working SQLite database
type_assignment_upload(SS_table, db_fpath, 'StandStock')
type_assignment_upload(harvested_carbon, db_fpath, 'harvested_carbon')
type_assignment_upload(control_carbon, db_fpath, 'control_carbon')
# type_assignment_upload(harvested_summary, db_fpath, 'harvested_summary')
# type_assignment_upload(control_summary, db_fpath, 'control_summary')

# establish a connection to the working database
con = lite.connect(db_fpath)
with con:
    cur = con.cursor()

    ### First, do some basic characterization & QC on the data in the Stock & Stand summary table ######################
    print
    cur.execute("SELECT COUNT(DISTINCT StandID) FROM StandStock")
    print "The file %s contains records for %i distinct stands" % (SS_table, cur.fetchall()[0][0])
    print

    cur.execute("SELECT StandID, Count(Distinct Year) FROM StandStock GROUP BY StandID")
    nice_display(cur, "There are the following numbers of time points for each stand:")

    cur.execute("SELECT StandID, COUNT(DISTINCT Species) FROM StandStock WHERE Species!='ALL' GROUP BY StandID")
    nice_display(cur, "There are the following numbers of tree species codes within each stand:")

    cur.execute("SELECT StandID, Species, COUNT(DISTINCT Year) FROM StandStock WHERE Species!='ALL' GROUP BY StandID, Species")
    nice_display(cur, "Here are the number of time points for each tree species code within each stand:")

    # determine initial stand mortality
    cur.execute(""" CREATE TABLE StartEndYear AS
                    SELECT StandID, MIN(Year) as StartYear, MAX(Year) as EndYear
                    FROM StandStock
                    GROUP BY StandID
                    ORDER BY StandID """)
    cur.execute("SELECT * FROM StartEndYear")
    nice_display(cur, "Here is the simulation starting date for each stand:")

    cur.execute(""" CREATE TABLE StandMortality AS
                    SELECT ss.StandID, ss.Year, (ss.MortBA/(ss.LiveBA+ss.MortBA)) AS InitialMortality
                    FROM StandStock ss
                    JOIN StartEndYear sey ON ss.StandID=sey.StandID
                    WHERE ss.Year=sey.StartYear AND ss.DiamClass='All' AND ss.Species='ALL'
                    ORDER BY ss.StandID """)
    cur.execute("SELECT * FROM StandMortality")
    nice_display(cur, "Here is the fraction of initial mortality of each stand on a BA basis:")

    # determine initial AND final stand BA
    cur.execute(""" CREATE TABLE StandBA AS
                    SELECT ss.StandID, ss.Year, ss.Species, (ss.LiveBA+ss.MortBA) AS TotBA
                    FROM StandStock ss
                    JOIN StartEndYear sey ON ss.StandID=sey.StandID
                    WHERE (ss.Year=sey.StartYear OR ss.Year=sey.EndYear) AND ss.DiamClass='All' AND ss.Species='ALL'
                    ORDER BY ss.StandID """)
    cur.execute("SELECT * FROM StandBA WHERE Year<2100")
    nice_display(cur, "Here is the INITIAL total basal area (live+dead) within each stand:")
    cur.execute("SELECT * FROM StandBA WHERE Year>2100")
    nice_display(cur, "Here is the FINAL total basal area (live+dead) within each stand:")

    # determine initial AND final stand species composition
    cur.execute(""" CREATE TABLE StandComposition AS
                    SELECT ss.StandID, ss.Year, ss.Species, (ss.LiveBA+ss.MortBA)/sba.TotBA AS BAShare
                    FROM StandStock ss
                    JOIN StandBA sba ON ss.StandID=sba.StandID AND ss.YEAR=sba.YEAR
                    WHERE ss.DiamClass='All' AND ss.Species!='ALL'
                    ORDER BY ss.StandID """)
    cur.execute("SELECT * FROM StandComposition WHERE Year<2100")
    nice_display(cur, "Here are the INITIAL shares of total basal area contributed by each species within each stand:")
    cur.execute("SELECT * FROM StandComposition WHERE Year<2100 AND Species='LP' ")
    nice_display(cur, "Here are the INITIAL shares of total basal area contributed by LODGEPOLE ONLY within each stand:")
    cur.execute("SELECT * FROM StandComposition WHERE Year>2100")
    nice_display(cur, "Here are the FINAL shares of total basal area contributed by each species within each stand:")

    cur.execute("SELECT * FROM StandComposition WHERE Year<2100 AND Species='AS' AND BAShare > 0.01 ")
    nice_display(cur, "Here are the INITIAL shares of total basal area contributed by ASPEN ONLY within each stand (where applicable):")
    cur.execute("SELECT * FROM StandComposition WHERE Year>2100 AND Species='AS' AND BAShare > 0.1 ")
    nice_display(cur, "Here are the stands that became partially or completely dominated by ASPEN:")


    ### JOIN stand carbon outputs to these stand summary characteristics ###############################################
    cur.execute(""" CREATE TABLE Master AS
                    SELECT c.StandID, c.Year, c.Aboveground_Total_Live AS Aboveground_Total_Live_control,
                            c.Total_Stand_Carbon AS Total_Stand_Carbon_control,
                            c.Total_Removed_Carbon AS Total_Removed_Carbon_control,
                        t.Aboveground_Total_Live AS Aboveground_Total_Live_RX,
                            t.Total_Stand_Carbon AS Total_Stand_Carbon_RX,
                            t.Total_Removed_Carbon AS Total_Removed_Carbon_RX
                    FROM control_carbon c
                    JOIN harvested_carbon t ON c.StandID=t.StandID AND c.Year=t.Year """)
    stand_C = sql_to_nested_dictionaries(cur, 'Master', 'StandID')

    # compute the integrated carbon deficit for each stand, and add to dictionary structure
    for stand_ID in stand_C:
        integrated_deficit, running_deficit = deficit(stand_C[stand_ID]['Year'],
                                              stand_C[stand_ID]['Total_Stand_Carbon_control'],
                                              stand_C[stand_ID]['Total_Stand_Carbon_RX'])
        stand_C[stand_ID]['Integrated_deficit'] = integrated_deficit
        stand_C[stand_ID]['Running_deficit'] = running_deficit

    # determine the min, median, and max deficit stands
    deficit_list = []
    for key in stand_C.keys():
        deficit_list.append((key, stand_C[key]['Integrated_deficit']))
    deficit_list.sort(key=lambda x: x[1])
    min_deficit_stand = deficit_list[0][0]
    med_deficit_stand = deficit_list[len(deficit_list)/2][0]
    max_deficit_stand = deficit_list[-1][0]

    detail_stands = [min_deficit_stand, med_deficit_stand, max_deficit_stand]
    detail_colors = ['g', 'b', 'r']

    # create an absolute ecosystem carbon plot (min/med/max stands only)
    for i, detail_stand in enumerate(detail_stands):
        detail_label = '%s cumulative deficit = %.0f Mg C y' % (detail_stand.split('_')[-1], stand_C[detail_stand]['Integrated_deficit'])
        plt.plot(stand_C[detail_stand]['Year'],
                 stand_C[detail_stand]['Total_Stand_Carbon_control'],
                 label=detail_label, marker='None', linestyle='--', linewidth=2, color=detail_colors[i])
        plt.plot(stand_C[detail_stand]['Year'],
                 stand_C[detail_stand]['Total_Stand_Carbon_RX'],
                 marker='None', linestyle='-', linewidth=2, color=detail_colors[i])
        plt.fill_between(stand_C[detail_stand]['Year'],
                         stand_C[detail_stand]['Total_Stand_Carbon_control'],
                         stand_C[detail_stand]['Total_Stand_Carbon_RX'],
                         color=detail_colors[i], alpha='0.3')
    plt.xlabel('Year')
    plt.ylabel('Total Ecosystem Carbon (units??)')
    plt.legend(loc=4, prop={'size': 11})
    plt.title('Stand integrated ecosystem carbon deficits-\nminimum, medium, and maximum')
    plt.savefig('Absolute_ecosystem_C_deficit_range.png')
    plt.close()

    # create a normalized carbon debt plot (min/med/max stands only)
    for i, detail_stand in enumerate(stand_C.keys()):
        detail_label = '%s cumulative deficit = %.0f Mg C y' % (detail_stand.split('_')[-1], stand_C[detail_stand]['Integrated_deficit'])
        cumulative_harvest = np.cumsum(stand_C[detail_stand]['Total_Removed_Carbon_RX'])
        normalized_deficit = stand_C[detail_stand]['Running_deficit'] / cumulative_harvest

        plt.plot(stand_C[detail_stand]['Year'], normalized_deficit,
                 marker='None', linestyle='-', linewidth=2, color=detail_colors[i], label=detail_label)

    plt.axhline(0, color='gray', linestyle='--', zorder=-1)
    plt.axhline(1, color='gray', linestyle='--', zorder=-1)
    plt.xlabel('Year')
    plt.ylabel('Normalized Ecosystem Carbon deficit (units??)')
    plt.legend(loc=4, prop={'size': 11})
    plt.title('Range of stand normalized ecosystem carbon deficits-\nminimum, medium, and maximum')
    plt.savefig('Normalized_ecosystem_C_deficit_range.png')
    plt.close()

print
