#!/Users/johnfield/GIS_sandbox/bin/python

""" This module performs basic analysis of raw tabular output from the FVS model, and calculates a stand-level carbon
deficit time-series.  The data analysis makes extensive use of SQLite files and queries (via the sqlite3 module) in
order to easily parse the FVS results, particularly those in the Stand & Stock table.  In some cases, stand-level
results are transcribed from the SQLite database into a nested python dictionary structure for easier management (for
example, storing data on carbon density within various pools for each stand), via the sql_to_nested_dictionaries()
function.  Summary figures are generated in matplotlib.  Other module dependencies include numpy for its basic vector
algebra capability; statsmodels for running multiple linear regression to determine which model inputs drive key model
results; my own analysis_tools.gen_stats() function to facilitate linear regression with significance testing; and
my own db_tools.list_to_sql() function to facilitate uploading tabular data to a SQLite database file.
"""

from analysis_tools import gen_stats
import csv
import datetime
from db_tools import list_to_sql
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import os
import sqlite3


# define conversion constants
_acre_to__ha = 1.0/0.40469
st_acre_to_Mg_ha = 0.90719/0.40469
ft2_acre_to_m2_ha = ((12.0*0.0254)**2) * (1.0/0.40469)


def type_assignment_bulk_convert_upload(csv_fpath, db_fpath, table, conversion_factor=0.0):
    """ Function facilitates uploading tabular .csv file data without a row of data types to a SQLite database.
    Rather than looking for SQLite data types as the second row in the .csv file, this routine assigns a type of 'REAL'
    to every data column except those listed in the 'text_columns' (assigned 'TEXT') and 'int_columns' (assigned 'INT')
    lists below.

    :param csv_fpath: full path to .csv file to be uploaded (str)
    :param db_fpath: full path to SQLite database file to receive data (str)
    :param table: name for table to be created with the database (str)
    :return:
    """

    # create temporary data storage structure and open .csv file
    data_table = []
    open_file = open(csv_fpath, "rU")
    csv_lines = csv.reader(open_file)

    # read the .csv file header, and specify column names of data type 'TEXT' or 'INT' (rather than 'REAL')
    header = next(csv_lines)
    text_columns = ['StandID', 'MgmtID', 'Species', 'DiamClass', 'CaseID']
    int_columns = ['Year', 'Forest_type']

    # remove any SQLite-illegal characters from the header list (which will become SQLite column names)
    for i in range(len(header)):
        header[i] = header[i].translate(None, " ,.()-/")

    # create a list of SQLite types corresponding to the header list
    types = []
    for column in header:
        if column in text_columns:
            types.append('TEXT')
        elif column in int_columns:
            types.append('INT')
        else:
            types.append('REAL')

    # copy header list, types list, and raw data to the temporary data storage structure, removing excess whitespace
    # from all TEXT data entries
    data_table.append(header)
    data_table.append(types)
    for line in csv_lines:
        for text_column in text_columns:
            if text_column in header:
                text_index = header.index(text_column)
                line[text_index] = line[text_index].replace(" ", "")
        data_table.append(line)

    # apply unit conversion to all float data
    if conversion_factor:
        for row in data_table[2:]:
            for e, entry in enumerate(row):
                if types[e] == 'REAL':
                    row[e] = str(float(row[e]) * conversion_factor)

    # transcribe temporary storage structure to SQLite database
    list_to_sql(data_table, db_fpath, table)
    return


def sql_append_unit_conversion(cursor_object, table, original_column, new_column, conversion_factor):
    """ Simple function to facilitate taking data from a column, applying a conversion factor, and saving it into a new
    column with a different name (note that SQLite lacks the capability to re-name existing columns).

    :param cursor_object: cursor object defined within an open sqlite3 database connection
    :param table: the name of the table within the open database to be modified (str)
    :param original_column: column within the database table which will supply the data for conversion (str)
    :param new_column: column to be created within the database table containing the copied & converted data (str)
    :param conversion_factor:
    :return:
    """

    cursor_object.execute("ALTER TABLE %s ADD COLUMN %s REAL" % (table, new_column))
    cursor_object.execute("UPDATE %s SET %s=(%s * %f)" % (table, new_column, original_column, conversion_factor))


def sql_to_nested_dictionaries(cursor_object, table, grouping_column):
    """ Function to transcribe tabular data within an SQLite database into a nested dictionary structure within
    python, facilitating easier management of complex hierarchical datasets.  Unique grouping_column entries are used
    to generate keys for the high-level outer dictionary.  Each entry in the high-level outer dictionary contains a
    lower-level inner dictionary with keys corresponding to each of the other columns in the database, and containing
    the associated rows of data as individual python lists.  In our case, this facilitates accessing individual
    time-series of carbon density for the different forest carbon pools (inner dictionary keys) for individual stands
    (outer dictionary keys) in the format:  dictionary[stand][pool]

    :param cursor_object: cursor object defined within an open sqlite3 database connection
    :param table: the name of the table within the open database to be transcribed (str)
    :param grouping_column: column within the database table which will be used to generate outer dictionary keys (str)
    :return: the two-level hierarchical python dictionary containing the transcribed data
    """

    # read grouping_column entries from database table to determine unique keys for outer dictionary
    cursor_object.execute("SELECT DISTINCT %s FROM %s" % (grouping_column, table))
    outer_key_tuples = cursor_object.fetchall()
    outer_keys = zip(*outer_key_tuples)[0]

    # read full set of columns from database table to determine keys for inner dictionary
    cursor_object.execute("PRAGMA table_info(%s)" % table)
    column_tuples = cursor_object.fetchall()
    columns = zip(*column_tuples)[1]

    # create nested dictionary structure, and save database table rows as python lists within that structure
    outer_dictionary = {}
    for outer_key in outer_keys:
        cursor_object.execute("SELECT * FROM %s WHERE %s='%s' " % (table, grouping_column, outer_key))
        data_tuples = cursor_object.fetchall()
        data = zip(*data_tuples)

        # load these results into a nested dictionary structure
        inner_dictionary = {}
        for e, column_name in enumerate(columns):
            if column_name != grouping_column:
                inner_dictionary[column_name] = data[e]
        outer_dictionary[outer_key] = inner_dictionary

    return outer_dictionary


def fetch_print(cursor_object, text):
    """ Function to facilitate extracting and displaying the results fof SQLite database queries, simple operations that
    are typically performed in a series.  Specifically, this function:
       * performs a fetchall() operation to get the results of a SQLite query (data returned as tuples)
       * prints a short description of the data being displayed
       * prints the tuple data as a numbered, tab-deliminted table for easier viewing
    :param cursor_object: cursor object defined within an open sqlite3 database connection
    :param text: short text description of data being displayed (str)
    :return:
    """

    query_results_tuple = cursor_object.fetchall()
    print text
    for e, each_tuple in enumerate(query_results_tuple):
        string = str(e+1)
        for element in each_tuple:
            string += '\t\t'
            string += str(element)
        print string
    print


def significance_test(xs, ys):
    """ Routine to perform linear regression on a dataset, determine regression significance, and add a trendline to
    the current active matplotlib plot in the event of significance.

    :param xs: list of data X values (list of float)
    :param ys: list of data Y values (list of float)
    :return:
    """

    n, slope, intercept, r_value, p_value, rmse, mdms = gen_stats(xs, ys)
    if p_value < 0.05:
        line_x_min = 0.6 * min(xs)
        line_x_max = 1.2 * max(xs)
        plt.plot([line_x_min, line_x_max], [intercept+(slope*line_x_min), intercept+(slope*line_x_max)], '--',
                 color='grey')


