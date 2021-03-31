import xarray as xr
import numpy as np
import pandas as pd
import plot.plot_settings as plot_settings
import matplotlib as mpl
import subprocess
import os
import xarray as xr
import branca
import folium
from folium.utilities import parse_options
import branca.colormap as cm
from branca.element import MacroElement
from jinja2 import Template
from collections import OrderedDict



class GroupedLayerControl(MacroElement):

    _template = Template("""
        {% macro html(this,kwards) %}
            <script src="./dist/leaflet.groupedlayercontrol.min.js"></script>
            <link rel="stylesheet" href="./dist/leaflet.groupedlayercontrol.min.css" />
        {% endmacro %}
    
        {% macro script(this,kwargs) %}
            var {{ this.get_name() }} = {
                base_layers : {
                    {%- for key, val in this.base_layers.items() %}
                    {{ key|tojson }} : {{val}},
                    {%- endfor %}
                },
                "Forecasts" :  {
                    {%- for key, val in this.overlays.items() %}
                    {{ key|tojson }} : {{val}},
                    {%- endfor %}
                }
            };
            L.control.groupedLayers(
                {{ this.get_name() }}.base_layers,
                {{ this.get_name() }},
                {{ this.options|tojson }}
            ).addTo({{this._parent.get_name()}});

            {%- for val in this.layers_untoggle.values() %}
            {{ val }}.remove();
            {%- endfor %}
        {% endmacro %}
        """)

    def __init__(self, position='topright', collapsed=True, autoZIndex=True, exclusiveGroups=[], groupCheckboxes=False,
                 **kwargs):
        super(GroupedLayerControl, self).__init__()
        self._name = 'LayerControl'
        self.options = parse_options(
            position=position,
            collapsed=collapsed,
            autoZIndex=autoZIndex,
            exclusiveGroups=exclusiveGroups,
            groupCheckboxes=groupCheckboxes,
            **kwargs
        )
        self.base_layers = OrderedDict()
        self.overlays = OrderedDict()
        self.layers_untoggle = OrderedDict()

    def reset(self):
        self.base_layers = OrderedDict()
        self.overlays = OrderedDict()
        self.layers_untoggle = OrderedDict()

    def render(self, **kwargs):
        """Renders the HTML representation of the element."""
        for item in self._parent._children.values():
            if not isinstance(item, folium.map.Layer ) or not item.control:
                continue
            key = item.layer_name
            if not item.overlay:
                self.base_layers[key] = item.get_name()
                if len(self.base_layers) > 1:
                    self.layers_untoggle[key] = item.get_name()
            else:
                self.overlays[key] = item.get_name()
                if not item.show:
                    self.layers_untoggle[key] = item.get_name()
        super(GroupedLayerControl, self).render()

class FavIcon(MacroElement):
    def __init__(self):
        super(FavIcon, self).__init__()

        self._template = Template(u"""
        {% macro html(this, kwargs) %}
            <link rel="apple-touch-icon" sizes="180x180" href="favicons/apple-touch-icon.png">
            <link rel="icon" type="image/png" sizes="32x32" href="favicons/favicon-32x32.png">
            <link rel="icon" type="image/png" sizes="16x16" href="favicons/favicon-16x16.png">
            <link rel="manifest" href="favicons/manifest.json">
            <link rel="mask-icon" href="favicons/safari-pinned-tab.svg" color="#5bbad5">
            
            <title>SnowCast</title>
            {% endmacro %}
            """)

class BindColormapLayer(MacroElement):
    """Binds a colormap to a given layer.
    https://nbviewer.jupyter.org/gist/BibMartin/f153aa957ddc5fadc64929abdee9ff2e
    Parameters
    ----------
    colormap : branca.colormap.ColorMap
        The colormap to bind.
    """
    def __init__(self, layer, colormap):
        super(BindColormapLayer, self).__init__()
        self.layer = layer
        self.colormap = colormap
        self._template = Template(u"""
        {% macro script(this, kwargs) %}
            {{this.colormap.get_name()}}.svg[0][0].style.display = 'block';
            {{this.colormap.get_name()}}.svg[0][0].style.backgroundColor = 'white';
            {{this._parent.get_name()}}.on('overlayadd', function (eventLayer) {
                if (eventLayer.layer == {{this.layer.get_name()}}) {
                    {{this.colormap.get_name()}}.svg[0][0].style.display = 'block';
                }});
            {{this._parent.get_name()}}.on('overlayremove', function (eventLayer) {
                if (eventLayer.layer == {{this.layer.get_name()}}) {
                    {{this.colormap.get_name()}}.svg[0][0].style.display = 'none';
                }});
        {% endmacro %}
        """)  # noqa

