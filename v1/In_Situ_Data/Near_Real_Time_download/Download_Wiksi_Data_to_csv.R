library(WISKIr)

#X <- findWISKIstations('*')
#write.csv(X$station_name, 'wiski_stanames.csv')

data_dir <- '/media/data2/SnowCast_station_data/CRHO_NRT/current/'

# Stations not currently working
# "Level Forest" "PowerLine" Upper Forest Bow Hut

stations <- c("Bonsai Meteorological","Burstall Pass", "Centennial Ridge",
    "Canadian Ridge", "Fortress Ledge",
    "Fortress Ridge", "Fortress Ridge South Meteorological", "Fisera Ridge", "Helen",
    "Hay Meadow", "Peyto Hut Main",
    "Upper Clearing", "Vista View", "Canadian Ridge North")

variables <- c('TEMPERATURE AIR','RelHum','SnowDepth','Snow Depth Quality Flag','WindDir','WindSpeed','AccumulatedPrecip',
                'IncomingLWRad','IncomingSWRad','OutgoingLWRad','OutgoingSWRad','IntervalPrecip','SurfTemp')

for(i in 1:length(stations))
{
  print( paste0('Working on ... ',stations[i]) )
  #sta_name = findWISKIstations(paste0('*',stations[i],'*'))
  #print(sta_name)  
  new_name <- stations[i] #stringr::str_replace_all(stations[i],' ','%20')
  #print(new_name)
  df<-findWISKItimeseries( new_name)
#  print(df)
  for (cvar in variables) {
    if(cvar %in% df$parametertype_name) {
        print(cvar)
        id<-df[ df$parametertype_name == cvar & df$ts_name == '01.Original',]$ts_id
  
    if( length(id) > 1)
    {
        id <- id[1]
     }
    # Some times this *&^%*&%^(&  fails and not handeled right. So write a stupied R try catch
    
    ts0<-getWISKIvalues(id,timezone='MST',startDate = "2016-04-01") # when no end date specified, retrives to end
    
    sane_var_name <- stringr::str_replace_all(cvar,' ','_')
    sane_file_name <- paste0( stringr::str_replace_all(stations[i],' ','_'),'__',sane_var_name ,'.csv')
    write.csv(ts0, paste0(data_dir,sane_file_name))
  }
}
}

