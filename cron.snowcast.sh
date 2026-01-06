
cd /home/chm003/project/Snowcast-www/SnowCast
spack env activate .
# echo `which python`
#   --no-met --no-chm --no-postprocess --no-plot
python snowcast.py  -c config_hrdps_west.py


