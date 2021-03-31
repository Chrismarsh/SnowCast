import pandas as pd
import cartopy.crs as ccrs
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
import os
import numpy as np
import matplotlib.pyplot as plt

# Plot setup
def make_map(projection=ccrs.PlateCarree()):
    fig, ax = plt.subplots(subplot_kw=dict(projection=projection))
    fig.set_size_inches(20, 12)
    #ax.coastlines(resolution='100m', zorder=1)

    gl = ax.gridlines(crs=ccrs.PlateCarree(), draw_labels=True,
                       linewidth=2, color='gray', alpha=0.4, linestyle='--')
    gl.top_labels = gl.right_labels = False
    gl.xformatter = LONGITUDE_FORMATTER
    gl.yformatter = LATITUDE_FORMATTER
    gl.xlabel_style = {'size': 'medium'}
    gl.ylabel_style = {'size': 'medium'}

    return fig, ax


def save_figure(f, file_out, fig_res):
    f.savefig(file_out, bbox_inches='tight', dpi=fig_res)


def plot_variable(df):
    # Make map
    fig, ax = make_map()
    var2plot = df.name

    p1 = df.plot.pcolormesh(x='lon', y='lat',
                                   ax=ax,
                                   robust=True, #colormap range is computed with 2nd and 98th percentiles
                                   cmap=get_cmap(var2plot),
                                   add_colorbar=False
                                   )

    # Make tri plot
    # p1 = ax.tripcolor(tri_info['Lon'], tri_info['Lat'], tri_info['triang'],
    #                   facecolors=tri_var * scale_factor[var2plot],
    #                   cmap=cmap_dict[var2plot],
    #                   vmin=var_vmin * scale_factor[var2plot],
    #                   vmax=var_vmax * scale_factor[var2plot])

    # # Add title
    # if time_start:
    #     ax.set_title(title_dict[var2plot] + '.\n' + str_time_start + ' to\n' + str_timestamp + '\n')
    # else:
    c_timestamp = df.time.values
    str_timestamp = pd.to_datetime(c_timestamp).strftime('%Y-%m-%d %H:%M:%S MST')

    ax.set_title(get_title(var2plot) + '\n' + str_timestamp + '\n')

    # # Plot scatter of Obs (if exists)
    # if obs_pts is not None:
    #     if (obs_pts.notnull().sum() > 0):
    #         p2 = ax.scatter(obs_pts.Lon, obs_pts.Lat, s=200,
    #                         c=obs_pts.values * scale_factor[var2plot], zorder=500,
    #                         cmap=cmap_dict[var2plot],
    #                         vmin=var_vmin * scale_factor[var2plot],
    #                         vmax=var_vmax * scale_factor[var2plot],
    #                         edgecolors='k', linewidths=2)

    # Add landmarks
    # ax.add_geometries(p_sh, ccrs.PlateCarree(),
    #                   edgecolor='black', facecolor='none', alpha=0.5)  # AB/BC boarder

    # Town/Cites
    t_lat = [51.089682, 51.177924, 51.426574, 51.268964, 51.394761]
    t_lon = [-115.360909, -115.570507, -116.18042, -115.919495, -116.49353]
    t_name = ['Canmore', 'Banff', 'Lake Louise', 'Castle Junction', 'Field']
    ax.scatter(t_lon, t_lat, c='k', s=300, marker='*')
    for i, txt in enumerate(t_name):
        ax.annotate(txt, (t_lon[i] + 0.01, t_lat[i] + 0.01), fontsize=20)

    # Add colorbar
    b1 = fig.colorbar(p1)
    b1.ax.set_ylabel(get_ylabel(var2plot))

    # Set map extent
    c_extent = [df.lon.values[~np.isnan(df.values)].min(),
                df.lon.values[~np.isnan(df.values)].max(),
                df.lat.values[~np.isnan(df.values)].min(),
                df.lat.values[~np.isnan(df.values)].max()]
    ax.set_extent(c_extent, ccrs.PlateCarree())

    # Add legend
    # if obs_pts is not None:
    #     obs_artist = plt.Line2D((0, 1), (0, 0), color='k', marker='o', linestyle='')
    #     ax.legend([obs_artist], ['Observed'], loc='upper right')

    # Save figure
    # if time_start:
    #     file_out = os.path.join(fig_dir, var2plot + '.png')
    # else:
    #     file_out = os.path.join(fig_dir, var2plot, var2plot + '_' + file_timestamp)
    # save_figure(fig, file_out, fig_res)
    return fig


def plot(settings, data):

    mpl.use('Agg')
    fig_res = settings['dpi']

    for var2plot in settings['plot_vars']:
        df = data.isel(time = -1)[var2plot] # plot the last time as we have 2 time at this point

        # df_trim = df[ np.abs(df - df.mean()) <= (3 * df.std())]  # Remove outliers (sometimes from avalnching)
        # df_cvar_max = np.max([np.abs(df_trim.min()), df_trim.max()])  # Use larger of neg or pos values
        # df_cvar_max = np.max([df_cvar_max, var_min_delta[var2plot]])  # Min max delta value
        # df_cvar_min = -1 * df_cvar_max

        fig = plot_variable(df)

        file_timestamp = str(pd.to_datetime(data.time.values[-1]).strftime('%Y_%m_%d_%H:%M:%S_MST'))
        base_dir = os.path.join(settings['fig_dir'], var2plot)
        if not os.path.exists(base_dir):
            os.mkdir(base_dir)
        file_out = os.path.join(base_dir, var2plot + '_' + file_timestamp + '.png')

        save_figure(fig, file_out, fig_res)