def deficit(years, systemC_control_list, systemC_RX_list):
    """ Calculates an ecosystem carbon deficit time-series as the difference in total ecosystem C storage between a
    control and a treatment (RX) scenario.

    :param years: python list of simulation year (list of int)
    :param systemC_control_list: total ecosystem carbon storage data for the control scenario (list of float)
    :param systemC_RX_list: total ecosystem carbon storage data for the RX scenario (list of float)
    :return: total time-integrated ecosystem C deficit (float); list of instantaneous ecosystem C deficits corresponding
       to the years list (list of float)
    """

    # define variables for keeping track of the current year being analyzed, the previous year's C deficit, etc.
    previous_year = ''
    previous_control_C = ''
    previous_RX_C = ''
    integrated_deficit = 0
    running_deficit = [0]

    # loop through each year, and read the control and X carbon results
    for i, current_year in enumerate(years):
        current_control_C = systemC_control_list[i]
        current_RX_C = systemC_RX_list[i]

        # starting in the second year, approximate the integral of carbon deficit over time with the trapezoidal rule
        if previous_year:
            previous_deficit = previous_control_C - previous_RX_C
            current_deficit = current_control_C - current_RX_C
            integral = ((previous_deficit + current_deficit) / 2.0) * (current_year - previous_year)
            integrated_deficit += integral
            running_deficit.append(current_deficit)

        # update the variables keeping track of the previous year's results
        previous_year = current_year
        previous_control_C = current_control_C
        previous_RX_C = current_RX_C

    return integrated_deficit, running_deficit