class BindColormapTileLayer(MacroElement):
    """Binds a colormap to a given layer.
    https://nbviewer.jupyter.org/gist/BibMartin/f153aa957ddc5fadc64929abdee9ff2e
    Parameters
    ----------
    colormap : branca.colormap.ColorMap
        The colormap to bind.
    """
    def __init__(self, layer, colormap):
        super(BindColormapTileLayer, self).__init__()
        self.layer = layer
        self.colormap = colormap
        self._template = Template(u"""
                {% macro script(this, kwargs) %}
            {{this.colormap.get_name()}}.svg[0][0].style.display = 'block';
            {{this.colormap.get_name()}}.svg[0][0].style.backgroundColor = 'white';
            {{this._parent.get_name()}}.on('layeradd', function (eventLayer) {
                if (eventLayer.layer == {{this.layer.get_name()}}) {
                    {{this.colormap.get_name()}}.svg[0][0].style.display = 'block';
                }});
            {{this._parent.get_name()}}.on('layerremove', function (eventLayer) {
                if (eventLayer.layer == {{this.layer.get_name()}}) {
                    {{this.colormap.get_name()}}.svg[0][0].style.display = 'none';
                }});
        {% endmacro %}
        """)  # noqa

class Sidebar(MacroElement):
    """

    """
    def __init__(self, map ):
        super(Sidebar, self).__init__()

        #sidebar.open('home')
        # will auto open sidebar

        self.map = map
        self._template = Template(u"""
        {% macro header(this, kwargs) %}
        <script src="./js/leaflet-sidebar.min.js"></script>
        <link rel="stylesheet" href="./css/leaflet-sidebar.min.css"/>
        {% endmacro %}
        
        {% macro script(this, kwargs) %}
           var sidebar = L.control.sidebar('sidebar').addTo({{this.map.get_name()}})
           
        {% endmacro %}
        
        {% macro html(this, kwargs) %}
               <div id="sidebar" class="sidebar collapsed">
        <!-- Nav tabs -->
            <div class="sidebar-tabs">
                <ul role="tablist">
                    <li><a href="#home" role="tab"><i class="fa fa-home"></i></a></li>
                    <li><a href="#about" role="tab"><i class="fa fa-info-circle"></i></a></li>
                    <li><a href="#help" role="tab"><i class="fa fa-question"></i></a></li>

                    <li><a href="https://github.com/Chrismarsh/CHM" role="tab" target="_blank"><i class="fa fa-github"></i></a></li>
                </ul>
    
            </div>
    
            <!-- Tab panes -->
            <div class="sidebar-content">
                <div class="sidebar-pane" id="home">
                    <h1 class="sidebar-header"> SnowCast <span class="sidebar-close"><i class="fa fa-caret-left"></i></span></h1>
                    <p></p>

                    <p></p>
                    <p><b>SnowCast</b> is an experimental data product that uses the Global Environmental Multiscale (GEM) model forecasts from Environment and Climate Change Canada (ECCC) to drive the Canadian Hydrological Model (CHM). Estimates of snowpack are provided over the a Bow River Basin, centered over Banff, Canada.  </p>

                    SnowCast is developed by <a href="http://www.nicwayand.com">Nic Wayand</a> and <a href="http://www.chrismarsh.ca"> Chris Marsh</a> at the University of Saskatchewan. SnowCast is developed as part of <a href="https://gwf.usask.ca/">Global Water Futures</a> and the <a href="http://www.usask.ca/hydrology/">Centre for Hydrology</a>, University of Saskatchewan. Thanks to collaboration with ECCC. </p>

                   
                    <b> Disclaimer - please note that the current version of this model is experimental and is not meant to be used for decision-making purposes </b> </p>
  
                </div>
    
                <div class="sidebar-pane" id="about">
                    <h1 class="sidebar-header">Model details<span class="sidebar-close"><i class="fa fa-caret-left"></i></span></h1>

                    <h3>Meteogrological data</h3>
                    <p></p>
                    <p>Global Environmental Multiscale (GEM) model forecasts are used to force the model with meteorological estimates.
                      <ul>
                        <li>GEM 2.5 km 2-day forecasts <a href="https://weather.gc.ca/grib/grib2_HRDPS_HR_e.html">(High Resolution Deterministic Prediction System (HRDPS))</a> </li>
                        <!-- <li>GEM 25 km 6-day forecasts <a href="https://weather.gc.ca/grib/grib2_glb_25km_e.html">(Global Deterministic Forecast System (GDPS)</a> </li> -->
                      </ul>
                    </p>

                    <h3>Hydrological model</h3>
                    <p>
                        The Canadian Hydrological Model (CHM) is a modular, multi-physics, spatially distributed modelling framework designed for 
                        representing cold-regions hydrological processes. CHM uses existing high-quality open-source libraries and modern high-performance
                         computing practices to provide a framework that allows for integration of a wide range of process representations, ranging from 
                         simple empirical relationships to physics-based, state-of-the-art algorithms. Modularity in structure and process representation 
                         allows for diagnosis of deficiencies in these aspects of the model.  CHM also has sufficient flexibility in spatial representation 
                         and algorithm parameterisation to assess uncertainty in model structure, parameters, initial conditions, process representation, and
                          spatial and temporal scales. By utilizing unstructured meshes, fewer than 1% of the computational elements of high-resolution structured 
                          (raster) grids are usually necessary.  This preserves surface and sub-surface heterogeneity but results in fewer parameters and initial conditions.
                    </p> 
                    <p></p>
                    <p>The simulation domain covers the Upper Bow River watershed, above Calgary, Alberta. The domain is divided into 129,721 triangles using the Mesher algorithm (Marsh et al, in review), to better approximate complex terrain and variable vegetation. This has resulted in requiring only 4% of the total computational elements as the original raster, dramatically improving computational efficiency. </p>

                </div>

                <div class="sidebar-pane" id="help">
                    <h1 class="sidebar-header">Help<span class="sidebar-close"><i class="fa fa-caret-left"></i></span></h1>
                    <p></p>

                    <h3>Overview</h3>
                        <p>
                        Two model outputs, SWE and snow depth, are provided for a) the start of the model run (current) and b) for a period in the future (forecast). The difference between these model outputs are shown as 'Predicted change.'
                        </p>

                    <h3>Variables</h3>
                        <p><b>SWE</b> -- Snow Water Equivalent is the amount of water stored in the snow pack, given as either a mass (kg/m^2) or as depth of ponded water (mm). These units are equivalent </p>
                        <b>Snow Depth</b> -- Snow depth is the depth of snow in meters </p>

                </div>


            </div>
        </div>
    {% endmacro %}
        
        """)  # noqa

