import itertools
import uuid
from concurrent import futures
from functools import partial
import sys
import branca
import branca.colormap as cm
import folium
import matplotlib as mpl
import numpy as np
import os
import pandas as pd
import subprocess
import xarray as xr
import time as timer
from branca.element import MacroElement
from collections import OrderedDict
from folium.utilities import parse_options
from jinja2 import Template
import rioxarray as rio
from tqdm import tqdm



from mpi4py import MPI

import plot.plot_settings as plot_settings

ROBUST_PERCENTILE = 0.02  # follows xarray's robust 98% - 2%

# This is copied here so-as to fix this problem
# https://github.com/python-visualization/branca/issues/89
class LinearColormap(cm.LinearColormap):
    def __init__(self, colors, index=None, vmin=0., vmax=1., caption=''):
        super(LinearColormap, self).__init__(colors=colors,vmin=vmin, vmax=vmax,
                                             caption=caption)
    _template = Template("""
    {% macro script(this, kwargs) %}
    var {{this.get_name()}} = {};

    {%if this.color_range %}
    {{this.get_name()}}.color = d3.scale.threshold()
              .domain({{this.color_domain}})
              .range({{this.color_range}});
    {%else%}
    {{this.get_name()}}.color = d3.scale.threshold()
              .domain([{{ this.color_domain[0] }}, {{ this.color_domain[-1] }}])
              .range(['{{ this.fill_color }}', '{{ this.fill_color }}']);
    {%endif%}

    {{this.get_name()}}.x = d3.scale.linear()
              .domain([{{ this.color_domain[0] }}, {{ this.color_domain[-1] }}])
              .range([0, 400]);

    {{this.get_name()}}.legend = L.control({position: 'topright'});
    {{this.get_name()}}.legend.onAdd = function (map) {var div = L.DomUtil.create('div', 'legend'); return div};
    {{this.get_name()}}.legend.addTo({{this._parent.get_name()}});

    {{this.get_name()}}.xAxis = d3.svg.axis()
        .scale({{this.get_name()}}.x)
        .orient("top")
        .tickSize(1)
        .tickValues({{ this.tick_labels }});

    {{this.get_name()}}.svg = d3.select(".legend.leaflet-control").append("svg")
        .attr("id", 'legend')
        .attr("width", 450)
        .attr("height", 40);

    {{this.get_name()}}.g = {{this.get_name()}}.svg.append("g")
        .attr("class", "key")
        .attr("transform", "translate(25,16)");

    {{this.get_name()}}.g.selectAll("rect")
        .data({{this.get_name()}}.color.range().map(function(d, i) {
          return {
            x0: i ? {{this.get_name()}}.x({{this.get_name()}}.color.domain()[i - 1]) : {{this.get_name()}}.x.range()[0],
            x1: i < {{this.get_name()}}.color.domain().length ? {{this.get_name()}}.x({{this.get_name()}}.color.domain()[i]) : {{this.get_name()}}.x.range()[1],
            z: d
          };
        }))
      .enter().append("rect")
        .attr("height", 10)
        .attr("x", function(d) { return d.x0; })
        .attr("width", 1.5)
        .style("fill", function(d) { return d.z; });

    {{this.get_name()}}.g.call({{this.get_name()}}.xAxis).append("text")
        .attr("class", "caption")
        .attr("y", 21)
        .text('{{ this.caption }}');
{% endmacro %}
""")

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

def make_colour_txt(var, vmin, vmax, mangle, n=12):
    colors = plot_settings.get_cmap(var)
    r = np.linspace(vmin, vmax, n)
    fname = f'color_{var}_{mangle}.txt'
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

def _gdal_prefix():
    try:
        prefix = subprocess.run(["gdal-config","--prefix"], stdout=subprocess.PIPE).stdout.decode()
        prefix = prefix.replace('\n', '')

        return prefix

    except FileNotFoundError as e:
        raise(""" ERROR: Could not find the system install of GDAL. 
                  Please install it via your package manage of choice.
                """)


