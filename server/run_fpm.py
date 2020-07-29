"""
Alec Vercruysse
2020-07-21

Connect to the uc2 rpi to capture images, get the images, process them
into decent 12-bit png bayer images, and save them as a dataset!

This is mainly needed due to speed and space: The rpi really cannot store
more than a single run of FPM. So we want to have some sort of automatic
way to store the data somewhere local instead of having to do it manually
every time. Also, removing black levels, converting to png, etc. takes
a lot of time on the pi (~1h). We can do better with parallel processing!

Make sure the host in your ~/.ssh/known_hosts file. A good way to do this
is just attempting a connection to the user@host with the private key you
specify in this config.

Unfortunately, this script does not support working in a venv on the remote
pi. This isn't a high priority imo because entire OS images can be swapped
with SD cards, so we can have dedicated SD cards designed for each
application.

TODO: Need to RM all files on pi working folder before we can start
querying which ones are available, otherwise the .done files will be
found and things will be incorrectly downloaded.

"""
import os
import sys
import multiprocessing
from pathlib import Path
from datetime import datetime
import io
import time

import paramiko
import requests
from bs4 import BeautifulSoup

import numpy as np
import png
from PIL import Image
import tifffile as tiff

# ================================== CONFIG ===================================
host = 'uc2pi.attlocal.net'
username = 'pi'
rsa_psk_path = '~/.ssh/uc2pi_key_rsa'

remote_script_path = '/home/pi/UC2-FPM-software/rpi/run_fpm.py'# needs to be absolute
remote_data_path = 'fpm_data'  # subdir of http server root

local_data_dir = '~/Documents/brake_2020_summer/data/fpm_data_{}'.format(
    datetime.today().strftime('%Y-%m-%d'))


new_dataset = True # if false, don't run FPM, just use the files already on the pi
#num_images = 5*64 # ONLY NEEDED WHEN ^^ IS FALSE: when can we stop processing?

# image processing options
remove_dark_level = True
dark_level = 256
# =============================================================================


def run_command(command, client, get_pty=True):
    """
    returns a generator printing stdout
    """
    stdin, stdout, stderr = client.exec_command(command, get_pty=get_pty)
    line_buf = ""
    while not stdout.channel.exit_status_ready():
        if stdout.channel.recv_ready():
            stdoutLine = stdout.readline()
            print(stdoutLine, end="")


def connect_and_run_command(host, username, rsa_psk_path, command):
    # initialize ssh client
    client = paramiko.SSHClient()
    key = paramiko.RSAKey.from_private_key_file(
        Path(rsa_psk_path).expanduser())
    client.load_system_host_keys()
    client.connect(host, username=username, pkey=key)
    transport = client.get_transport()
    transport.set_keepalive(1)  # keep it low (for a clean disconnect)

    # run fpm script remotely
    run_command(command, client)


def download_and_process(url, local_data_dir, name):
    time.sleep(10) # make sure rpi cpu has time to flush io and all that just in case
    print("url: {}\nlocal data dir: {}\nname: {}".format(url, local_data_dir, name))
    raw_response = requests.get(url, stream=True).content
    buf = io.BytesIO(raw_response)
    img_arr = np.load(buf, allow_pickle=True)
    if remove_dark_level:
        img_arr[img_arr < dark_level] = dark_level
        img_arr -= dark_level
    #image_2d = np.reshape(img_arr, (-1, img_arr.shape[1] * 3))
    #print(image_2d.shape)
    path = (Path(local_data_dir) / Path(name)).expanduser()
    print('saving file: {}'.format(path))
    with open(path, "wb") as f:
        # for some reason Pillow can't open 16-bit RGB images.
        # we have to combine chanels ourselves:
        #red = Image.fromarray(img_arr[:, :, 0], mode="I;16").convert("L")
        #green = Image.fromarray(img_arr[:, :, 1], mode="I;16").convert("L")
        #blue = Image.fromarray(img_arr[:, :, 2], mode="I;16").convert("L")
        #Image.merge("RGB", (red, green, blue)).save(path)
        tiff.imwrite(path, img_arr)


def update_remote_file_list(host, remote_data_path):
    url = 'http://' + host + '/' + remote_data_path
    index_page = requests.get(url).text
    soup = BeautifulSoup(index_page, 'html.parser')
    all_paths = [node.get('href') for node in soup.find_all('a')]
    return [
        path for path in all_paths
        if path.endswith('.npy')
        and path.replace('.npy', '.done') in all_paths
    ]


def sync_new_files(host, remote_data_path, existing_paths, local_data_dir):
    new_paths = update_remote_file_list(host, remote_data_path)
    jobs = []
    for path in list(set(new_paths) - set(existing_paths)):
        name = path.replace(".npy", ".tiff")
        url = 'http://' + host + '/' + remote_data_path + '/' + path
        job = multiprocessing.Process(target=download_and_process,
                                      args=(url, local_data_dir, name))
        jobs.append(job)
        job.start()
    return new_paths, jobs


def main():
    print("using remote_script_path: \"{}\"".format(remote_script_path))
    command = "rm /var/www/{}/*; {}".format(remote_data_path, remote_script_path)

    if new_dataset:
        # run the script and wait until completion (show log info)
        ssh_proc = multiprocessing.Process(target=connect_and_run_command,
                                           args=(
                                               host,
                                               username,
                                               rsa_psk_path,
                                               command,
                                           ))
        ssh_proc.start()
    else:
        print("new_dataset false, using existing files...")

    time.sleep(5) # give the pi some time to delete files first
    # look for new files @ http://hostname/fpm_data, download and process
    try:
        os.mkdir(Path(local_data_dir).expanduser())
    except FileExistsError:
        print("WARNING: local data dir already exists. deleteing...")
        for path in Path(local_data_dir).expanduser().glob('*'):
            print("deleting: {}".format(path))
            os.unlink(path)
    paths = []
    jobs = []
    while ssh_proc.is_alive() if new_dataset else len(paths) < num_images:
        paths, newjobs = sync_new_files(host, remote_data_path, paths, local_data_dir)
        jobs.extend(newjobs)
    # run one more time once the script is complete to deal with last file
    paths, newjobs = sync_new_files(host, remote_data_path, paths, local_data_dir)
    jobs.extend(newjobs)
    for job in jobs:
        job.join()
    print("all files processed. exiting...")

    
if __name__ == '__main__':
    main()
