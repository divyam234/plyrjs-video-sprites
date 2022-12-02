import subprocess
import shlex
import sys
import logging
import os
import datetime
import math
import glob
import pipes
from dateutil import relativedelta
##################################
# Generate tooltip thumbnail images & corresponding WebVTT file for a video (e.g MP4).
# Final product is one *_sprite.jpg file and one *_thumbs.vtt file.
#
# DEPENDENCIES: required: ffmpeg & imagemagick
#               optional: sips (comes with MacOSX) - yields slightly smaller sprites
#    download ImageMagick: http://www.imagemagick.org/script/index.php OR http://www.imagemagick.org/script/binary-releases.php (on MacOSX: "sudo port install ImageMagick")
#    download ffmpeg: http://www.ffmpeg.org/download.html
# jwplayer reference: http://www.longtailvideo.com/support/jw-player/31778/adding-tooltip-thumbnails/
#
# TESTING NOTES: Tested putting time gaps between thumbnail segments, but had no visual effect in JWplayer, so omitted.
#                Tested using an offset so that thumbnail would show what would display mid-way through clip rather than for the 1st second of the clip, but was not an improvement.
##################################

#TODO determine optimal number of images/segment distance based on length of video? (so longer videos don't have huge sprites)

USE_SIPS = False #True to use sips if using MacOSX (creates slightly smaller sprites), else set to False to use ImageMagick
THUMB_WIDTH=240#100-150 is width recommended by JWPlayer; I like smaller files
SPRITE_NAME = "sprite.jpg" #jpg is much smaller than png, so using jpg
VTTFILE_NAME = "thumbs.vtt"
THUMB_OUTDIR = "thumbs"
USE_UNIQUE_OUTDIR = False #true to make a unique timestamped output dir each time, else False to overwrite/replace existing outdir
logger = logging.getLogger(sys.argv[0])
logSetup=False

class SpriteTask():
    """small wrapper class as convenience accessor for external scripts"""
    def __init__(self,videofile):
        self.remotefile = videofile.startswith("http")
        if not self.remotefile and not os.path.exists(videofile):
            sys.exit("File does not exist: %s" % videofile)
        basefile = os.path.basename(videofile)
        basefile_nospeed = removespeed(basefile) #strip trailing speed suffix from file/dir names, if present
        newoutdir = makeOutDir(basefile_nospeed)
        fileprefix,ext = os.path.splitext(basefile_nospeed)
        spritefile = os.path.join(newoutdir,"%s_%s" % (fileprefix,SPRITE_NAME))
        vttfile = os.path.join(newoutdir,"%s_%s" % (fileprefix,VTTFILE_NAME))
        self.videofile = videofile
        self.vttfile = vttfile
        self.spritefile = spritefile
        self.outdir = newoutdir
    def getVideoFile(self):
        return self.videofile
    def getOutdir(self):
        return self.outdir
    def getSpriteFile(self):
        return self.spritefile
    def getVTTFile(self):
        return self.vttfile