def upload_convert_filter_process(working_path, db_file, rx_control_prefixes, site_file, filter_string=''):
    """ Function to upload raw FVS Stand & Stock table and FFE carbon results into a database, and process into new
    summary data tables.  Operations include defining input file paths; uploading files to an SQLite database, including
    bulk unit conversion for the Carbon results; performing individual column unit conversions for Stand & Stock
    tables; and creating derivative tables of initial mortality, basal area and trees per hectare by species, etc., to
    facilitate further stand-level analysis; and to load forest carbon pool data into a nested python dictionary
    structure.

    :param working_path: full path where input data files are located (str)
    :param db_file: name of SQLite database file to receive data (str)
    :param rx_control_prefixes: list containing the descriptive scenario names (file prefixes) for both the Treatment
        and Control scenarios (list of two str)
    :param site_file: the full name (extension included) of the file within the working_path in which contains FVS site
        data (aspect, elevation, slope, etc.) (str)
    :param filter_string: SQLite query (e.g., WHERE StandID !='T1_MedBow_LS7') to be applied to filter out specific
        stands or other records from all input data files (str)
    :return: path where database file and all results files & figures will be stored (str); nested dictionary structure
        containing stand carbon density data (dict of float)
    """

    print
    analysis_name, control_name = rx_control_prefixes
    print "Uploading and converting results for scenario '%s' and control '%s'" % (analysis_name, control_name)
    print

    # define paths to all input files, delete database if it already exists
    control_SS_table = working_path + control_name + '-SS.csv'
    rx_SS_table = working_path + analysis_name + '-SS.csv'
    control_carbon = working_path + control_name + '-Carbon.csv'
    rx_carbon = working_path + analysis_name + '-Carbon.csv'

    site_data = working_path + site_file

    if filter_string:
        print "Filtering raw results based on the following SQL statement:"
        print filter_string
        print
        analysis_name += '_Filtered'

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H.%M")
    archive_path = working_path + 'results/' + timestamp + '-' + analysis_name + '/'
    print "Analysis contained in %s" % archive_path
    print
    if not os.path.exists(archive_path):
        os.mkdir(archive_path)

    db_fpath = archive_path + db_file
    if os.path.exists(db_fpath):
        os.remove(db_fpath)

    # load FVS results to working SQLite database
    type_assignment_bulk_convert_upload(control_SS_table, db_fpath, 'Control_StandStock')
    type_assignment_bulk_convert_upload(rx_SS_table, db_fpath, 'RX_StandStock')
    type_assignment_bulk_convert_upload(control_carbon, db_fpath, 'Control_Carbon', conversion_factor=st_acre_to_Mg_ha)
    type_assignment_bulk_convert_upload(rx_carbon, db_fpath, 'RX_Carbon', conversion_factor=st_acre_to_Mg_ha)
    type_assignment_bulk_convert_upload(site_data, db_fpath, 'site')

    # establish a connection to the working database
    con = sqlite3.connect(db_fpath)
    with con:
        cur = con.cursor()

        if filter_string:
            # log the filter string for reference
            metadata_fpath = archive_path + analysis_name + '-Filter_string.txt'
            m = open(metadata_fpath, "w")
            m.write(filter_string)
            m.close()

            # apply the filter to each table
            for table in ('Control_StandStock', 'RX_StandStock', 'Control_Carbon', 'RX_Carbon', 'site'):
                cur.execute("ALTER TABLE %s RENAME TO temp" % table)
                cur.execute(""" CREATE TABLE %s AS SELECT * FROM temp %s """ % (table, filter_string))
                cur.execute("DROP TABLE temp")

        # create new columns in Stand & Stock results with metric units
        sql_append_unit_conversion(cur, 'Control_StandStock', 'LiveBA', 'LiveBA_metric', ft2_acre_to_m2_ha)
        sql_append_unit_conversion(cur, 'RX_StandStock', 'LiveBA', 'LiveBA_metric', ft2_acre_to_m2_ha)
        sql_append_unit_conversion(cur, 'Control_StandStock', 'LiveTPA', 'LiveTPHA', _acre_to__ha)
        sql_append_unit_conversion(cur, 'RX_StandStock', 'LiveTPA', 'LiveTPHA', _acre_to__ha)

        # create a table of RX simulation starting and ending years for all stands
        cur.execute(""" CREATE TABLE RX_StartEndYear AS
                        SELECT StandID, MIN(Year) as StartYear, MAX(Year) as EndYear
                        FROM RX_StandStock
                        GROUP BY StandID """)

        # create a table of initial species diversity within each stand
        cur.execute(""" CREATE TABLE SpeciesDiversity AS
                        SELECT StandID, COUNT(DISTINCT Species) AS SpeciesCount
                        FROM Control_StandStock
                        WHERE Species!='ALL'
                        GROUP BY StandID """)

        # create a table of RX simulation initial mortality
        cur.execute(""" CREATE TABLE RX_StandMortality AS
                        SELECT ss.StandID, ss.Year, (ss.MortBA / (ss.LiveBA + ss.MortBA)) AS InitialMortality
                        FROM RX_StandStock ss
                        JOIN RX_StartEndYear sey ON ss.StandID=sey.StandID
                        WHERE ss.Year=sey.StartYear AND ss.DiamClass='All' AND ss.Species='ALL' """)

        # create tables of stand BA by species over time for both Control and RX
        # pivot/transpose from http://sqlite.1065341.n5.nabble.com/Transpose-selected-rows-into-columns-td81378.html
        cur.execute(""" CREATE TABLE Control_SpeciesBA AS
                        SELECT StandID, Year,
                            MAX(CASE Species WHEN 'AF' THEN LiveBA_metric ELSE 0.0 END) AF_BA,
                            MAX(CASE Species WHEN 'AS' THEN LiveBA_metric ELSE 0.0 END) AS_BA,
                            MAX(CASE Species WHEN 'ES' THEN LiveBA_metric ELSE 0.0 END) ES_BA,
                            MAX(CASE Species WHEN 'LP' THEN LiveBA_metric ELSE 0.0 END) LP_BA,
                            MAX(CASE Species WHEN 'OH' THEN LiveBA_metric ELSE 0.0 END) OH_BA,
                            MAX(CASE Species WHEN 'ALL' THEN LiveBA_metric ELSE 0.0 END) Tot_BA
                        FROM Control_StandStock
                        GROUP BY StandID, Year """)
        cur.execute(""" CREATE TABLE RX_SpeciesBA AS
                        SELECT StandID, Year,
                            MAX(CASE Species WHEN 'AF' THEN LiveBA_metric ELSE 0.0 END) AF_BA,
                            MAX(CASE Species WHEN 'AS' THEN LiveBA_metric ELSE 0.0 END) AS_BA,
                            MAX(CASE Species WHEN 'ES' THEN LiveBA_metric ELSE 0.0 END) ES_BA,
                            MAX(CASE Species WHEN 'LP' THEN LiveBA_metric ELSE 0.0 END) LP_BA,
                            MAX(CASE Species WHEN 'OH' THEN LiveBA_metric ELSE 0.0 END) OH_BA,
                            MAX(CASE Species WHEN 'ALL' THEN LiveBA_metric ELSE 0.0 END) Tot_BA
                        FROM RX_StandStock
                        GROUP BY StandID, Year """)

        # verify that transpose operations didn't miss anything
        cur.execute("ALTER TABLE Control_SpeciesBA ADD COLUMN Tot_BA_check REAL")
        cur.execute("UPDATE Control_SpeciesBA SET Tot_BA_check=(AF_BA + AS_BA + ES_BA + LP_BA + OH_BA - Tot_BA)/Tot_BA")
        cur.execute("SELECT StandID, AVG(Tot_BA_check) FROM Control_SpeciesBA WHERE Tot_BA_check>0 GROUP BY StandID")
        print "###############################################################################################"
        fetch_print(cur, "WARNING- the stands have Control species fraction summation errors as follows:")

        cur.execute("ALTER TABLE RX_SpeciesBA ADD COLUMN Tot_BA_check REAL")
        cur.execute("UPDATE RX_SpeciesBA SET Tot_BA_check=(AF_BA + AS_BA + ES_BA + LP_BA + OH_BA - Tot_BA)/Tot_BA")
        cur.execute("SELECT StandID, AVG(Tot_BA_check) FROM RX_SpeciesBA WHERE Tot_BA_check>0 GROUP BY StandID")
        print "###############################################################################################"
        fetch_print(cur, "WARNING- the stands have RX species fraction summation errors as follows:")
        print "###############################################################################################"
        print

        # create tables of stand composition over time for both Control and RX
        cur.execute(""" CREATE TABLE Control_StandComposition AS
                        SELECT StandID, Year,
                            AF_BA/Tot_BA AS AF_share,
                            AS_BA/Tot_BA AS AS_share,
                            ES_BA/Tot_BA AS ES_share,
                            LP_BA/Tot_BA AS LP_share,
                            OH_BA/Tot_BA AS OH_share
                        FROM Control_SpeciesBA """)
        cur.execute(""" CREATE TABLE RX_StandComposition AS
                        SELECT StandID, Year,
                            AF_BA/Tot_BA AS AF_share,
                            AS_BA/Tot_BA AS AS_share,
                            ES_BA/Tot_BA AS ES_share,
                            LP_BA/Tot_BA AS LP_share,
                            OH_BA/Tot_BA AS OH_share
                        FROM RX_SpeciesBA """)

        # create tables of total live trees per hectare (TPHA) over time for both Control and RX
        cur.execute(""" CREATE TABLE Control_TPHA AS
                        SELECT StandID, Year,
                            MAX(CASE WHEN DiamClass=2 THEN LiveTPHA ELSE 0.0 END) AS 'd2',
                            MAX(CASE WHEN DiamClass=4 THEN LiveTPHA ELSE 0.0 END) AS 'd4',
                            MAX(CASE WHEN DiamClass=6 THEN LiveTPHA ELSE 0.0 END) AS 'd6',
                            MAX(CASE WHEN DiamClass=8 THEN LiveTPHA ELSE 0.0 END) AS 'd8',
                            MAX(CASE WHEN DiamClass=10 THEN LiveTPHA ELSE 0.0 END) AS 'd10',
                            MAX(CASE WHEN DiamClass=12 THEN LiveTPHA ELSE 0.0 END) AS 'd12',
                            MAX(CASE WHEN DiamClass=14 THEN LiveTPHA ELSE 0.0 END) AS 'd14',
                            MAX(CASE WHEN DiamClass=16 THEN LiveTPHA ELSE 0.0 END) AS 'd16',
                            MAX(CASE WHEN DiamClass=18 THEN LiveTPHA ELSE 0.0 END) AS 'd18',
                            MAX(CASE WHEN DiamClass=20 THEN LiveTPHA ELSE 0.0 END) AS 'd20',
                            MAX(CASE WHEN DiamClass=22 THEN LiveTPHA ELSE 0.0 END) AS 'd22',
                            MAX(CASE WHEN DiamClass=24 THEN LiveTPHA ELSE 0.0 END) AS 'd24',
                            MAX(CASE WHEN DiamClass=26 THEN LiveTPHA ELSE 0.0 END) AS 'd26',
                            MAX(CASE WHEN DiamClass=28 THEN LiveTPHA ELSE 0.0 END) AS 'd28',
                            MAX(CASE WHEN DiamClass=30 THEN LiveTPHA ELSE 0.0 END) AS 'd30',
                            MAX(CASE WHEN DiamClass='All' THEN LiveTPHA ELSE 0.0 END) AS 'Tot_TPHA'
                        FROM Control_StandStock
                        WHERE Species="ALL"
                        GROUP BY StandID, Year """)
        cur.execute("ALTER TABLE Control_TPHA ADD COLUMN small_TPHA REAL")
        cur.execute("UPDATE Control_TPHA SET small_TPHA=(d2 + d4 + d6 + d8)")
        cur.execute("ALTER TABLE Control_TPHA ADD COLUMN big_TPHA REAL")
        cur.execute("UPDATE Control_TPHA SET big_TPHA=(d10 + d12 + d14 + d16 + d18 + d20 + d22 + d24 + d26 + d28 + d30)")
        cur.execute("ALTER TABLE Control_TPHA ADD COLUMN small_big_ratio REAL")
        cur.execute("UPDATE Control_TPHA SET small_big_ratio=small_TPHA/big_TPHA")

        cur.execute(""" CREATE TABLE RX_TPHA AS
                        SELECT StandID, Year,
                            MAX(CASE WHEN DiamClass=2 THEN LiveTPHA ELSE 0.0 END) AS 'd2',
                            MAX(CASE WHEN DiamClass=4 THEN LiveTPHA ELSE 0.0 END) AS 'd4',
                            MAX(CASE WHEN DiamClass=6 THEN LiveTPHA ELSE 0.0 END) AS 'd6',
                            MAX(CASE WHEN DiamClass=8 THEN LiveTPHA ELSE 0.0 END) AS 'd8',
                            MAX(CASE WHEN DiamClass=10 THEN LiveTPHA ELSE 0.0 END) AS 'd10',
                            MAX(CASE WHEN DiamClass=12 THEN LiveTPHA ELSE 0.0 END) AS 'd12',
                            MAX(CASE WHEN DiamClass=14 THEN LiveTPHA ELSE 0.0 END) AS 'd14',
                            MAX(CASE WHEN DiamClass=16 THEN LiveTPHA ELSE 0.0 END) AS 'd16',
                            MAX(CASE WHEN DiamClass=18 THEN LiveTPHA ELSE 0.0 END) AS 'd18',
                            MAX(CASE WHEN DiamClass=20 THEN LiveTPHA ELSE 0.0 END) AS 'd20',
                            MAX(CASE WHEN DiamClass=22 THEN LiveTPHA ELSE 0.0 END) AS 'd22',
                            MAX(CASE WHEN DiamClass=24 THEN LiveTPHA ELSE 0.0 END) AS 'd24',
                            MAX(CASE WHEN DiamClass=26 THEN LiveTPHA ELSE 0.0 END) AS 'd26',
                            MAX(CASE WHEN DiamClass=28 THEN LiveTPHA ELSE 0.0 END) AS 'd28',
                            MAX(CASE WHEN DiamClass=30 THEN LiveTPHA ELSE 0.0 END) AS 'd30',
                            MAX(CASE WHEN DiamClass='All' THEN LiveTPHA ELSE 0.0 END) AS 'Tot_TPHA'
                        FROM RX_StandStock
                        WHERE Species="ALL"
                        GROUP BY StandID, Year """)
        cur.execute("ALTER TABLE RX_TPHA ADD COLUMN small_TPHA REAL")
        cur.execute("UPDATE RX_TPHA SET small_TPHA=(d2 + d4 + d6 + d8)")
        cur.execute("ALTER TABLE RX_TPHA ADD COLUMN big_TPHA REAL")
        cur.execute("UPDATE RX_TPHA SET big_TPHA=(d10 + d12 + d14 + d16 + d18 + d20 + d22 + d24 + d26 + d28 + d30)")
        cur.execute("ALTER TABLE RX_TPHA ADD COLUMN small_big_ratio REAL")
        cur.execute("UPDATE RX_TPHA SET small_big_ratio=small_TPHA/big_TPHA")

        # create tables of stand density by species over time for both Control and RX
        cur.execute(""" CREATE TABLE Control_SpeciesTPHA AS
                    SELECT StandID, Year,
                        MAX(CASE WHEN Species='AF' THEN LiveTPHA ELSE 0.0 END) AS 'AF_TPHA',
                        MAX(CASE WHEN Species='AS' THEN LiveTPHA ELSE 0.0 END) AS 'AS_TPHA',
                        MAX(CASE WHEN Species='ES' THEN LiveTPHA ELSE 0.0 END) AS 'ES_TPHA',
                        MAX(CASE WHEN Species='LP' THEN LiveTPHA ELSE 0.0 END) AS 'LP_TPHA',
                        MAX(CASE WHEN Species='OH' THEN LiveTPHA ELSE 0.0 END) AS 'OH_TPHA'
                    FROM Control_StandStock
                    WHERE DiamClass='All'
                    GROUP BY StandID, Year """)
        cur.execute(""" CREATE TABLE RX_SpeciesTPHA AS
                    SELECT StandID, Year,
                        MAX(CASE WHEN Species='AF' THEN LiveTPHA ELSE 0.0 END) AS 'AF_TPHA',
                        MAX(CASE WHEN Species='AS' THEN LiveTPHA ELSE 0.0 END) AS 'AS_TPHA',
                        MAX(CASE WHEN Species='ES' THEN LiveTPHA ELSE 0.0 END) AS 'ES_TPHA',
                        MAX(CASE WHEN Species='LP' THEN LiveTPHA ELSE 0.0 END) AS 'LP_TPHA',
                        MAX(CASE WHEN Species='OH' THEN LiveTPHA ELSE 0.0 END) AS 'OH_TPHA'
                    FROM RX_StandStock
                    WHERE DiamClass='All'
                    GROUP BY StandID, Year """)

        # create tables of carbon pool density over time for both Control and RX, and save to nested dictionary
        cur.execute(""" CREATE TABLE Carbon AS
                        SELECT c.StandID, c.Year,
                                c.Aboveground_Total_Live AS Aboveground_Total_Live_Control,
                                c.Belowground_Live AS Belowground_Live_Control,
                                c.Belowground_Dead AS Belowground_Dead_Control,
                                c.Standing_Dead AS Standing_Dead_Control,
                                c.Forest_Down_Dead_Wood AS Forest_Down_Dead_Wood_Control,
                                c.Forest_Floor AS Forest_Floor_Control,
                                c.Forest_Shrub_Herb AS Forest_Shrub_Herb_Control,
                                c.Total_Stand_Carbon AS Total_Stand_Carbon_Control,
                                c.Total_Removed_Carbon AS Total_Removed_Carbon_Control,
                            rx.Aboveground_Total_Live AS Aboveground_Total_Live_RX,
                                rx.Belowground_Live AS Belowground_Live_RX,
                                rx.Belowground_Dead AS Belowground_Dead_RX,
                                rx.Standing_Dead AS Standing_Dead_RX,
                                rx.Forest_Down_Dead_Wood AS Forest_Down_Dead_Wood_RX,
                                rx.Forest_Floor AS Forest_Floor_RX,
                                rx.Forest_Shrub_Herb AS Forest_Shrub_Herb_RX,
                                rx.Total_Stand_Carbon AS Total_Stand_Carbon_RX,
                                rx.Total_Removed_Carbon AS Total_Removed_Carbon_RX
                        FROM Control_Carbon c
                        JOIN RX_Carbon rx ON c.StandID=rx.StandID AND c.Year=rx.Year """)

        stand_C = sql_to_nested_dictionaries(cur, 'Carbon', 'StandID')

        # compute the integrated carbon deficit for each stand, and add to dictionary structure
        for stand_ID in stand_C:
            integrated_deficit, running_deficit = deficit(stand_C[stand_ID]['Year'],
                                                  stand_C[stand_ID]['Total_Stand_Carbon_Control'],
                                                  stand_C[stand_ID]['Total_Stand_Carbon_RX'])
            stand_C[stand_ID]['Integrated_deficit'] = integrated_deficit
            stand_C[stand_ID]['Running_deficit'] = running_deficit

    return archive_path, stand_C


