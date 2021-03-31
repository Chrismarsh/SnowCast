''' Created on Mon Jan 30 2016
 @author Jan Talsma
 amended by Micha Werner
 amended by Dave Casson
 upgraded to Python3 Dave CAasson
 
 Script to harvest Environment Canada NWP forecasts
 - Regional Model
 - Global Model
 - High Resolution Model
 - REPS Model
 - GEPS Model
 
 Can be run with command line arguments
 1. Name of XML run file (exported from FEWS - contains paths)
 2. Model to download [RDPS; GDPS; HRDPS; REPS; GEPS]
 3. Model time step (in hours)
 4. Maximum lead time to download (in hours)
 5. Option to use multi-threading or to download sequentially

'''

import os
import time
import optparse as op
import datetime as dt
import urllib3
import threading
import socket

global NumFilesDownloaded
global FilesFailed

timeout = 10
socket.setdefaulttimeout(timeout)

####################################################################################################
def getRunInfo(settingsDict, runInfoFile,logger):
    ''' Function to retrieve run time information from FEWS '''
    
    logger.info('Loading run time information from run info file')
    workDir   = 'test' #fa.getElementFromRuninfo(runInfoFile, 'workDir')
    # startTime = fa.getStartTimefromRuninfo(runInfoFile)
    # endTime   = fa.getEndTimefromRuninfo(runInfoFile)
    
    # add to settings dict, not used
    # settingsDict['startTime'] = startTime
    # settingsDict['endTime']   = endTime
    settingsDict['workDir']   = workDir
    

    # settingsDict['diagnosticFile']  = fa.getElementsFromRuninfo(runInfoFile, 'outputDiagnosticFile')
    settingsDict['destinationDir'] =  'test_dl' #fa.getKeyValueFromRunInfo(runInfoFile, 'destinationDir', True)
    

    return settingsDict



def start_thread(url,outputDir,filename,logger,useThreading,threadLimiter,maximumNumberOfThreads):
    ''' Function implement threading for data download'''
    global numFilesDownloaded
    global FilesFailed
    threadLimiter.acquire()
    
    thread = threading.Thread(target=data_download, args=(url,outputDir,filename,logger,useThreading,threadLimiter,maximumNumberOfThreads))
    thread.start()
       
    return thread

def data_download(url,outputDir,filename,logger,useThreading,threadLimiter,maximumNumberOfThreads):
    ''' Function to download data from url, called by threading'''
    outputFile = os.path.join(outputDir,filename)

    if os.path.isfile(outputFile):
        logger.info('File %s already exists. Download cancelled' %filename)
        if useThreading:
            threadLimiter.release()
    else:
        # try:
            http = urllib3.PoolManager(timeout=60, retries=3, num_pools = maximumNumberOfThreads)
            response = http.request('GET',url,preload_content=False)
            with open(outputFile, 'wb') as out:
                while True:
                    data = response.read(1024)
                    if not data:
                        break
                    out.write(data)

            response.release_conn()
            url = url.replace('&','&amp;')
            logger.info('Downloading url complete [%s]' %url)
            global NumFilesDownloaded
            NumFilesDownloaded +=1
        # except urllib3.exceptions.NewConnectionError:
        #     logger.error('Downloading url failed [%s]' %url)
        #     FilesFailed.append(filename)
        # except urllib3.exceptions.HTTPError:
        #     logger.error('Downloading url failed [%s]' %url)
        #     FilesFailed.append(filename)

    if useThreading:
        #Log Current number of threads
        logger.info('Maximum Number Concurrent of Threads Allowed = %d, Number of Threads Active = %d' %(maximumNumberOfThreads, threading.active_count()-1))
        threadLimiter.release()
    return True

