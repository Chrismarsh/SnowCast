import pandas as pd
import os

class point_forcing(object):
    ''' Class for working with CHM ascii forcing files'''

    def __init__(self, cfile=None, output_dir=None):
        # Load it in
        cfile = open(cfile,'r')
        self.df = pd.read_csv(cfile, sep="\t", parse_dates=True, na_values = -9999)
        cfile.close()
        self.df.set_index('datetime', inplace=True)
        self.df.index = pd.to_datetime(self.df.index)
        self.output_dir = output_dir

    def add_missing_timesteps(self, freq='H'):
        # Reindex to have continuous time steps
        self.df_c = self.df.reindex(pd.date_range(self.df.index[0], self.df.index[-1],
                                          freq=freq))

    def fill_missing_variables(self, method='linear'):
        # Simple linear interpolation along time
        if method == 'linear' or method == 'spline':
            self.df_c = self.df_c.interpolate(method=method, axis=0).ffill().bfill()
        else:
            raise ValueError('Method not found.')

        assert not self.df_c.isnull().values.any()

    def write_to_ascii(self, cfile=None):
        self.df_c.index.name = 'datetime' # This gets dropped so add back in
        file_out = open(os.path.join(self.output_dir, cfile), 'w')
        self.df_c.to_csv(file_out, sep='\t', date_format='%Y%m%dT%H%M%S')
        file_out.close()