def summarize_data(db_fpath):
    """ Summarizes FVS data within the SQLite database for quality control purposes, printing results to the screen for
    manual inspection.

    :param db_fpath: full path to SQLite database file containing FVS data (str)
    :return:
    """

    # establish a connection to the working database
    con = sqlite3.connect(db_fpath)
    with con:
        cur = con.cursor()

        # count the number of stands included in the results
        cur.execute("SELECT COUNT(DISTINCT StandID) FROM Control_StandStock")
        print "The Control data contains records for %i distinct stands" % cur.fetchall()[0][0]
        cur.execute("SELECT COUNT(DISTINCT StandID) FROM RX_StandStock")
        print "The RX data contains records for %i distinct stands" % cur.fetchall()[0][0]
        print

        # count number of time points included for each individual stand
        cur.execute("SELECT StandID, COUNT(DISTINCT Year) FROM Control_StandStock GROUP BY StandID ORDER BY StandID")
        fetch_print(cur, "There are the following numbers of time points for each stand Control:")

        cur.execute("SELECT StandID, COUNT(DISTINCT Year) FROM RX_StandStock GROUP BY StandID ORDER BY StandID")
        fetch_print(cur, "There are the following numbers of time points for each stand RX:")

        # determine the unique species included in the results
        cur.execute("SELECT DISTINCT Species FROM Control_StandStock WHERE Species!='ALL' ")
        fetch_print(cur, "The Control data includes the following species:")
        cur.execute(""" SELECT StandID, COUNT(DISTINCT Species)
                        FROM Control_StandStock
                        WHERE Species!='ALL'
                        GROUP BY StandID
                        ORDER BY StandID """)
        fetch_print(cur, "The number of species names present in each stand Control is as follows:")

        cur.execute("SELECT DISTINCT Species FROM RX_StandStock WHERE Species!='ALL' ")
        fetch_print(cur, "The RX data includes the following species:")
        cur.execute("SELECT * FROM SpeciesDiversity ORDER BY StandID")
        fetch_print(cur, "The number of species names present in each stand RX is as follows:")

        # display the starting and ending year for all of the RX simulations
        cur.execute("SELECT * FROM RX_StartEndYear ORDER BY StandID")
        fetch_print(cur, "Here are the RX simulation starting and ending years for each stand:")

        # display the initial mortality of each stand
        cur.execute("SELECT * FROM RX_StandMortality ORDER BY StandID")
        fetch_print(cur, "Here is the fraction of initial mortality of each stand on a BA basis:")

        # display the initial BA of each stand for both the Control and RX
        cur.execute(""" SELECT b.StandID, b.Tot_BA
                        FROM Control_SpeciesBA b
                        JOIN RX_StartEndYear y ON b.StandID=y.StandID AND b.Year=y.StartYear
                        ORDER BY b.StandID """)
        fetch_print(cur, "Here is the initial total live BA for each stand Control:")

        cur.execute(""" SELECT b.StandID, b.Tot_BA
                        FROM RX_SpeciesBA b
                        JOIN RX_StartEndYear y ON b.StandID=y.StandID AND b.Year=y.StartYear
                        ORDER BY b.StandID """)
        fetch_print(cur, "Here is the initial total live BA for each stand RX (verify same as Control):")

        # determine stands which become dominated by aspen
        cur.execute(""" SELECT c.StandID, c.AS_share
                        FROM Control_StandComposition c
                        JOIN RX_StartEndYear sey ON c.StandID=sey.StandID AND c.Year=sey.EndYear
                        WHERE AS_share>0.0001
                        ORDER BY c.StandID """)
        fetch_print(cur, "Here are the Control stands that became partially or completely dominated by ASPEN:")

        cur.execute(""" SELECT c.StandID, c.AS_share
                        FROM RX_StandComposition c
                        JOIN RX_StartEndYear sey ON c.StandID=sey.StandID AND c.Year=sey.EndYear
                        WHERE AS_share>0.0001
                        ORDER BY C.StandID """)
        fetch_print(cur, "Here are the RX stands that became partially or completely dominated by ASPEN:")


