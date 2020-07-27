#!/usr/bin/env python3
"""
Alec Vercruysse
2020-07-21

Run the _minimal_ capture code (to make a capture as fast as possible) needed to get 12-bit bayer data
from the rpi camera. This script should be run by a script on a server that actually unpacks and
converts the bayer data into a decent dataset easily uploadable to google drive.

Again, this should capture all data to a folder in /www/var, so that all files can be hosted on an
apache server (make sure that's running too! Installing RPi_Cam_Web_Interface also intalls a server
with the correct defaults. In the case of this install, make sure you don't autostart the camera on
boot otherwise this script will be unable to open the camera.

Make sure the user running this script has ownership or write access to www/var.
You can use 'sudo chown pi /www/var' or 'sudo chmod 777 /www/var' for the default user pi.

It might be helpful to pipe the logs to a log file that the parent process can read.
"""

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s :: %(levelname)s :: %(message)s')

import os
import sys
from pathlib import Path
logging.info("using python executable: {}".format(sys.executable))

sys.path.insert(0,"/home/pi/picamera")
import picamera
import picamera.array
logging.info("using picamera from (make sure it's the git repo): {}".format(picamera.__file__))
logging.info("using picamera.array from (make sure it's the git repo): {}".format(picamera.array.__file__))

import time
import paho.mqtt.client as mqtt
import numpy as np
from PIL import Image

# ====================================== configure these values ====================================
mqtt_host_ip = "localhost"
mqtt_client_id = "pi"
setup_id = "FPMSCOPE"
ledmatrix_id = "LEDMATRIX"
ledmatrix_pxl_count = 64
exposure_times = [1000, 5000, 10000, 100000, 100000] # in us
analog_gain = 1                        # 1--highest read noise, highest dynamic range
digital_gain = 1
base_folder_path = "/var/www/" # probably what you want if you're hosting these files on a webserver.
# ==================================================================================================

os.chdir(base_folder_path) # need to ensure the user running this script has access! e.g. chown/chmod
try:
    dir_name = "fpm_data"
    os.mkdir(dir_name)
except FileExistsError:
    # we don't want to have more than one dataset at a time on the pi (space constraints)
    #if input("FPM data dir already exists. Type yes to overwrite: ") != "yes":
    #   raise SystemExitm ("\"yes\" not inputted, exiting...")
    logging.warning("FPM data dir already exists. deleteing all files in it...")
    for path in Path(dir_name).glob('*'):
        logging.warning("del: {}".format(path))
        path.unlink()
os.chdir(dir_name)

try:
    camera = picamera.PiCamera(sensor_mode=0)
except picamera.exc.PiCameraMMALError:
    console.critical("MMAL error. Most likely another process has acess to the camera.")
    raise SystemExit

camera.analog_gain = analog_gain
camera.digital_gain = digital_gain
camera.exposure_mode = 'off'
start_time = time.time()

client = mqtt.Client(mqtt_client_id)
client.connect(mqtt_host_ip)
ledmatrix_topic = "/{}/{}/".format(setup_id, ledmatrix_id)
_, matrix_stat_mid = client.subscribe(ledmatrix_topic + "STAT")
if matrix_stat_mid is None:
    logging.critical('error: unable to subscribe to {}STAT'.format(ledmatrix_topic))
    sys.quit()

client.publish(ledmatrix_topic + "RECM" , "CLEAR")
# TODO: publish some sort of DONE on /STAT when CLEAR completes
# so we don't have to wait an arbitrary amount of time
time.sleep(2) 

message_awk = True
ledmatrix_stat = 1
def ledmatrix_stat_callback(client, userdata, message):
    global message_awk
    logging.info("stat_callback: Received message '" + str(message.payload) + "' on topic '"
          + message.topic + "' with QoS " + str(message.qos))
    if message.payload == b"PXL DONE":
        message_awk = True
    elif message.payload = b"0":
        ledmatrix_stat = 0
    elif message.payload =b"1":
        ledmatrix_stat = 1

def set_led_and_wait(i, rgb):
    global message_awk
    if message_awk == False:
        logging.critical("message_awk is False, so a message is already in progress.")
        raise ValueError("message_awk is False, so a message is already in progress.")
    message_awk = False
    client.publish(ledmatrix_topic + "RECM", "PXL+{}+{}+{}+{}".format(i, *rgb))
    while not message_awk:
        if ledmatrix_stat = 0:
            while not ledmatrix_stat:
                time.sleep(0.1)
            client.publish(ledmatrix_topic + "RECM", "PXL+{}+{}+{}+{}".format(i, *rgb))
        time.sleep(0.1)

def on_message(client, userdata, message):
    logging.info("fallback on_message: Received message '" + str(message.payload) + "' on topic '"
          + message.topic + "' with QoS " + str(message.qos))
    
client.message_callback_add(ledmatrix_topic + "STAT", ledmatrix_stat_callback)
client.on_message = on_message
client.loop_start()
logging.info("ag: {}\t dg: {}".format(camera.analog_gain, camera.digital_gain))
for pxl_idx in range(ledmatrix_pxl_count):
    with picamera.array.PiBayerArray(camera) as output:
        logging.info("starting pxl {}...".format(pxl_idx))
        set_led_and_wait(pxl_idx, (255, 0, 0))
        for exposure_time in exposure_times:
            camera.shutter_speed = exposure_time
            camera.capture(output, 'jpeg', bayer=True)
            np.save("img{}_{}us".format(pxl_idx, exposure_time), output.array)
            logging.info("{}u exposure complete.".format(exposure_time))
            Path("img{}_{}us.done".format(pxl_idx, exposure_time)).touch()
        set_led_and_wait(pxl_idx, (0, 0, 0))
logging.info("finished in: {}s".format(time.time() - start_time))
