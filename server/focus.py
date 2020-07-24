"""
Alec Vercruysse
2020-07-23

Meant to provide a quantitative Figure of Merit for seeing the focus
of the image. Uses the preview from https://elinux.org/RPi-Cam-Web-Interface.
So make sure that's up and running. same package requirements as the run_fpm
script.

continuously prints the variance of each band
"""
import requests
import numpy as np
from PIL import Image
from PIL import ImageStat
import io
from time import sleep
from collections import deque
import subprocess
import os

hostname = 'uc2pi.attlocal.net'
preview = True
crop_center = False

last_vals = deque() # a queue
while (True):
    response = requests.get('http://{}/html/cam_pic.php'.format(hostname))
    buf = io.BytesIO(response.content)
    img = Image.open(buf)
    width = img.size[0]
    height = img.size[1]
    crop_x = (width - height)/2
    if crop_center:
        img = img.crop((crop_x, 0, crop_x + height, height))
    img.save('/tmp/focus.png', "png")
    if preview: viewer = subprocess.Popen(['feh', "/tmp/focus.png"])
    var = ImageStat.Stat(img).var
    if len(last_vals) == 3:
        last_vals.popleft()
    last_vals.append(var)
    print("variance:\t{:8>f}\t{:8>f}\t{:8>f}".format(*np.mean(last_vals, axis=0)))
    sleep(2)
    if preview:
        viewer.terminate()
        viewer.kill()
    
