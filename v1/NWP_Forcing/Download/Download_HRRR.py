import os
import numpy as np
import wget
import sys
import imp
import time
import urllib
import send_mail
from datetime import date

import hrrr_variable_from_pando as hrrr

# Load in config file
#######  load user configurable paramters here    #######
# Check user defined configuraiton file
if len(sys.argv) == 1:
    raise ValueError('Download_HRDPS_GRIB2.py requires one argument [configuration file] (i.e. python Download_HRDPS_GRIB2.py download_config.py')

# Get name of configuration file/module
configfile = sys.argv[1]
cvar = str(sys.argv[2])
print(cvar)

# Load in configuration file as module
X = imp.load_source('',configfile)

# Assinge to local variables
download_dir = X.download_dir

# Move to input if exists (make if not)
if not os.path.isdir(download_dir):
    os.mkdir(download_dir)
os.chdir(download_dir)

# Info
sDate = date(2016, 8, 28)   # Start date
eDate = date(2017, 11, 28)
#eDate = date(2017, 11, 28)   # End date (exclusive)
#variables = ['TMP:2 m', 'RH:2 m', 'UGRD:10 m', 'VGRD:10 m', 'PRATE', 'CPOFP', 'DSWRF', 'DLWRF', 'PRES:surface','WEASD', 'SNOD','APCP:surface']

hrrr.get_single_variable_multiple_days(sDate,eDate,cvar,download_dir)

