#!/bin/bash

inputDir=$1 
#outputFile=${inputFile%.*}
#print(outputFile)


convert -delay 20 $inputDir/*.png $inputDir/animated.gif

#FPS=3 
#WIDTH=1024

# first convert an image sequence to a movie
#ffmpeg -sameq -i ${inputDir}/*.png temp.mp4

# ... and then convert the movie to a GIF animation
#ffmpeg -i temp.mp4 -pix_fmt rgb24 -s qcif -loop_output 0 output.gif

#Generate palette for better quality 
#ffmpeg -i $inputFile -vf fps=$FPS,scale=$WIDTH:-1:flags=lanczos,palettegen tmp_palette.png 
 
#Generate gif using palette 
#ffmpeg -i $inputFile -i tmp_palette.png -loop 0 -filter_complex "fps=$FPS,scale=$WIDTH:-1:flags=lanczos[x];[x][1:v]paletteuse" $outputFile.gif 
 
#rm -f temp.mp4
