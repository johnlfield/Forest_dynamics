"""Routine to read tabular FVS model output
"""

from analysis_tools import gen_stats
import csv
from db_tools import list_to_sql
import matplotlib
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
    text_columns = ['StandID', 'MgmtID', 'Species', 'DiamClass', 'CaseID']
    int_columns = ['Year']
    header = next(csv_lines)

    # remove any illegal characters from header (which will become SQLite column names) and text column list
    for i in range(len(header)):
        header[i] = header[i].translate(None, " ,.()-/")

    types = []
    for column in header:
        if column in text_columns:
            types.append('TEXT')
        elif column in int_columns:
            types.append('INT')
        else:
            types.append('REAL')

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
        cursor_object.execute("SELECT DISTINCT %s FROM %s" % (grouping_column, table))
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

# load FVS results to working SQLite database
type_assignment_upload(SS_table, db_fpath, 'StandStock')
type_assignment_upload(harvested_carbon, db_fpath, 'harvested_carbon')
type_assignment_upload(control_carbon, db_fpath, 'control_carbon')

# establish a connection to the working database
con = lite.connect(db_fpath)
with con:
    cur = con.cursor()


    ### First, do some basic characterization & QC on the data in the Stock & Stand summary table ######################
    print
    cur.execute("SELECT COUNT(DISTINCT StandID) FROM StandStock")
    print "The file %s contains records for %i distinct stands" % (SS_table, cur.fetchall()[0][0])
    print

    # filter out stands that will become aspen-dominated
    # cur.execute("ALTER TABLE StandStock RENAME TO temp")
    # cur.execute(""" CREATE TABLE StandStock AS
    #                 SELECT * FROM temp
    #                 WHERE StandID NOT IN ('T1_MedBow_LS14', 'T1_MedBow_LS21', 'T1_MedBow_LS33', 'T1_MedBow_LS53', 'T1_MedBow_LS58', 'T1_MedBow_LS6') """)
    # cur.execute("DROP TABLE temp")

    cur.execute("SELECT StandID, Count(Distinct Year) FROM StandStock GROUP BY StandID")
    nice_display(cur, "There are the following numbers of time points for each stand:")

    cur.execute("SELECT StandID, COUNT(DISTINCT Species) FROM StandStock WHERE Species!='ALL' GROUP BY StandID")
    nice_display(cur, "There are the following numbers of tree species codes within each stand:")

    cur.execute(""" SELECT StandID, Species, COUNT(DISTINCT Year)
                    FROM StandStock
                    WHERE Species!='ALL'
                    GROUP BY StandID, Species """)
    nice_display(cur, "Here are the number of time points for each tree species code within each stand:")

    # determine initial stand mortality
    cur.execute(""" CREATE TABLE StartEndYear AS
                    SELECT StandID, MIN(Year) as StartYear, MAX(Year) as EndYear
                    FROM StandStock
                    GROUP BY StandID
                    ORDER BY StandID """)
    cur.execute("SELECT * FROM StartEndYear")
    nice_display(cur, "Here are the simulation starting and ending years for each stand:")

    cur.execute(""" CREATE TABLE StandMortality AS
                    SELECT ss.StandID, ss.Year, (ss.MortBA/(ss.LiveBA+ss.MortBA)) AS InitialMortality
                    FROM StandStock ss
                    JOIN StartEndYear sey ON ss.StandID=sey.StandID
                    WHERE ss.Year=sey.StartYear AND ss.DiamClass='All' AND ss.Species='ALL'
                    ORDER BY ss.StandID """)
    cur.execute("SELECT * FROM StandMortality")
    nice_display(cur, "Here is the fraction of initial mortality of each stand on a BA basis:")

    # determine stand BA by species and time
    # pivot/transpose from http://sqlite.1065341.n5.nabble.com/Transpose-selected-rows-into-columns-td81378.html
    cur.execute(""" CREATE TABLE StandBA AS
                    SELECT StandID, Year,
                        MAX(CASE Species WHEN 'AF' THEN (LiveBA+MortBA) ELSE 0.0 END) AF_BA,
                        MAX(CASE Species WHEN 'AS' THEN (LiveBA+MortBA) ELSE 0.0 END) AS_BA,
                        MAX(CASE Species WHEN 'ES' THEN (LiveBA+MortBA) ELSE 0.0 END) ES_BA,
                        MAX(CASE Species WHEN 'LP' THEN (LiveBA+MortBA) ELSE 0.0 END) LP_BA,
                        MAX(CASE Species WHEN 'OH' THEN (LiveBA+MortBA) ELSE 0.0 END) OH_BA,
                        MAX(CASE Species WHEN 'ALL' THEN (LiveBA+MortBA) ELSE 0.0 END) Tot_BA
                    FROM StandStock
                    GROUP BY StandID, Year """)
    cur.execute("SELECT b.StandID, b.Tot_BA FROM StandBA b JOIN StartEndYear y WHERE b.StandID=y.StandID AND b.Year=y.StartYear")
    nice_display(cur, "Here is the INITIAL total basal area (live+dead) within each stand:")
    # verify that transpose operation didn't miss anything
    cur.execute("ALTER TABLE StandBA ADD COLUMN Tot_BA_check REAL")
    cur.execute("UPDATE StandBA SET Tot_BA_check=(AF_BA + AS_BA + ES_BA + LP_BA + OH_BA - Tot_BA)/Tot_BA")
    cur.execute("SELECT StandID, AVG(Tot_BA_check) FROM StandBA WHERE Tot_BA_check>0 GROUP BY StandID")
    print "###############################################################################################"
    nice_display(cur, "WARNING- the following stands have species summation average percentage errors as follows:")
    print "###############################################################################################"
    print

    # determine stand BA shares by species and time
    cur.execute(""" CREATE TABLE StandComposition AS
                    SELECT StandID, Year,
                        AF_BA/Tot_BA AS AF_share,
                        AS_BA/Tot_BA AS AS_share,
                        ES_BA/Tot_BA AS ES_share,
                        LP_BA/Tot_BA AS LP_share,
                        OH_BA/Tot_BA AS OH_share
                    FROM StandBA """)

    cur.execute("SELECT * FROM StandComposition c JOIN StartEndYear y WHERE c.StandID=y.StandID AND c.Year=y.StartYear")
    nice_display(cur, "Here are the INITIAL shares of total basal area contributed by each species within each stand (AF, AS, ES, LP, OH):")
    cur.execute("SELECT * FROM StandComposition c JOIN StartEndYear y WHERE c.StandID=y.StandID AND c.Year=y.EndYear")
    nice_display(cur, "Here are the FINAL shares of total basal area contributed by each species within each stand (AF, AS, ES, LP, OH):")


    cur.execute("SELECT c.StandID, c.AS_share FROM StandComposition c JOIN StartEndYear y WHERE c.StandID=y.StandID AND c.Year=y.StartYear AND AS_share>0.0001")
    nice_display(cur, "Here are the INITIAL shares of total basal area contributed by ASPEN ONLY for each stand:")
    cur.execute("SELECT c.StandID, c.AS_share FROM StandComposition c JOIN StartEndYear y WHERE c.StandID=y.StandID AND c.Year=y.EndYear AND AS_share>0.0001")
    nice_display(cur, "Here are the stands that became partially or completely dominated by ASPEN:")

    # determine stand live TPA by time
    cur.execute(""" CREATE TABLE TPA AS
                    SELECT StandID, Year,
                        MAX(CASE WHEN DiamClass=2 THEN LiveTPA ELSE 0.0 END) AS 'd2',
                        MAX(CASE WHEN DiamClass=4 THEN LiveTPA ELSE 0.0 END) AS 'd4',
                        MAX(CASE WHEN DiamClass=6 THEN LiveTPA ELSE 0.0 END) AS 'd6',
                        MAX(CASE WHEN DiamClass=8 THEN LiveTPA ELSE 0.0 END) AS 'd8',
                        MAX(CASE WHEN DiamClass=10 THEN LiveTPA ELSE 0.0 END) AS 'd10',
                        MAX(CASE WHEN DiamClass=12 THEN LiveTPA ELSE 0.0 END) AS 'd12',
                        MAX(CASE WHEN DiamClass=14 THEN LiveTPA ELSE 0.0 END) AS 'd14',
                        MAX(CASE WHEN DiamClass=16 THEN LiveTPA ELSE 0.0 END) AS 'd16',
                        MAX(CASE WHEN DiamClass=18 THEN LiveTPA ELSE 0.0 END) AS 'd18',
                        MAX(CASE WHEN DiamClass=20 THEN LiveTPA ELSE 0.0 END) AS 'd20',
                        MAX(CASE WHEN DiamClass=22 THEN LiveTPA ELSE 0.0 END) AS 'd22',
                        MAX(CASE WHEN DiamClass=24 THEN LiveTPA ELSE 0.0 END) AS 'd24',
                        MAX(CASE WHEN DiamClass=26 THEN LiveTPA ELSE 0.0 END) AS 'd26',
                        MAX(CASE WHEN DiamClass=28 THEN LiveTPA ELSE 0.0 END) AS 'd28',
                        MAX(CASE WHEN DiamClass=30 THEN LiveTPA ELSE 0.0 END) AS 'd30',
                        MAX(CASE WHEN DiamClass='All' THEN LiveTPA ELSE 0.0 END) AS 'Tot_TPA'
                    FROM StandStock
                    WHERE Species="ALL"
                    GROUP BY StandID, Year """)
    # cur.execute("ALTER TABLE TPA RENAME TO tmp")
    # cur.execute(""" CREATE TABLE TPA(StandID TEXT, Year INT, d2 REAL, d4 REAL, d6 REAL, d8 REAL, d10 REAL, d12 REAL,
    #                  d14 REAL, d16 REAL, d18 REAL, d20 REAL, d22 REAL, d24 REAL, d26 REAL, d28 REAL, d30 REAL,
    #                  Tot_TPA REAL) """)
    # cur.execute(""" INSERT INTO TPA(StandID, Year, d2, d4, d6, d8, d10, d12, d14, d16, d18, d20, d22, d24, d26, d28, d30, Tot_TPA)
    #                 SELECT * FROM tmp """)
    # cur.execute("DROP TABLE tmp")

    cur.execute("ALTER TABLE TPA ADD COLUMN small_TPA REAL")
    cur.execute("UPDATE TPA SET small_TPA=(d2 + d4 + d6 + d8)")
    cur.execute("ALTER TABLE TPA ADD COLUMN big_TPA REAL")
    cur.execute("UPDATE TPA SET big_TPA=(d10 + d12 + d14 + d16 + d18 + d20 + d22 + d24 + d26 + d28 + d30)")
    cur.execute("ALTER TABLE TPA ADD COLUMN small_big_ratio REAL")
    cur.execute("UPDATE TPA SET small_big_ratio=small_TPA/big_TPA")
    cur.execute("SELECT t.StandID, t.small_big_ratio FROM TPA t JOIN StartEndYear y WHERE t.StandID=y.StandID AND t.Year=y.StartYear")
    nice_display(cur, "Here is the INITIAL ratio of small:big trees (<10in cutoff) within each stand:")
    # verify that transpose operation didn't miss anything
    cur.execute("UPDATE TPA SET small_big_ratio=small_TPA/big_TPA")
    cur.execute("ALTER TABLE TPA ADD COLUMN Tot_TPA_check REAL")
    cur.execute("UPDATE TPA SET Tot_TPA_check=(small_TPA+big_TPA-Tot_TPA)/Tot_TPA")
    cur.execute("SELECT StandID, AVG(Tot_TPA_check) FROM TPA WHERE Tot_TPA_check>0 GROUP BY StandID")
    print "###############################################################################################"
    nice_display(cur, "WARNING- the following stands have TPA summation average percentage errors as follows:")
    print "###############################################################################################"
    print

    ### Read stand carbon outputs ######################################################################################
    cur.execute(""" CREATE TABLE Carbon AS
                    SELECT c.StandID, c.Year, c.Aboveground_Total_Live AS Aboveground_Total_Live_control,
                            c.Total_Stand_Carbon AS Total_Stand_Carbon_control,
                            c.Total_Removed_Carbon AS Total_Removed_Carbon_control,
                        t.Aboveground_Total_Live AS Aboveground_Total_Live_RX,
                            t.Total_Stand_Carbon AS Total_Stand_Carbon_RX,
                            t.Total_Removed_Carbon AS Total_Removed_Carbon_RX
                    FROM control_carbon c
                    JOIN harvested_carbon t ON c.StandID=t.StandID AND c.Year=t.Year """)
                    # WHERE c.StandID NOT IN ('T1_MedBow_LS14', 'T1_MedBow_LS21', 'T1_MedBow_LS33', 'T1_MedBow_LS53', 'T1_MedBow_LS58', 'T1_MedBow_LS6') """)
    stand_C = sql_to_nested_dictionaries(cur, 'Carbon', 'StandID')

    # compute the integrated carbon deficit for each stand, and add to dictionary structure
    for stand_ID in stand_C:
        integrated_deficit, running_deficit = deficit(stand_C[stand_ID]['Year'],
                                              stand_C[stand_ID]['Total_Stand_Carbon_control'],
                                              stand_C[stand_ID]['Total_Stand_Carbon_RX'])
        stand_C[stand_ID]['Integrated_deficit'] = integrated_deficit
        stand_C[stand_ID]['Running_deficit'] = running_deficit


    ### Plot illustrative C deficit results for the min, median, and max deficit stands ################################
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
    for i, standID in enumerate(detail_stands):
        detail_label = '%s cumulative deficit = %.0f Mg C y' % (standID.split('_')[-1],
                                                                stand_C[standID]['Integrated_deficit'])
        plt.plot(stand_C[standID]['Year'],
                 stand_C[standID]['Total_Stand_Carbon_control'],
                 label=detail_label, marker='None', linestyle='--', linewidth=2, color=detail_colors[i])
        plt.plot(stand_C[standID]['Year'],
                 stand_C[standID]['Total_Stand_Carbon_RX'],
                 marker='None', linestyle='-', linewidth=2, color=detail_colors[i])
        plt.fill_between(stand_C[standID]['Year'],
                         stand_C[standID]['Total_Stand_Carbon_control'],
                         stand_C[standID]['Total_Stand_Carbon_RX'],
                         color=detail_colors[i], alpha='0.3')
    plt.xlabel('Year')
    plt.ylabel('Total Ecosystem Carbon (units??)')
    plt.legend(loc=4, prop={'size': 11})
    plt.title('Stand integrated ecosystem carbon deficits-\nminimum, medium, and maximum')
    plt.savefig('Absolute_ecosystem_deficit_detail.png')
    plt.close()

    # create a normalized carbon debt plot (min/med/max stands only)
    for i, standID in enumerate(detail_stands):
        detail_label = '%s cumulative deficit = %.0f Mg C y' % (standID.split('_')[-1],
                                                                stand_C[standID]['Integrated_deficit'])
        cumulative_harvest = np.cumsum(stand_C[standID]['Total_Removed_Carbon_RX'])
        normalized_deficit = stand_C[standID]['Running_deficit'] / cumulative_harvest

        plt.plot(stand_C[standID]['Year'], normalized_deficit,
                 marker='None', linestyle='-', linewidth=2, color=detail_colors[i], label=detail_label)

    plt.axhline(0, color='gray', linestyle='--', zorder=-1)
    plt.axhline(1, color='gray', linestyle='--', zorder=-1)
    plt.xlabel('Year')
    plt.ylabel('Normalized Ecosystem Carbon deficit (units??)')
    plt.legend(loc=3, prop={'size': 11})
    plt.title('Range of stand normalized ecosystem carbon deficits-\nminimum, medium, and maximum')
    plt.savefig('Normalized_ecosystem_deficit_detail.png')
    plt.close()

    ### Plot normalized C deficit results for all stands ###############################################################
    counts = [0, 0, 0]
    for i, standID in enumerate(stand_C.keys()):
        cumulative_harvest = np.cumsum(stand_C[standID]['Total_Removed_Carbon_RX'])
        normalized_deficit = stand_C[standID]['Running_deficit'] / cumulative_harvest
        stand_C[standID]['Normalized_deficit'] = normalized_deficit

        if standID not in ['T1_MedBow_LS7', 'T1_MedBow_LS82']:
            color = 'c'
            zorder = 0
            if normalized_deficit[-1] >= 1.0:
                color = 'y'
                counts[0] += 1
            elif normalized_deficit[-1] >= 0.0:
                color = 'g'
                zorder += 1
                counts[1] += 1
            else:
                color = 'b'
                zorder += 2
                counts[2] += 1

            plt.plot(stand_C[standID]['Year'], normalized_deficit,
                     marker='None', linestyle='-', linewidth=1, color=color, zorder=zorder)

    plt.axhline(0, color='k', linestyle='--', zorder=-1)
    plt.axhline(1, color='k', linestyle='--', zorder=-1)
    plt.text(2205, 1.5, "%i stands\nlose more\nC than is\nharvested" % counts[0], color='y')
    plt.text(2205, 0.0, "%i stands\npartially\nrecover C\ndeficit" % counts[1], color='g')
    plt.text(2205, -1.1, "%i stands\nout-grow\ntheir controls" % counts[2], color='b')
    plt.xlabel('Year')
    plt.ylabel('Normalized Ecosystem Carbon deficit (units??)')
    plt.title('Normalized ecosystem carbon deficits-\nall stands')
    plt.savefig('Normalized_ecosystem_C_deficit_range.png')
    plt.close()

    ### Scatterplots of normalized deficit vs. stand characteristics ###################################################

    # load deficit results to database and JOIN to stand metadata
    deficit_upload = [['StandID', 'Integrated_deficit', 'End_normalized_deficit'],
                      ['TEXT', 'REAL', 'REAL']]
    for key in stand_C.keys():
        deficit_upload.append([str(key), stand_C[key]['Integrated_deficit'], stand_C[key]['Normalized_deficit'][-1]])
    list_to_sql(deficit_upload, db_fpath, 'Deficit')

    def significance_test(xs, ys):
        n, slope, intercept, r_value, p_value, rmse, mdms = gen_stats(xs, ys)
        if p_value < 0.05:
            line_x_min = 0.6 * min(xs)
            line_x_max = 1.2 * max(xs)
            plt.plot([line_x_min, line_x_max], [intercept+(slope*line_x_min), intercept+(slope*line_x_max)], '--',
                     color='grey')

    plt.subplot(3, 3, 1)
    cur.execute(""" SELECT c.LP_share, d.End_normalized_deficit
                    FROM Deficit d
                    JOIN StandComposition c ON d.StandID=c.StandID
                    JOIN StartEndYear y WHERE d.StandID=y.StandID AND c.Year=y.EndYear """)
    data_tuples = cur.fetchall()
    data = zip(*data_tuples)
    plt.scatter(data[0], data[1])
    significance_test(data[0], data[1])
    plt.xlabel('Final lodgepole retention (fraction of BA)')
    plt.ylabel('End normalized C deficit')

    plt.subplot(3, 3, 2)
    cur.execute(""" SELECT c.AS_share, d.End_normalized_deficit
                    FROM Deficit d
                    JOIN StandComposition c ON d.StandID=c.StandID
                    JOIN StartEndYear y WHERE d.StandID=y.StandID AND c.Year=y.EndYear """)
    data_tuples = cur.fetchall()
    data = zip(*data_tuples)
    plt.scatter(data[0], data[1])
    significance_test(data[0], data[1])
    plt.xlabel('Final aspen content (fraction of BA)')
    plt.ylabel('End normalized C deficit')

    plt.subplot(3, 3, 3)
    cur.execute(""" SELECT m.InitialMortality, d.End_normalized_deficit
                    FROM Deficit d
                    JOIN StandMortality m ON d.StandID=m.StandID """)
    data_tuples = cur.fetchall()
    data = zip(*data_tuples)
    plt.scatter(data[0], data[1])
    significance_test(data[0], data[1])
    plt.xlabel('Initial stand mortality (basal area basis)')
    plt.ylabel('End normalized C deficit')

    plt.subplot(3, 3, 4)
    cur.execute(""" SELECT a.Tot_BA, d.End_normalized_deficit
                    FROM Deficit d
                    JOIN StandBA a ON d.StandID=a.StandID
                    JOIN StartEndYear y WHERE d.StandID=y.StandID AND a.Year=y.StartYear """)
    data_tuples = cur.fetchall()
    data = zip(*data_tuples)
    plt.scatter(data[0], data[1])
    significance_test(data[0], data[1])
    plt.xlabel('Initial stand total basal area (ft2 ac-1)')
    plt.ylabel('End normalized C deficit')

    plt.subplot(3, 3, 5)
    cur.execute(""" SELECT c.LP_share, d.End_normalized_deficit
                    FROM Deficit d
                    JOIN StandComposition c ON d.StandID=c.StandID
                    JOIN StartEndYear y WHERE d.StandID=y.StandID AND c.Year=y.StartYear """)
    data_tuples = cur.fetchall()
    data = zip(*data_tuples)
    plt.scatter(data[0], data[1])
    significance_test(data[0], data[1])
    plt.xlabel('Initial lodgepole purity (fraction of BA)')
    plt.ylabel('End normalized C deficit')

    plt.subplot(3, 3, 6)
    cur.execute(""" SELECT t.Tot_TPA, d.End_normalized_deficit
                    FROM Deficit d
                    JOIN TPA t ON d.StandID=t.StandID
                    JOIN StartEndYear y WHERE d.StandID=y.StandID AND t.Year=y.StartYear """)
    data_tuples = cur.fetchall()
    data = zip(*data_tuples)
    plt.scatter(data[0], data[1])
    significance_test(data[0], data[1])
    plt.xlabel('Initial live TPA')
    plt.ylabel('End normalized C deficit')

    plt.subplot(3, 3, 7)
    cur.execute(""" SELECT t.small_big_ratio, d.End_normalized_deficit
                    FROM Deficit d
                    JOIN TPA t ON d.StandID=t.StandID
                    JOIN StartEndYear y WHERE d.StandID=y.StandID AND t.Year=y.StartYear AND t.small_big_ratio NOT null """)
    data_tuples = cur.fetchall()
    data = zip(*data_tuples)
    plt.scatter(data[0], data[1])
    significance_test(data[0], data[1])
    plt.xlabel('Initial small:big live tree ratio (10in cutoff)')
    plt.ylabel('End normalized C deficit')

    plt.subplot(3, 3, 8)
    cur.execute(""" SELECT t.Tot_TPA
                    FROM TPA t
                    JOIN StartEndYear y ON t.StandID=y.StandID WHERE t.Year=y.StartYear """)
    x_tuples = cur.fetchall()
    xs = zip(*x_tuples)[0]
    print xs
    print
    cur.execute(""" SELECT c.AS_share
                    FROM StandComposition c
                    JOIN StartEndYear y ON c.StandID=y.StandID AND c.Year=y.EndYear """)
    y_tuples = cur.fetchall()
    ys = zip(*y_tuples)[0]
    print ys
    print
    plt.scatter(xs, ys)
    significance_test(xs, ys)
    plt.xlabel('Initial live TPA')
    plt.ylabel('Final aspen content (fraction of BA)')

    matplotlib.rcParams.update({'font.size': 8})
    plt.tight_layout()
    plt.savefig('Deficit_determinants.png')
    plt.close()

print
