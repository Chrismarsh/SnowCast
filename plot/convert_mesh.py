import CHM as pc

def filter_output(settings):

    pvd = settings['chm_outpath']
    dxdy = settings['dxdy']

    df = pc.pvd_to_xarray(pvd, dxdy=dxdy)

    # get last 24 hr period
    s = df.isel(time=[-48, -1])

    # build up the list of variables we have
    all_var = set([x for x in s.data_vars.keys()])
    keep_var = set(settings['plot_vars'])

    # figure out what to drop
    drop = all_var - keep_var
    s = s.drop_vars(drop)



    return s


