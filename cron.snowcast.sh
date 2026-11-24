
cd ~/project/Snowcast-www-v2/SnowCast
spack env activate .

(
  snowcast run projects/western-cordillera &&
  snowcast publish sites/snowcast.json --project western-cordillera
) &

(
  snowcast run projects/tvc &&
  snowcast publish sites/snowcast.json --project tvc
) &

wait