def plot_deficit_detail(stand_C_dictionary, archive_path):
    """ Creates an multi-panel plot illustrating the carbon dynamics of the stands with the smallest and largest
    integrated carbon deficits of harvest, showing a) aboveground live C vs. time and b) total ecosystem C vs.
    time for both the Control and RX, as well as c) the normalized carbon deficit vs. time.

    :param stand_C_dictionary: nested dictionary structure containing stand carbon density data (dict of float)
    :param archive_path: path where database file and all results files & figures will be stored (str)
    :return:
    """

    print "Creating plots to illustrate carbon deficits of representative stands..."

    # determine the stands with smallest and largest total integrated ecosystem carbon deficit
    deficit_list = []
    for key in stand_C_dictionary.keys():
        deficit_list.append((key, stand_C_dictionary[key]['Integrated_deficit']))

    deficit_list.sort(key=lambda x: x[1])
    min_deficit_stand = deficit_list[0][0]
    max_deficit_stand = deficit_list[-1][0]

    detail_stands = [min_deficit_stand, max_deficit_stand]
    detail_colors = ['b', 'r']

    # create an aboveground live carbon plot (min/max stands only)
    ax1 = plt.subplot2grid((2, 2), (0, 0))
    for i, standID in enumerate(detail_stands):
        ax1.plot(stand_C_dictionary[standID]['Year'],
                 stand_C_dictionary[standID]['Aboveground_Total_Live_Control'],
                marker='None', linestyle='--', linewidth=2, color=detail_colors[i])
        ax1.plot(stand_C_dictionary[standID]['Year'],
                 stand_C_dictionary[standID]['Aboveground_Total_Live_RX'],
                 marker='None', linestyle='-', linewidth=2, color=detail_colors[i])
        ax1.fill_between(stand_C_dictionary[standID]['Year'],
                         stand_C_dictionary[standID]['Aboveground_Total_Live_Control'],
                         stand_C_dictionary[standID]['Aboveground_Total_Live_RX'],
                         color=detail_colors[i], alpha='0.3')

    ax1.set_xlabel('Year')
    ax1.set_ylabel('Aboveground Live Carbon\n(Mg C $\mathregular{ha^{-1}}$)')

    # create an absolute ecosystem carbon plot (min/max stands only)
    ax2 = plt.subplot2grid((2, 2), (0, 1))
    for i, standID in enumerate(detail_stands):
        ax2.plot(stand_C_dictionary[standID]['Year'],
                 stand_C_dictionary[standID]['Total_Stand_Carbon_Control'],
                 marker='None', linestyle='--', linewidth=2, color=detail_colors[i])
        ax2.plot(stand_C_dictionary[standID]['Year'],
                 stand_C_dictionary[standID]['Total_Stand_Carbon_RX'],
                 marker='None', linestyle='-', linewidth=2, color=detail_colors[i])
        ax2.fill_between(stand_C_dictionary[standID]['Year'],
                         stand_C_dictionary[standID]['Total_Stand_Carbon_Control'],
                         stand_C_dictionary[standID]['Total_Stand_Carbon_RX'],
                         color=detail_colors[i], alpha='0.3')

    ax2.set_xlabel('Year')
    ax2.set_ylabel('Total Ecosystem Carbon\n(Mg C $\mathregular{ha^{-1}}$)')

    # create a normalized carbon deficit plot (min/max stands only)
    ax3 = plt.subplot2grid((2, 1), (1, 0), colspan=2)
    for i, standID in enumerate(detail_stands):
        detail_label = '%s deficit = %.0f Mg C y' % (standID.split('_')[-1],
                                                                stand_C_dictionary[standID]['Integrated_deficit'])
        cumulative_harvest = np.cumsum(stand_C_dictionary[standID]['Total_Removed_Carbon_RX'])
        normalized_deficit = stand_C_dictionary[standID]['Running_deficit'] / cumulative_harvest

        ax3.plot(stand_C_dictionary[standID]['Year'], normalized_deficit,
                 marker='None', linestyle='-', linewidth=2, color=detail_colors[i], label=detail_label)

    ax3.axhline(0, color='gray', linestyle='--', zorder=-1)
    ax3.axhline(1, color='gray', linestyle='--', zorder=-1)
    ax3.set_xlabel('Year')
    ax3.set_ylabel('Normalized deficit\n(C deficit : C removed)')
    ax3.legend(loc=10, bbox_to_anchor=[0.5, 1.04], prop={'size': 10}, shadow=True, fancybox=True)

    matplotlib.rcParams.update({'font.size': 11})
    plt.suptitle('Carbon deficit of harvest- min & max deficit stands', fontsize=13)
    plt.tight_layout()
    plt.subplots_adjust(top=0.9)
    plt.subplots_adjust(bottom=0.1)

    scenario = archive_path.split('-')[-1].split('/')[0]
    plt.savefig(archive_path + scenario + '-Normalized_ecosystem_deficit_detail.pdf')
    plt.close()
    print
    print