def make_colour_txt( var, vmin, vmax, n=12):
    colors = plot_settings.get_cmap(var)
    r = np.linspace(vmin, vmax, n)
    fname = f'color_{var}.txt'
    with open(fname, 'w') as file:
        for elev, c in zip(r, colors):
            if isinstance(c, str):
                hex = c.lstrip('#')
                rgb = tuple(int(hex[i:i + 2], 16) for i in (0, 2, 4))
                file.write(f'{elev} {rgb[0]} {rgb[1]} {rgb[2]} 255\n')
            else:
                file.write(f'{elev} {c[0]*255} {c[1]*255} {c[2]*255} 255\n')

        file.write(f'nv 0 0 0 0\n')

    return fname


def make_geotiff(df, var=None, time=None):

    if time is not None:
        d = df[var].isel(time=time).rio.write_nodata(-9999)
    else:
        # if a diff comes in it won't have a time axis
        d = df[var].rio.write_nodata(-9999)
        time = 'diff'

    tmp_tiff = f'{var}_wgs_{time}.tif'
    d.rio.to_raster(tmp_tiff)
    exec = f"""/usr/local/bin/gdalwarp -t_srs EPSG:4326 -srcnodata '-9999' {tmp_tiff}  output_{var}_{time}.tif"""
    subprocess.check_call([exec], shell=True)

    os.remove(tmp_tiff)

    return f'output_{var}_{time}.tif'

