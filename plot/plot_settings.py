import matplotlib as mpl
import seaborn as sns


def get_var_ranges(variable):
    # Min max value for plotting change (m)
    var_min_delta = {'snowdepthavg': 0.1,
                     'swe': 0.01,
                     'p_snow': 0.01}

    return var_min_delta[variable]

def get_unit(variable):
    ylabel_unit = {'ilwr_out': 'W m-2',
                   'G': 'W m-2',
                   'T_s_0': 'C',
                   't': 'C',
                   'rh': '%',
                   'p': 'm',
                   'ilwr': 'W m-2',
                   'iswr': 'W m-2',
                   'U_2m_above_srf': 'm/s',
                   'vw_dir': 'degrees true north',
                   'swe': 'mm',
                   'snowdepthavg': 'm'}
    return ylabel_unit[variable]

def colormap(variable):

    # Create Colormaps
    colormap = mpl.colors.ListedColormap(get_cmap(variable))
    # colormap.set_under('#669900')  # Use green color for values below the minimum
    return colormap

def get_cmap(variable):
    cmap_dict = {'snowdepthavg': sns.color_palette("YlGnBu", 12),
                 'p_rain': sns.color_palette("Reds", 12),
                 'p_snow':sns.color_palette("Blues", 12),
                 'swe': [   "#ffffff",
                            "#ccf8ff",
                            "#a5d9fa",
                            "#80a4f2",
                            "#5d64e8",
                            "#5b38d9",
                            "#711adb",
                            "#b02bd9",
                            "#e84de0",
                            "#f26fc7",
                            "#fa96bc",
                            "#ffc6c2"
                        ],
                 'snowdepthavg_diff': sns.diverging_palette(10, 240, n=12), # sns.color_palette("RdBu", 12),
                 'swe_diff': sns.diverging_palette(10, 240, n=12)} # sns.color_palette("RdBu", 12)}

    return cmap_dict[variable]

def get_title(variable):
    title_dict = {'snowdepthavg': 'Snowdepth',
                  'swe': 'SWE',
                  'p_snow': 'Snowfall',
                  'p_rain': 'Rainfall',
                  'snowdepthavg_diff': 'Snowdepth change',
                  'swe_diff': 'SWE change'}

    return title_dict[variable]