def plot_all_deficits(stand_C_dictionary, db_fpath, archive_path):
    """ Creates an multi-panel plot illustrating the carbon deficits of harvest for all stands, showing a) aboveground
    live C vs. time and b) total ecosystem C vs. time for both the Control and RX, as well as c) the normalized carbon
    deficit vs. time.

    :param stand_C_dictionary: nested dictionary structure containing stand carbon density data (dict of float)
    :param db_fpath: full path to SQLite database file containing FVS data (str)
    :param archive_path: path where database file and all results files & figures will be stored (str)
    :return:
    """

    print "Creating plots to illustrate carbon deficits for all stands..."
    deficit_set = []

    # plot control & RX total aboveground live carbon trajectories for all stands
    ax1 = plt.subplot2grid((2, 2), (0, 0))
    for i, standID in enumerate(stand_C_dictionary.keys()):
        if i == 0:
            ax1.plot(stand_C_dictionary[standID]['Year'],
                     stand_C_dictionary[standID]['Aboveground_Total_Live_Control'],
                     label="Control", marker='None', linestyle='-', linewidth=1, color='r')
            ax1.plot(stand_C_dictionary[standID]['Year'],
                     stand_C_dictionary[standID]['Aboveground_Total_Live_RX'],
                     label="Harvest & regen.", marker='None', linestyle='-', linewidth=1, color='g')
        else:
            ax1.plot(stand_C_dictionary[standID]['Year'],
                     stand_C_dictionary[standID]['Aboveground_Total_Live_Control'],
                     marker='None', linestyle='-', linewidth=1, color='r')
            ax1.plot(stand_C_dictionary[standID]['Year'],
                     stand_C_dictionary[standID]['Aboveground_Total_Live_RX'],
                     marker='None', linestyle='-', linewidth=1, color='g')

    ax1.set_ylabel('Aboveground Live Carbon\n(Mg C $\mathregular{ha^{-1}}$)')
    ax1.legend(loc=4, prop={'size': 9})

    # plot control & RX total ecosystem carbon trajectories for all stands
    ax2 = plt.subplot2grid((2, 2), (0, 1))
    for i, standID in enumerate(stand_C_dictionary.keys()):
        if i == 0:
            ax2.plot(stand_C_dictionary[standID]['Year'],
                     stand_C_dictionary[standID]['Total_Stand_Carbon_Control'],
                     label="Control", marker='None', linestyle='-', linewidth=1, color='r')
            ax2.plot(stand_C_dictionary[standID]['Year'],
                     stand_C_dictionary[standID]['Total_Stand_Carbon_RX'],
                     label="Harvest & regen.", marker='None', linestyle='-', linewidth=1, color='g')
        else:
            ax2.plot(stand_C_dictionary[standID]['Year'],
                     stand_C_dictionary[standID]['Total_Stand_Carbon_Control'],
                     marker='None', linestyle='-', linewidth=1, color='r')
            ax2.plot(stand_C_dictionary[standID]['Year'],
                     stand_C_dictionary[standID]['Total_Stand_Carbon_RX'],
                     marker='None', linestyle='-', linewidth=1, color='g')

    ax2.set_ylabel('Total Ecosystem Carbon\n(Mg C $\mathregular{ha^{-1}}$)')
    ax2.legend(loc=4, prop={'size': 9})

    # plot and store normalized ecosystem carbon deficits for all stands
    ax3 = plt.subplot2grid((2, 1), (1, 0), colspan=2)
    for i, standID in enumerate(stand_C_dictionary.keys()):
        cumulative_harvest = np.cumsum(stand_C_dictionary[standID]['Total_Removed_Carbon_RX'])
        normalized_deficit = stand_C_dictionary[standID]['Running_deficit'] / cumulative_harvest
        stand_C_dictionary[standID]['Normalized_deficit'] = normalized_deficit

        zorder = 0
        if normalized_deficit[-1] >= 1.0:
            color = 'y'
        elif normalized_deficit[-1] >= 0.0:
            color = 'c'
            zorder += 1
        else:
            color = 'm'
            zorder += 2

        ax3.plot(stand_C_dictionary[standID]['Year'], normalized_deficit,
                 marker='None', linestyle='-', linewidth=1, color=color, zorder=zorder)
        deficit_set.append(normalized_deficit)

    # add labels, thresholds, and legend
    ax3.axhline(0, color='k', linestyle='--', zorder=-1)
    ax3.axhline(1, color='k', linestyle='--', zorder=-1)

    ax3.plot(2100, 0, marker='None', linestyle='-', linewidth=5,
             label='stands with persistent deficit in excess of harvested C', color='y')
    ax3.plot(2100, 0, marker='None', linestyle='-', linewidth=5,
             label='stands which partially recover their deficit', color='c')
    ax3.plot(2100, 0, marker='None', linestyle='-', linewidth=5,
             label='stands which eventually out-grow their controls', color='m')
    ax3.legend(loc=3, prop={'size': 9})

    ax3.set_xlabel('Year')
    ax3.set_ylabel('Normalized deficit\n(C deficit : C removed)')

    matplotlib.rcParams.update({'font.size': 11})
    plt.suptitle('Carbon deficit of harvest- all stands', fontsize=13)
    plt.tight_layout()
    plt.subplots_adjust(top=0.9)
    plt.subplots_adjust(bottom=0.1)

    scenario = archive_path.split('-')[-1].split('/')[0]
    plt.savefig(archive_path + scenario + '-Normalized_ecosystem_C_deficit_range.pdf')
    plt.close()

    # load deficit results to database
    deficit_upload = [['StandID', 'Integrated_deficit', 'End_normalized_deficit'],
                      ['TEXT', 'REAL', 'REAL']]
    for key in stand_C_dictionary.keys():
        deficit_upload.append([str(key), stand_C_dictionary[key]['Integrated_deficit'],
                               stand_C_dictionary[key]['Normalized_deficit'][-1]])

    list_to_sql(deficit_upload, db_fpath, 'Deficit')

    # calculate average & SD for normalized deficit range, add to plot, and write to file

    print
    print


