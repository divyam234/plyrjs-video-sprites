#!/usr/bin/python
import sys
import makesprites
import shutil
import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed

OUTPUT_FOLDER = "out"

MAX_WORKERS=4

if not len(sys.argv) > 1 :
    sys.exit("Please pass the full path to file containing the video list for which to create thumbnails.")

def copyFile(origfile,output_folder):
    thefile = os.path.basename(origfile)
    outputFolder = os.path.join(OUTPUT_FOLDER,output_folder)
    if not os.path.exists(outputFolder):
        try:
            os.makedirs(outputFolder)
        except:
            pass
    outfile = os.path.join(outputFolder,thefile)
    shutil.copy(origfile,outfile)



def generate_sprite(file_path,output_folder):
    task = makesprites.SpriteTask(file_path)
    makesprites.run(task)
    spritefile = task.getSpriteFile()
    vttfile = task.getVTTFile()
    copyFile(spritefile,output_folder)
    copyFile(vttfile,output_folder)

def main(video_list):
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
          futures=[]
          for video in video_list:
            futures.append(executor.submit(generate_sprite,video))
          for future in as_completed(futures):
            print(future.result())

if __name__ == "__main__":
    video_list=[]
    main(video_list)