def mainscript():
    
    start = time.time()
    txtLogFile   = os.path.normpath('get_ec_forecast.log')
    
    # logger = fa.setlogger(txtLogFile,'log')
    # logger.info('Started Environment Canada download script at %s', str(dt.datetime.fromtimestamp(start)))
    
    # get command line arguments - this is the name of the run fike
    cmdLineArgs = op.OptionParser()
    cmdLineArgs.add_option('--runInfoFile',  '-r',  default='none') 
    cmdLineArgs.add_option('--model',        '-m',  default='RDPS') 
    cmdLineArgs.add_option('--leadTime',     '-l',  default='48') 
    cmdLineArgs.add_option('--parameter',    '-p',  default='APCP_SFC_0') 
    cmdLineArgs.add_option('--delay',        '-d',  default='3') 
    cmdLineArgs.add_option('--firstLeadTime','-f',  default='3') 
    cmdLineArgs.add_option('--urlBase',      '-u',  default='none') 
    cmdLineArgs.add_option('--threading',    '-t',  default='1')  
    cmdLineArgs.add_option('--maxThreads',    '-n',  default='10')  
    cmdLineArgs.add_option('--referenceTime','-z',  default=dt.datetime.now().strftime("%Y%m%d%H%M"))
    
    cmdOptions, cmdArguments = cmdLineArgs.parse_args()    
    runInfoFile     = cmdOptions.runInfoFile
    model           = cmdOptions.model
    leadTime        = int(cmdOptions.leadTime)
    parameterString = cmdOptions.parameter
    delayHours      = int(cmdOptions.delay)
    urlBase         = cmdOptions.urlBase
    firstLeadTime   = int(cmdOptions.firstLeadTime)
    threadingOpt    = int(cmdOptions.threading)
    maximumNumberOfThreads    = int(cmdOptions.maxThreads)
    referenceTime   = dt.datetime.strptime(cmdOptions.referenceTime, "%Y%m%d%H%M")
    
    # interpret option whether to use threading
    useThreading=False
    threadLimiter = threading.BoundedSemaphore(maximumNumberOfThreads) #Additional Variable to Control Threading, defined even if threading not used
    
    if threadingOpt==1: 
        useThreading=True
        # logger.info('Threading enabled with maximum number of threads =  %d'  %maximumNumberOfThreads)
        
    settingsDict = dict()

    # fixed URL's - can be replaced using urlBase option in command line
    settingsDict['RDPS_URL'] = 'https://dd.weather.gc.ca/model_gem_regional/10km/grib2/'
    settingsDict['GDPS_URL'] = 'https://dd.weather.gc.ca/model_gem_global/15km/grib2/lat_lon/'
    settingsDict['HRDPS_URL'] = 'https://dd.weather.gc.ca/model_hrdps/continental/grib2/'
    settingsDict['REPS_URL'] = 'https://dd.weather.gc.ca/ensemble/reps/15km/grib2/raw/'

    if parameterString == 'WIND_TGL_10m':
        settingsDict['GEPS_URL'] = 'https://dd.weather.gc.ca/ensemble/geps/grib2/products/'
    else:
        settingsDict['GEPS_URL'] = 'https://dd.weather.gc.ca/ensemble/geps/grib2/raw/'

    # fixed time step (in hours) per model    
    settingsDict['RDPS_TIMESTEP']  = 1
    settingsDict['GDPS_TIMESTEP']  = 3
    settingsDict['HRDPS_TIMESTEP'] = 1
    settingsDict['REPS_TIMESTEP'] = 3
    settingsDict['GEPS_TIMESTEP'] = 6
    
    # interval at which model is run (in hours) per model    
    settingsDict['RDPS_INTERVAL']  = 6
    settingsDict['GDPS_INTERVAL']  = 12
    settingsDict['HRDPS_INTERVAL'] = 6
    settingsDict['REPS_INTERVAL'] = 12
    settingsDict['GEPS_INTERVAL'] = 12
    
    if 'none' in runInfoFile:
        # logger.warning('No command line provided -downloading regional model for 48 hours')
        #if not command line is provided, download regional model
        settingsDict['destinationDir'] = '.'
    else:
        # in this case a run file is provided as well as other command line arguments        
        settingsDict = getRunInfo(settingsDict, runInfoFile,logger)   

        

    xmlLog = False    
    xmlLogFile = os.path.normpath('get_ec_forecasts_log.xml')
    if 'diagnosticFile' in settingsDict:
        xmlLog = True    
        #xmlLogFile = settingsDict['diagnosticFile']  # this does not seem to work! Assigning logFile name

    outputDir = settingsDict['destinationDir']    

    logger.info(xmlLogFile)
    
    if xmlLog: fa.log2xml(txtLogFile,xmlLogFile) # this convers text log file to fews diagnostics file


    # check if running for a valid model identifier - if not then bomb
    if model not in ['RDPS', 'GDPS','HRDPS','REPS','GEPS']:
        logger.error('Unrecognized model identifier code [%s]  use either [RDPS,GDPS,HRDPS,REPS,GEPS]' %model)
        if xmlLog: fa.log2xml(txtLogFile,xmlLogFile) # this convers text log file to fews diagnostics file
        quit() 

    
    # allocate settings depending on the model chosen
    timeStep  = settingsDict['%s_TIMESTEP' %model]
    
    interval  = settingsDict['%s_INTERVAL' %model]
    
    # assign URL if not provided in command line
    if 'none' in urlBase:
        urlBase = settingsDict['%s_URL' %model]
    
    # reference time is utc+00 - configurable delay (cfs data is in utc+00)
    refDate = referenceTime-dt.timedelta(0,delayHours*3600) #dt.datetime.utcnow()-dt.timedelta(0,delayHours*3600)

    # time stamps
    dStr = refDate.date().strftime("%Y%m%d")
    hStr = '%02d'%(interval*int(refDate.time().hour/interval))
    
    logger.info('Downloading forecast for reference date [%s %s] and parameters [%s]' %(dStr,hStr,parameterString))
    if xmlLog: fa.log2xml(txtLogFile,xmlLogFile) # this convers text log file to fews diagnostics file

    # list with variables to download - this may be a comma separated list
    parameters  = parameterString.split(',')
    # 'TMP_TGL_2','APCP_SFC_0']

    logger.debug('Downloading parameters  [%s] for lead times [%d] to [%d] at [%d] intervals' %(parameterString, firstLeadTime, leadTime, timeStep))
    if xmlLog: fa.log2xml(txtLogFile,xmlLogFile) # this convers text log file to fews diagnostics file
  
    # list with lead times to download
    leadTimes = list()
    for leadTime in range(firstLeadTime, leadTime+timeStep,timeStep):
        leadTimes.append('%03d' %leadTime)
        
    #Create empty list for threads
    threads = list()
    
    global NumFilesDownloaded
    global FilesFailed
    NumFilesDownloaded = 0
    FilesFailed = list()
 
    
    for leadTime in leadTimes:
        for parameter in parameters:
    
            if 'RDPS' in model:  filename = 'CMC_reg_' + parameter + '_ps10km_' + dStr + hStr + '_P' + leadTime +'.grib2'
            if 'GDPS' in model:  filename = 'CMC_glb_' + parameter + '_latlon.15x.15_' + dStr + hStr + '_P' + leadTime +'.grib2'
            if 'HRDPS' in model: filename = 'CMC_hrdps_continental_' + parameter + '_ps2.5km_' + dStr + hStr + '_P' + leadTime +'-00.grib2'
            if 'REPS' in model:
                if parameter == "WIND_TGL_10m":
                    filename = 'CMC-reps-srpe-prob_' + parameter + '_ps15km_' + dStr + hStr + '_P' + leadTime +'_all-products.grib2'
                else:
                    filename = 'CMC-reps-srpe-raw_' + parameter + '_ps15km_' + dStr + hStr + '_P' + leadTime + '_allmbrs.grib2'
            if 'GEPS' in model:
                if parameter == "WIND_TGL_10m":
                    filename = 'CMC_geps-prob_' + parameter + '_latlon0p5x0p5_' + dStr + hStr + '_P' + leadTime + '_all-products.grib2'
                else:
                    filename = 'CMC_geps-raw_' + parameter + '_latlon0p5x0p5_' + dStr + hStr + '_P' + leadTime + '_allmbrs.grib2'

            url = urlBase + hStr + '/' + leadTime + '/' + filename

            if useThreading:
                threads.append(start_thread(url,outputDir,filename,logger,useThreading,threadLimiter,maximumNumberOfThreads))
            else:
                data_download(url,outputDir,filename,logger,useThreading,threadLimiter,maximumNumberOfThreads)

    if useThreading: [thread.join() for thread in threads]
    
    logger.info('Completed downloading %d files in %d seconds'%(NumFilesDownloaded, time.time() - start))
    
    for failedfile in FilesFailed:
        logger.error('File failed to download: %s' %failedfile)
        
    if xmlLog: fa.log2xml(txtLogFile,xmlLogFile) # this convers text log file to fews diagnostics file


####################################################################################################    
if __name__ == '__main__':
    ### this is not executed when script is imported from another script
    mainscript()
    