def plot_stand_dynamics(stand_C_dictionary, db_fpath, archive_path):
    """ Plots basal area and tree density by species, and the carbon density in various forest carbon pools, for both
    the Control and Harvested scenarios of individual stands.  Grey horizontal lines illustrate the stand initial
    condition, for reference.

    :param stand_C_dictionary: nested dictionary structure containing stand carbon density data (dict of float)
    :param db_fpath: full path to SQLite database file containing FVS data (str)
    :param archive_path: path where database file and all results files & figures will be stored (str)
    :return:
    """

    print "Creating plots to illustrate Control and RX stand growth dynamics..."

    # determine the stands with smallest, median, and largest total integrated ecosystem carbon deficit
    deficit_list = []
    for key in stand_C_dictionary.keys():
        deficit_list.append((key, stand_C_dictionary[key]['Integrated_deficit']))

    deficit_list.sort(key=lambda x: x[1])
    min_deficit_stand = deficit_list[0][0]
    med_deficit_stand = deficit_list[len(deficit_list)/2][0]
    max_deficit_stand = deficit_list[-1][0]

    detail_stands = [min_deficit_stand, med_deficit_stand, max_deficit_stand]
    descriptors = ['minimum', 'median', 'maximum']

    # establish a connection to the working database
    con = sqlite3.connect(db_fpath)
    with con:
        cur = con.cursor()

        for i, standID in enumerate(stand_C_dictionary.keys()):
            print i, standID

            f, axes = plt.subplots(3, 2, sharex='col', sharey='row')
            for j, scenario in enumerate(['Control', 'RX']):

                # query database for data on BA and TPHA by species vs. time
                cur.execute("SELECT Year, AF_BA, AS_BA, ES_BA, LP_BA, OH_BA FROM %s_SpeciesBA WHERE StandID='%s'"
                            % (scenario, standID))
                BA_data = cur.fetchall()
                Year, AF_BA, AS_BA, ES_BA, LP_BA, OH_BA = zip(*BA_data)

                cur.execute("SELECT Year, AF_TPHA, AS_TPHA, ES_TPHA, LP_TPHA, OH_TPHA FROM %s_SpeciesTPHA WHERE StandID='%s'"
                            % (scenario, standID))
                BA_data = cur.fetchall()
                Year, AF_TPHA, AS_TPHA, ES_TPHA, LP_TPHA, OH_TPHA = zip(*BA_data)

                # create panels showing BA and TPHA by species vs. time (only including species present in data)
                species_BAs = [AF_BA, AS_BA, ES_BA, LP_BA, OH_BA]
                species_TPHAs = [AF_TPHA, AS_TPHA, ES_TPHA, LP_TPHA, OH_TPHA]
                species_list = ['subalpine fir\n(Abies lasiocarpa)',
                                'quaking aspen\n(Populus tremuloides)',
                                'Engelmann spruce\n(Picea engelmannii)',
                                'lodgepole pine\n(Pinus contorta)',
                                'other hardwoods']
                colors = ['b', 'g', 'r', 'c', 'm', 'y', 'k']
                axis_line = []
                for k in range(len(Year)):
                    axis_line.append(0)
                bottom_BA_boundary = np.array(axis_line)
                bottom_TPHA_boundary = np.array(axis_line)

                for e in range(len(species_BAs)):
                    BA_series = np.array(species_BAs[e])
                    TPHA_series = np.array(species_TPHAs[e])
                    if np.sum(TPHA_series):

                        # plot BA area plot
                        top_BA_boundary = bottom_BA_boundary + BA_series
                        axes[0, j].fill_between(Year, bottom_BA_boundary, top_BA_boundary,
                                         facecolor=colors[e], edgecolor='none')
                        axes[0, j].plot(2020, 0, label=species_list[e], marker='None', color=colors[e], linewidth=5)
                        bottom_BA_boundary = top_BA_boundary

                        # plot TPHA area plot
                        top_TPHA_boundary = bottom_TPHA_boundary + TPHA_series
                        axes[1, j].fill_between(Year, bottom_TPHA_boundary, top_TPHA_boundary,
                                         facecolor=colors[e], edgecolor='none')
                        axes[1, j].plot(2020, 0, label=species_list[e], marker='None', color=colors[e], linewidth=5)
                        bottom_TPHA_boundary = top_TPHA_boundary

                # mark initial starting points
                axes[0, 0].axhline(y=bottom_BA_boundary[0], color='grey', lw=0.4)
                axes[0, 1].axhline(y=bottom_BA_boundary[0], color='grey', lw=0.4)
                axes[1, 0].axhline(y=bottom_TPHA_boundary[0], color='grey', lw=0.4)
                axes[1, 1].axhline(y=bottom_TPHA_boundary[0], color='grey', lw=0.4)

                # create carbon pool detail panels
                axis_line = []
                for k in range(len(stand_C_dictionary[standID]['Belowground_Dead_%s' % scenario])):
                    axis_line.append(0)

                Year = stand_C_dictionary[standID]['Year']

                Belowground_Live = np.array(stand_C_dictionary[standID]['Belowground_Live_%s' % scenario]) * -1
                Belowground_Dead = Belowground_Live + \
                                   np.array(stand_C_dictionary[standID]['Belowground_Dead_%s' % scenario]) * -1

                Surface = np.array(stand_C_dictionary[standID]['Forest_Down_Dead_Wood_%s' % scenario]) + \
                          np.array(stand_C_dictionary[standID]['Forest_Floor_%s' % scenario]) + \
                          np.array(stand_C_dictionary[standID]['Forest_Shrub_Herb_%s' % scenario])
                Standing_Dead = Surface + np.array(stand_C_dictionary[standID]['Standing_Dead_%s' % scenario])
                Aboveground_Live = Standing_Dead + \
                                   np.array(stand_C_dictionary[standID]['Aboveground_Total_Live_%s' % scenario])

                axes[2, j].fill_between(Year,
                                 axis_line,
                                 Belowground_Live,
                                 facecolor='greenyellow', edgecolor='none')
                axes[2, j].plot(2100, 0,
                                label='Belowground_Live', marker='None', linestyle='-', linewidth=5, color='greenyellow')

                axes[2, j].fill_between(Year,
                                 Belowground_Live,
                                 Belowground_Dead,
                                 facecolor='gold', edgecolor='none')
                axes[2, j].plot(2100, 0,
                         label='Belowground_Dead', marker='None', linestyle='-', linewidth=5, color='gold')

                axes[2, j].fill_between(Year,
                                 axis_line,
                                 Surface,
                                 facecolor='saddlebrown', edgecolor='none')
                axes[2, j].plot(2100, 0,
                         label='Surface', marker='None', linestyle='-', linewidth=5, color='saddlebrown')

                axes[2, j].fill_between(Year,
                                 Surface,
                                 Standing_Dead,
                                 facecolor='darkorange', edgecolor='none')
                axes[2, j].plot(2100, 0,
                         label='Standing_Dead', marker='None', linestyle='-', linewidth=5, color='darkorange')

                axes[2, j].fill_between(Year,
                                 Standing_Dead,
                                 Aboveground_Live,
                                 facecolor='green', edgecolor='none')
                axes[2, j].plot(2100, 0,
                         label='Aboveground_Live', marker='None', linestyle='-', linewidth=5, color='green')

                # mark initial starting points
                axes[2, 0].axhline(y=Aboveground_Live[0], color='grey', lw=0.4)
                axes[2, 1].axhline(y=Aboveground_Live[0], color='grey', lw=0.4)

            # note min/med/max deficit stands in both the figure title and file name
            master_title = 'Growth dynamics of stand %s' % standID
            file_name = '-C_pool_detail-stand_%s.pdf' % standID
            if standID in detail_stands:
                case_index = detail_stands.index(standID)
                case = descriptors[case_index]
                master_title += ' (%s deficit stand) % case'
                file_name = '-C_pool_detail-deficit_%s-stand_%s.pdf' % (case, standID)

            # labeling, formatting & saving
            matplotlib.rcParams.update({'font.size': 11})
            plt.suptitle(master_title, fontsize=13)
            axes[0, 0].set_title('Control')
            axes[0, 1].set_title('Harvested')

            axes[2, 0].axhline(color='k')
            axes[2, 1].axhline(color='k')

            plt.setp([a.get_xticklabels() for a in axes[0, :]], visible=False)
            plt.setp([a.get_xticklabels() for a in axes[1, :]], visible=False)
            plt.setp([a.get_yticklabels() for a in axes[:, 1]], visible=False)
            axes[0, 0].set_ylabel('Live basal area\n($\mathregular{m^2 ha^{-1}}$)')
            axes[1, 0].set_ylabel('Trees per hectare')
            axes[2, 0].set_ylabel('Carbon density\n(Mg C $\mathregular{ha^{-1}}$)')
            axes[2, 0].set_xlabel('Year')
            axes[2, 1].set_xlabel('Year')

            axes[1, 0].legend(loc=10, prop={'size': 8}, bbox_to_anchor=[0.9, 0.94], shadow=True, fancybox=True)
            axes[1, 1].legend(loc=10, prop={'size': 8}, bbox_to_anchor=[0.9, 0.94], shadow=True, fancybox=True)
            axes[2, 1].legend(loc=10, prop={'size': 8}, bbox_to_anchor=[-0.1, 0.8], shadow=True, fancybox=True)

            scenario = archive_path.split('-')[-1].split('/')[0]
            plt.savefig(archive_path + scenario + file_name)
            plt.close()
    print
    print


def productivity_determinants(db_fpath, archive_path):
    """ Creates scatterplots and performs multiple linear regression to help identify which simulation factors are the
    most significant determinants of productivity in both Contol and Harvest scenarios. Factors tested include:
        * site aspect
        * site slope
        * site elevation
        * initial species diversity
        * initial tree density
        * initial live basal area
        * initial stand carbon density
        * initial stand mortality (BA basis)

    :param db_fpath:
    :param archive_path:
    :return:
    """

    # establish a connection to the working database
    con = sqlite3.connect(db_fpath)
    with con:
        cur = con.cursor()

        def carbon_subplots(panel, total_panels, query, x_label, y_label):

            subplot_rows = round(total_panels**0.5)
            subplot_columns = subplot_rows
            plt.subplot(subplot_rows, subplot_columns, panel)

            cur.execute(query)
            data_tuples = cur.fetchall()
            data = zip(*data_tuples)

            plt.scatter(data[0], data[1])
            significance_test(data[0], data[1])
            plt.xlabel(x_label)
            plt.ylabel(y_label)

            return data[0], data[1]

        response_label = 'Year 2100 AG Live C'

        for i, case in enumerate(['Control', 'RX']):
            print "Creating plots to illustrate determinants of %s stand productivity..." % case

            regressor_sets = [

                ["""SELECT x.Aspect, c.Aboveground_Total_Live_%s
                    FROM Carbon c
                    JOIN site x ON x.StandID=c.StandID
                    WHERE c.Year=2100 """ % case, 'site aspect'],

                ["""SELECT x.Slope, c.Aboveground_Total_Live_%s
                    FROM Carbon c
                    JOIN site x ON x.StandID=c.StandID
                    WHERE c.Year=2100 """ % case, 'site slope'],

                ["""SELECT x.ElevFt, c.Aboveground_Total_Live_%s
                    FROM Carbon c
                    JOIN site x ON x.StandID=c.StandID
                    WHERE c.Year=2100 """ % case, 'site elevation'],

                ["""SELECT x.SpeciesCount, c.Aboveground_Total_Live_%s
                    FROM Carbon c
                    JOIN SpeciesDiversity x ON x.StandID=c.StandID
                    WHERE c.Year=2100 """ % case, 'initial species diversity'],

                ["""SELECT x.Tot_TPHA, c.Aboveground_Total_Live_%s
                    FROM Carbon c
                    JOIN Control_TPHA x ON x.StandID=c.StandID
                    WHERE c.Year=2100 AND x.Year=2014 """ % case, 'initial tree density'],

                ["""SELECT x.Tot_BA, c.Aboveground_Total_Live_%s
                    FROM Carbon c
                    JOIN Control_SpeciesBA x ON x.StandID=c.StandID
                    WHERE c.Year=2100 AND x.Year=2014""" % case, 'initial stand live basal area'],

                ["""SELECT x.Aboveground_Total_Live_Control, c.Aboveground_Total_Live_%s
                    FROM Carbon c
                    JOIN Carbon x ON x.StandID=c.StandID
                    WHERE c.Year=2100 AND x.Year=2014""" % case, 'initial stand live carbon density'],

                ["""SELECT x.InitialMortality, c.Aboveground_Total_Live_%s
                    FROM Carbon c
                    JOIN RX_StandMortality x ON x.StandID=c.StandID
                    WHERE c.Year=2100 AND x.Year=2014""" % case, 'initial stand mortality (BA basis)']

            ]

            response_data = []
            regressor_data = []
            for j, regressor_set in enumerate(regressor_sets):
                query, x_label = regressor_set
                print "Testing", x_label
                xs, ys = carbon_subplots(j+1, len(regressor_sets), query, x_label, response_label)
                response_data.append(xs)
                regressor_data.append(ys)

            matplotlib.rcParams.update({'font.size': 8})
            plt.tight_layout()
            plt.subplots_adjust(top=0.9)
            plt.subplots_adjust(bottom=0.1)
            plt.suptitle('%s stand productivity determinants' % case, fontsize=13)

            scenario = archive_path.split('-')[-1].split('/')[0]
            plt.savefig(archive_path + scenario + '-%s_productivity_determinants.pdf' % case)
            plt.close()

            # now try some multiple regression considering all three predictors
            import statsmodels.api as sm
            # https://stackoverflow.com/questions/11479064/multiple-linear-regression-in-python
            predictors = np.array(regressor_data).T
            predictors = sm.add_constant(predictors)
            results = sm.OLS(endog=response_data[0], exog=predictors).fit()
            print results.summary()
    print
    print