def make_map(settings, df):

    minZoom = 0
    maxZoom = 12

    # the lat long in the df isn't /quite/ right but close enough for this
    m = folium.Map(location=[df.lat.mean(), df.lon.mean()], zoom_start=8, tiles=None, control_scale=True, zoom_control=True, max_zoom=maxZoom, min_zoom=minZoom)
    folium.TileLayer('Stamen Terrain', control=False, overlay=True, max_zoom=maxZoom, min_zoom=minZoom).add_to(m) # overlay=True is important to allow it to be drawn over and not replaced

    layer_attr = 'University of Saskatchewan, Global Water Futures'

    # figure out the vmin/vmax for plotting
    for var in list(df.index.levels[0].values):
        tiffs = list(df.loc[var].tiff.values)

        rasters = [rio.open_rasterio(x, masked=True, chunks=True, lock=False) for x in tiffs]
        ds = xr.concat(rasters, dim='time')

        # fixes
        # dimension time on 0th function argument to apply_ufunc with dask='parallelized' consists of multiple chunks, but is also a core dimension.
        ds = ds.chunk(dict(time=-1, y=-1, x=-1))

        # Gets the robust percentile range across multiple tiffs, follows mpl's routine
        vmax = float(ds.quantile(1.0 - ROBUST_PERCENTILE, dim=['time', 'y', 'x']))
        vmin = float(ds.quantile(ROBUST_PERCENTILE, dim=['time', 'y', 'x']))

        if '_diff' in var:
            # because this is a difference it should be centred around zero
            max_range = np.max([abs(vmax), abs(vmin)])
            vmax = np.sign(vmax) * max_range
            vmin = np.sign(vmin) * max_range

        df.loc[var, 'vmin'] = vmin
        df.loc[var, 'vmax'] = vmax


    for idx, row in df.iterrows():

        #this has the MPI call in it
        make_tiles(settings, row['tiff'], idx[0], row['datetime'], row['vmax'], row['vmin'], minZoom=0, maxZoom=12)

        vmin = row.vmin
        vmax = row.vmax

        model_time = idx[1].strftime('%Y/%m/%d %H:00 UTC')
        var = idx[0]

        if '_diff' in var:
            name = 'Predicted change in ' + plot_settings.get_title(var) + (' (%s)' % plot_settings.get_unit(var))
        else:
            name = plot_settings.get_title(var)
            if idx[1].hour == 1: # "now" is 01h, future is 23h
                name = '%s (%s) - Current %s' % (name, plot_settings.get_unit(var), model_time)
            else:
                name = '%s (%s) - Forecast for %s' % (name, plot_settings.get_unit(var), model_time)

        TL = folium.raster_layers.TileLayer(
            os.path.join('./tiles', f"""tiles_{var}_{row['datetime']}""",'{z}/{x}/{y}.png'),
            minZoom=minZoom, maxZoom=maxZoom,
            attr=layer_attr,
            name=name,
            opacity=0.6,
            overlay=False,
            tms=True,
            show=True if idx[1].hour == 1 and var == 't' else False).add_to(m) #snowdepthavg
        colormap = LinearColormap(colors=plot_settings.get_cmap(var), vmin=vmin, vmax=vmax)
        colormap.caption = '%s (%s)' % (plot_settings.get_title(var), plot_settings.get_unit(var))

        m.add_child(colormap)
        m.add_child(BindColormapTileLayer(TL, colormap))

    m.add_child(FavIcon())

    folium.LayerControl(collapsed=False).add_to(m)

    m.save(os.path.join(settings['html_dir'],'index.html'))


def make_tiles(settings, tiff, var, time, vmax, vmin, minZoom, maxZoom):
    colormap = None
    mangle = uuid.uuid4().hex[:8]

    if time == 'diff':
        colormap = make_colour_txt(f'{var}_diff', vmin, vmax, mangle, n=12)
    else:
        colormap = make_colour_txt(var, vmin, vmax, mangle, n=12)
    exec = f'gdaldem color-relief {tiff} {colormap} temp_color_{mangle}.vrt -alpha'
    subprocess.check_call([exec], shell=True)
    tile_path = os.path.join(settings['html_dir'], 'tiles', f'tiles_{var}_{time}')

    if 'plotgen_exec_str' in settings:
        exec_str = f"""{settings['plotgen_exec_str']} temp_color_{mangle}.vrt --mpi -w leaflet -z {minZoom}-{maxZoom} {tile_path} False"""
        print(exec_str)
        subprocess.check_call([exec_str], shell=True, cwd=os.path.join(settings['snowcast_base']))
    else:
        comm = MPI.COMM_SELF.Spawn(sys.executable,
                               args=[os.path.join('plot','MPI_gdal2tiles.py'),
                                     f'temp_color_{mangle}.vrt',
                                     '--mpi',
                                     '-w', 'leaflet',
                                     '-z', f'{minZoom}-{maxZoom}',
                                     tile_path],
                               maxprocs=settings['plotgen_maxprocs'])

        comm.Disconnect()


    os.remove(f'temp_color_{mangle}.vrt')
    os.remove(colormap)