def make_map(settings, df):

    minZoom = 7
    maxZoom = 12

    # the lat long in the df isn't /quite/ right but close enough for this
    m = folium.Map(location=[df.lat.mean(), df.lon.mean()], zoom_start=9, tiles=None, control_scale=True ,zoom_control=True, max_zoom=maxZoom, min_zoom=minZoom)
    folium.TileLayer('Stamen Terrain', control=False, overlay=True, max_zoom=maxZoom, min_zoom=minZoom).add_to(m) # overlay=True is important to allow it to be drawn over and not replaced

    ROBUST_PERCENTILE = 0.02  # follows xarray's robust 98% - 2%
    layer_attr = 'University of Saskatchewan, Global Water Futures'



    for var in settings['plot_vars']:

        vmax = float(df.quantile(1.0 - ROBUST_PERCENTILE, dim=['time', 'y', 'x'])[var])
        vmin = float(df.quantile(ROBUST_PERCENTILE, dim=['time', 'y', 'x'])[var])

        for time in [0, -1]:

            # convert to geotiff and reporject
            tiff = make_geotiff(df, var=var, time=time)

            make_tiles(settings, tiff, var, time, vmax, vmin, minZoom, maxZoom )

            model_time = pd.to_datetime(df.time.values[time])
            model_time = model_time.strftime('%Y/%m/%d %H:00 UTC')

            name = plot_settings.get_title(var)
            if time == 0:
                name = '%s - Current %s' % (name, model_time)
            else:
                name = '%s - Forecast for %s' % (name, model_time)

            TL = folium.raster_layers.TileLayer(
                os.path.join('./tiles', f'tiles_{var}_{time}','{z}/{x}/{y}.png'),
                minZoom=minZoom, maxZoom=maxZoom,
                attr=layer_attr,
                name=name,
                opacity=0.6,
                overlay=False,
                tms=True,
                show=True if time == 0 and var == 'snowdepthavg' else False).add_to(m)
            colormap = cm.LinearColormap(colors=plot_settings.get_cmap(var), vmin=vmin, vmax=vmax)
            colormap.caption = '%s (%s)' % (plot_settings.get_title(var), plot_settings.get_unit(var))

            m.add_child(colormap)
            m.add_child(BindColormapTileLayer(TL, colormap))

        diff = df.isel(time=-1) - df.isel(time=0)
        vmax = float(diff.quantile(1.0 - ROBUST_PERCENTILE, dim=['y', 'x'])[var])
        vmin = float(diff.quantile(ROBUST_PERCENTILE, dim=['y', 'x'])[var])

        # because this is a difference it should be centred around zero
        max_range = np.max([abs(vmax), abs(vmin)])
        vmax = np.sign(vmax) * max_range
        vmin = np.sign(vmin) * max_range

        tiff = make_geotiff(diff, var=var, time=None)
        make_tiles(settings, tiff, var, 'diff', vmax, vmin, minZoom, maxZoom)

        name = 'Predicted change in ' + plot_settings.get_title(var)
        TL = folium.raster_layers.TileLayer(
            os.path.join('./tiles', f'tiles_{var}_diff', '{z}/{x}/{y}.png'),
            minZoom=minZoom, maxZoom=maxZoom,
            attr=layer_attr,
            name=name,
            opacity=0.6,
            overlay=False,
            tms=True,
            show=False).add_to(m)
        colormap = cm.LinearColormap(colors=plot_settings.get_cmap(f'{var}_diff'), vmin=vmin, vmax=vmax)
        colormap.caption = '%s (%s)' % (plot_settings.get_title(var), plot_settings.get_unit(var))
        m.add_child(colormap)
        m.add_child(BindColormapTileLayer(TL, colormap))

    # GroupedLayerControl(collapsed=False,exclusiveGroups=['Forecasts']).add_to(m)
    m.add_child(Sidebar(m))
    m.add_child(FavIcon())

    folium.LayerControl(collapsed=False).add_to(m)

    m.save(os.path.join(settings['html_dir'],'index.html'))


def make_tiles(settings, tiff, var, time, vmax, vmin, minZoom, maxZoom):
    colormap = None
    if time == 'diff':
        colormap = make_colour_txt(f'{var}_diff', vmin, vmax, n=12)
    else:
        colormap = make_colour_txt(var, vmin, vmax, n=12)
    exec = f'gdaldem color-relief {tiff} {colormap} temp_color.vrt -alpha'
    subprocess.check_call([exec], shell=True)
    tile_path = os.path.join(settings['html_dir'], 'tiles', f'tiles_{var}_{time}')
    exec = f'python /usr/local/bin/gdal2tiles.py temp_color.vrt -w leaflet -z {minZoom}-{maxZoom} {tile_path}'
    subprocess.check_call([exec], shell=True)
    os.remove(tiff)
    os.remove('temp_color.vrt')
    os.remove(colormap)