def makeOutDir(videofile):
    """create unique output dir based on video file name and current timestamp"""
    base,ext = os.path.splitext(videofile)
    script = sys.argv[0]
    basepath = os.path.dirname(os.path.abspath(script)) #make output dir always relative to this script regardless of shell directory
    if len(THUMB_OUTDIR)>0 and THUMB_OUTDIR[0]=='/':
        outputdir = THUMB_OUTDIR
    else:
        outputdir = os.path.join(basepath,THUMB_OUTDIR)
    if USE_UNIQUE_OUTDIR:
        newoutdir = "%s.%s" % (os.path.join(outputdir,base),datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    else:
        newoutdir = "%s_%s" % (os.path.join(outputdir,base),"vtt")
    if not os.path.exists(newoutdir):
        logger.info("Making dir: %s" % newoutdir)
        os.makedirs(newoutdir)
    elif os.path.exists(newoutdir) and not USE_UNIQUE_OUTDIR:
        #remove previous contents if reusing outdir
        files = os.listdir(newoutdir)
        print ("Removing previous contents of output directory: %s" % newoutdir)
        for f in files:
            os.unlink(os.path.join(newoutdir,f))
    return newoutdir

def doCmd(cmd,logger=logger):  #execute a shell command and return/print its output
    #logger.info( "START [%s] : %s " % (datetime.datetime.now(), cmd))
    args = shlex.split(cmd) #tokenize args
    output = None
    try:
        output = subprocess.run(args, check=True, capture_output=True, text=True).stdout #pipe stderr into stdout
    except Exception as e:
        ret = "ERROR   [%s] An exception occurred\n%s\n%s" % (datetime.datetime.now(),output,str(e))
        logger.error(ret)
        raise e #todo ?
    ret = "END   [%s]\n%s" % (datetime.datetime.now(),output)
    #logger.info(ret)
    sys.stdout.flush()
    return output

def takesnaps(videofile,newoutdir):
    """
    take snapshot image of video every Nth second and output to sequence file names and custom directory
        reference: https://trac.ffmpeg.org/wiki/Create%20a%20thumbnail%20image%20every%20X%20seconds%20of%20the%20video
    """

    cmd = "ffmpeg -skip_frame nokey -i %s -qscale:v 2 -vsync passthrough %s/tv%%03d.jpg" % (pipes.quote(videofile), pipes.quote(newoutdir))
    doCmd (cmd)
    count = len(os.listdir(newoutdir))
    logger.info("%d thumbs written in %s" % (count,newoutdir))
    #return the list of generated files
    return count,get_thumb_images(newoutdir)

def get_thumb_images(newdir):
    return glob.glob("%s/tv*.jpg" % newdir)

def resize(files):
    """change image output size to 100 width (originally matches size of video)
      - pass a list of files as string rather than use '*' with sips command because
        subprocess does not treat * as wildcard like shell does"""
    if USE_SIPS:
        # HERE IS MAC SPECIFIC PROGRAM THAT YIELDS SLIGHTLY SMALLER JPGs
        doCmd("sips --resampleWidth %d %s" % (THUMB_WIDTH," ".join(map(pipes.quote, files))))
    else:
        # THIS COMMAND WORKS FINE TOO AND COMES WITH IMAGEMAGICK, IF NOT USING A MAC
        doCmd("mogrify -geometry %dx %s" % (THUMB_WIDTH," ".join(map(pipes.quote, files))))

def get_geometry(file):
    """execute command to give geometry HxW+X+Y of each file matching command
       identify -format "%g - %f\n" *         #all files
       identify -format "%g - %f\n" onefile.jpg  #one file
     SAMPLE OUTPUT
        100x66+0+0 - _tv001.jpg
        100x2772+0+0 - sprite2.jpg
        4200x66+0+0 - sprite2h.jpg"""
    geom = doCmd("""identify -format "%%g - %%f\n" %s""" % pipes.quote(file))
    parts = geom.split("-",1)
    return parts[0].strip() #return just the geometry prefix of the line, sans extra whitespace

def get_frametime(file):
    timestamps = doCmd("""ffprobe -loglevel error -select_streams v:0 -show_entries packet=pts_time,flags -of csv=print_section=0 %s""" % pipes.quote(file)).split('\n')
    keyframes=list(map(lambda y : y.split(',')[0],filter(lambda x: x.find('K')!=-1,timestamps)))
    keyframes.append(timestamps[-2].split(',')[0])
    return keyframes

def makevtt(spritefile,numsegments,keyframes,coords,gridsize,writefile):
    """generate & write vtt file mapping video time to each image's coordinates
    in our spritemap"""
    #split geometry string into individual parts
    ##4200x66+0+0     ===  WxH+X+Y
    wh,xy = coords.split("+",1)
    w,h = wh.split("x")
    w = int(w)
    h = int(h)
    #x,y = xy.split("+")

    basefile = os.path.basename(spritefile)
    vtt = ["WEBVTT",""] #line buffer for file contents
    # NOTE - putting a time gap between thumbnail end & next start has no visual effect in JWPlayer, so not doing it.
    clipstart=float(keyframes[0])
    for imgnum in range(0,numsegments):
        xywh = get_grid_coordinates(imgnum,gridsize,w,h)
        start = get_time_str(clipstart)
        end  = get_time_str(float(keyframes[imgnum+1]))
        clipstart = float(keyframes[imgnum+1])
        vtt.append(str(imgnum))
        vtt.append("%s --> %s" % (start,end)) #00:00.000 --> 00:05.000
        vtt.append("%s#xywh=%s" % (basefile,xywh))
        vtt.append("") #Linebreak
    vtt =  "\n".join(vtt)
    #output to file
    writevtt(writefile,vtt)

def get_time_str(numseconds,adjust=None):
    """ convert time in seconds to VTT format time (HH:)MM:SS.ddd"""
    if adjust: #offset the time by the adjust amount, if applicable
        seconds = max(numseconds + adjust, 0) #don't go below 0! can't have a negative timestamp
    else:
        seconds = numseconds
    delta = relativedelta.relativedelta(seconds=seconds)
    return "%02d:%02d:%02d.000" % (delta.hours,delta.minutes, delta.seconds)

def get_grid_coordinates(imgnum,gridsize,w,h):
    """ given an image number in our sprite, map the coordinates to it in X,Y,W,H format"""
    x= int(imgnum % gridsize);
    y = int(imgnum /gridsize)
    imgx = x * w
    imgy =y * h
    return "%s,%s,%s,%s" % (imgx,imgy,w,h)

def makesprite(outdir,spritefile,coords,gridsize):
    """montage _tv*.jpg -tile 8x8 -geometry 100x66+0+0 montage.jpg  #GRID of images
           NOT USING: convert tv*.jpg -append sprite.jpg     #SINGLE VERTICAL LINE of images
           NOT USING: convert tv*.jpg +append sprite.jpg     #SINGLE HORIZONTAL LINE of images
     base the sprite size on the number of thumbs we need to make into a grid."""
    grid = "%dx%d" % (gridsize,gridsize)
    cmd = "montage %s/tv*.jpg -tile %s -geometry %s %s" % (pipes.quote(outdir), grid, coords, pipes.quote(spritefile))#if video had more than 144 thumbs, would need to be bigger grid, making it big to cover all our case
    doCmd(cmd)

def writevtt(vttfile,contents):
    """ output VTT file """
    with open(vttfile,mode="w") as h:
        h.write(contents)
    logger.info("Wrote: %s" % vttfile)

def removespeed(videofile):
    """some of my files are suffixed with datarate, e.g. myfile_3200.mp4;
     this trims the speed from the name since it's irrelevant to my sprite names (which apply regardless of speed);
     you won't need this if it's not relevant to your filenames"""
    videofile = videofile.strip()
    speed = videofile.rfind("_")
    speedlast = videofile.rfind(".")
    maybespeed = videofile[speed+1:speedlast]
    try:
        int(maybespeed)
        videofile = videofile[:speed] + videofile[speedlast:]
    except:
        pass
    return videofile

def run(task):
    addLogging()
    outdir = task.getOutdir()
    spritefile = task.getSpriteFile()

    #create snapshots
    numfiles,thumbfiles = takesnaps(task.getVideoFile(),outdir)
    #resize them to be mini
    resize(thumbfiles)

    #get key frames time

    keyframes=get_frametime(task.getVideoFile())

    #get coordinates from a resized file to use in spritemapping
    gridsize = int(math.ceil(math.sqrt(numfiles)))
    coords = get_geometry(thumbfiles[0]) #use the first file (since they are all same size) to get geometry settings

    #convert small files into a single sprite grid
    makesprite(outdir,spritefile,coords,gridsize)

    #generate a vtt with coordinates to each image in sprite
    makevtt(spritefile,numfiles,keyframes,coords,gridsize,task.getVTTFile())

def addLogging():
    global logSetup
    if not logSetup:
        basescript = os.path.splitext(os.path.basename(sys.argv[0]))[0]
        LOG_FILENAME = 'logs/%s.%s.log'% (basescript,datetime.datetime.now().strftime("%Y%m%d_%H%M%S")) #new log per job so we can run this program concurrently
        #CONSOLE AND FILE LOGGING
        print ("Writing log to: %s" % LOG_FILENAME)
        if not os.path.exists('logs'):
            os.makedirs('logs')
        logger.setLevel(logging.DEBUG)
        handler = logging.FileHandler(LOG_FILENAME)
        logger.addHandler(handler)
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        logger.addHandler(ch)
        logSetup = True #set flag so we don't reset log in same batch


if __name__ == "__main__":
    if not len(sys.argv) > 1 :
        sys.exit("Please pass the full path or url to the video file for which to create thumbnails.")
    if len(sys.argv) == 3:
        THUMB_OUTDIR = sys.argv[2]
    videofile = sys.argv[1]
    task = SpriteTask(videofile)
    run(task)