def deficit_determinants(db_fpath, archive_path):
    """ Creates scatterplots and performs multiple linear regression to help identify which simulation factors are the
    most significant determinants of stand integrated carbon deficit. Factors tested include:
        * site aspect
        * site slope
        * site elevation
        * initial species diversity
        * initial tree density
        * initial live basal area
        * initial stand carbon density
        * initial stand mortality (BA basis)

    :param db_fpath:
    :param archive_path:
    :return:
    """

    # establish a connection to the working database
    con = sqlite3.connect(db_fpath)
    with con:
        cur = con.cursor()

        def deficit_subplots(panel, total_panels, query, x_label, y_label):

            subplot_rows = round(total_panels**0.5)
            subplot_columns = subplot_rows
            plt.subplot(subplot_rows, subplot_columns, panel)

            cur.execute(query)
            data_tuples = cur.fetchall()
            data = zip(*data_tuples)

            plt.scatter(data[0], data[1])
            significance_test(data[0], data[1])
            plt.xlabel(x_label)
            plt.ylabel(y_label)

            return data[0], data[1]

        response_label = 'End normalized C deficit'

        print "Creating plots to illustrate determinants of stand integrated carbon deficit..."

        regressor_sets = [

        ["""SELECT x.Aspect, d.End_normalized_deficit
            FROM Deficit d
            JOIN site x ON x.StandID=d.StandID""", 'site aspect'],

        ["""SELECT x.Slope, d.End_normalized_deficit
            FROM Deficit d
            JOIN site x ON x.StandID=d.StandID""", 'site slope'],

        ["""SELECT x.ElevFt, d.End_normalized_deficit
            FROM Deficit d
            JOIN site x ON x.StandID=d.StandID""", 'site elevation'],

        ["""SELECT x.SpeciesCount, d.End_normalized_deficit
            FROM Deficit d
            JOIN SpeciesDiversity x ON x.StandID=d.StandID""", 'initial species diversity'],

        ["""SELECT x.Tot_TPHA, d.End_normalized_deficit
            FROM Deficit d
            JOIN Control_TPHA x ON x.StandID=d.StandID
            WHERE x.Year=2014 """, 'initial tree density'],

        ["""SELECT x.Tot_BA, d.End_normalized_deficit
            FROM Deficit d
            JOIN Control_SpeciesBA x ON x.StandID=d.StandID
            WHERE x.Year=2014""", 'initial stand live basal area'],

        ["""SELECT x.Aboveground_Total_Live_Control, d.End_normalized_deficit
            FROM Deficit d
            JOIN Carbon x ON x.StandID=d.StandID
            WHERE x.Year=2014""", 'initial stand live carbon density'],

        ["""SELECT x.InitialMortality, d.End_normalized_deficit
            FROM Deficit d
            JOIN RX_StandMortality x ON x.StandID=d.StandID
            WHERE x.Year=2014""", 'initial stand mortality (BA basis)']

    ]

    response_data = []
    regressor_data = []
    for j, regressor_set in enumerate(regressor_sets):
        query, x_label = regressor_set
        print "Testing", x_label
        xs, ys = deficit_subplots(j+1, len(regressor_sets), query, x_label, response_label)
        response_data.append(xs)
        regressor_data.append(ys)

    matplotlib.rcParams.update({'font.size': 8})
    plt.tight_layout()
    plt.subplots_adjust(top=0.9)
    plt.subplots_adjust(bottom=0.1)
    plt.suptitle('Harvest carbon deficit determinants', fontsize=13)

    scenario = archive_path.split('-')[-1].split('/')[0]
    plt.savefig(archive_path + scenario + '-deficit_determinants.pdf')
    plt.close()

    # now try some multiple regression considering all three predictors
    import statsmodels.api as sm
    # https://stackoverflow.com/questions/11479064/multiple-linear-regression-in-python
    predictors = np.array(regressor_data).T
    predictors = sm.add_constant(predictors)
    results = sm.OLS(endog=response_data[0], exog=predictors).fit()
    print results.summary()
    print
    print


def CSF_analysis():
    """ Function to specify and control a full FVS sensitivity analysis for the Colorado State Forest stands.

    :return:
    """

    working_path = '/Users/johnfield/Desktop/local_python_code/Forest_dynamics/FVS_files/'
    db_file = 'FVS_analysis.db'
    site_file = 'COSF_stand_data_trimmed.csv'

    rx_control_file_prefix_set = [
        ['3337afterRX', 'Static_Regen_control'],
        ['6034afterRX', 'Static_Regen_control'],
        ['1250afterRX', 'Static_Regen_control'],
        ['3337tpa_261BAmax', 'Static_Regen_control'],
        ['3337tpa_242BAmax', 'Static_Regen_control'],
        ['3337tpa_rcp60_noAutoEst', 'Static_Regen_control'],
        ['3337tpa_rcp60_AutoEst', 'Static_Regen_control']
    ]

    filter = ''
    # filter = "WHERE StandID !='T1_MedBow_LS7' "
    # filter = """ WHERE StandID NOT IN ('T1_MedBow_LS14', 'T1_MedBow_LS21', 'T1_MedBow_LS33', 'T1_MedBow_LS53',
    #                                    'T1_MedBow_LS54', 'T1_MedBow_LS58', 'T1_MedBow_LS6') """

    for rx_control_file_prefixes in rx_control_file_prefix_set:
        archive_path, stand_C_dictionary = upload_convert_filter_process(working_path,
                                                                         db_file,
                                                                         rx_control_file_prefixes,
                                                                         site_file,
                                                                         filter_string=filter)
        database_fpath = archive_path + db_file
        summarize_data(database_fpath)
        plot_deficit_detail(stand_C_dictionary, archive_path)
        plot_all_deficits(stand_C_dictionary, database_fpath, archive_path)
        plot_stand_dynamics(stand_C_dictionary, database_fpath, archive_path)
        # productivity_determinants(database_fpath, archive_path)
        # deficit_determinants(database_fpath, archive_path)


CSF_analysis()