def make_map_good(settings, df):

    m = None
    for var in settings['plot_vars']:

        all_vmax = []
        all_vmin = []
        cm_handles = [] #colourmap handles
        for time in [0, -1]:
            colored_data, lat, lon, vmax, vmin, model_time = get_var(df, var, time = time)

            # save out vmin/max for the entirely timerange to get a  global min/max later
            all_vmax.append(vmax)
            all_vmin.append(vmin)
            # Define the folium map
            if m is None:
                m = folium.Map(location=[lat.mean(), lon.mean()], zoom_start=9, tiles=None)
                folium.TileLayer('Stamen Terrain', control=False, overlay=True).add_to(m)
                # Add the layer control

            name = plot_settings.get_title(var)

            if time == 0:
                name = '%s - Current %s' % (name, model_time)
            else:
                name = '%s - Forecast for %s' %(name,model_time)

            # Add the raster layer
            IO = folium.raster_layers.ImageOverlay(colored_data,
                                              [[lat.min(), lon.min()], [lat.max(), lon.max()]],
                                              mercator_project=True,
                                              name=name,
                                              opacity=0.6,
                                              show=True if time == 0 and var == 'snowdepthavg' else False,
                                              control_scale=True,
                                              max_zoom=11
                                              ).add_to(m)


            colormap = cm.LinearColormap(colors=plot_settings.get_cmap(var), vmin=vmin, vmax=vmax)
            colormap.caption = '%s (%s)' % (plot_settings.get_title(var), plot_settings.get_unit(var))
            cm_handles.append(colormap)
            m.add_child(colormap)
            m.add_child(BindColormap(IO, colormap))

        vmax = np.amax(all_vmax)
        vmin = np.amax(all_vmin)

        # for key, cmh in m._children.items():
        #     if isinstance(cmh, cm.LinearColormap):
        #         if plot_settings.get_title(var) in cmh.caption:
        #             m._children[key].vmin = vmin
        #             m._children[key].vmax = vmax


    # create difference plots
    # diff = df.isel(time=-1) - df.isel(time=0)
    diff = None

    for var in settings['plot_vars']:
        colored_data, lat, lon, vmax, vmin, model_time = get_var(diff, var, None)
        name = 'Predicted change in ' + plot_settings.get_title(var)

        IO = folium.raster_layers.ImageOverlay(colored_data,
                                          [[lat.min(), lon.min()], [lat.max(), lon.max()]],
                                          mercator_project=True,
                                          name=name,
                                          opacity=0.6,
                                          show=False,
                                          control_scale=True,
                                          max_zoom=11
                                          ).add_to(m)

        colormap = cm.LinearColormap(colors=plot_settings.get_cmap(f'{var}_diff'), vmin=vmin, vmax=vmax)
        colormap.caption = '%s (%s)' % (plot_settings.get_title(var), plot_settings.get_unit(var))
        m.add_child(colormap)
        m.add_child(BindColormap(IO, colormap))


    GroupedLayerControl(collapsed=False,exclusiveGroups=['Forecasts']).add_to(m)
    m.add_child(Sidebar(m))
    m.add_child(FavIcon())
    m.save(os.path.join(settings['html_dir'],'index.html'))


def get_var(df, var, time):
    d = None
    has_time = True

    # if time is not None:
    #     d = df[var].isel(time=time).rio.write_nodata(-9999)
    # else:
    #     d = df[var].rio.write_nodata(-9999) # if a diff comes in it won't have a time axis
    #     time = 'diff'
    #     has_time = False
    #
    # d.rio.to_raster(f'{var}_wgs_{time}.tif')
    # exec = f"""/usr/local/bin/gdalwarp -t_srs EPSG:4326 -srcnodata '-9999' {var}_wgs_{time}.tif  output_{var}_{time}.tif"""
    # subprocess.check_call([exec], shell=True)


    if time is None:
        time='diff'
        has_time = False


    da = xr.open_rasterio(f'output_{var}_{time}.tif')

    # Select data2plot, lat and lon
    data2plot = da.values[0, :]
    data2plot[data2plot == -9999] = np.nan

    lat = da.y.values
    lon = da.x.values

    v=var
    if not has_time:
        v = f'{var}_diff'
    colormap = plot_settings.colormap(v)

    # Function to normalize SWE between 0 and 200
    ROBUST_PERCENTILE = 2.0
    vmax = np.nanpercentile(data2plot, 100 - ROBUST_PERCENTILE)
    vmin = np.nanpercentile(data2plot, ROBUST_PERCENTILE)

    # Remove SWE values lower than 0.1 mm so that these values appear as empty value on the map
    # data2plot[data2plot < vmin] = np.nan
    # Remove large values
    # data2plot[data2plot > vmax] = np.nan

    norm_var = mpl.colors.Normalize(vmin=vmin, vmax=vmax)

    # Generate normalized  data
    normed_data = norm_var(data2plot).data
    # Generate colors corresponding to the normalized  data
    colored_data = colormap(normed_data)

    model_time=''
    if has_time and d is not None:
        model_time = pd.to_datetime(d.time.values)
        model_time = model_time.strftime('%Y/%m/%d %H')

    return colored_data, lat, lon, vmax, vmin, model_time



