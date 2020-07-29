"""
Alec Vercruysse
2020-07-24

Clean up and check images to make sure they're ready for FPM processing.
"""

from pathlib import Path
from datetime import datetime
import multiprocessing
import re
from itertools import chain
import time

import numpy as np
import cv2 as cv
import tifffile as tiff
from PIL import Image
import colour_demosaicing
import psutil

# ================================= CONFIG ====================================
local_data_dir = Path(
    "~/Documents/brake_2020_summer/data/fpm_data_{}_fixed".format(
        datetime.today().strftime('%Y-%m-%d'))).expanduser()

dest_dir = Path(
    "~/Documents/brake_2020_summer/data/in_progress"
).expanduser()

as_uint8 = True # convert read images to 8-bit depth? This is needed to run the
                # devebec script
run_hdr = False
exposure_chosen_idx = 3 # only needed if we don't process them together as hdr

chunksize = 22  # pixel image sets to process at once.
# ============================================================================
def load_images(dirname, pxl, to_dict, as_uint8=False):
    paths = Path(dirname).glob("img{}_*".format(pxl))
    to_dict[pxl] = [
        tiff.imread(str(path)) for path in sorted(
            paths,
            key=lambda x: int( # sort by exposure time
                re.search(r".*img(\d*)_(\d*)us.*", str(x)).group(2)))
    ]
    if as_uint8:
        to_dict[pxl] = [(img >> 4).astype(np.uint8) for img in to_dict[pxl]]

def get_img_info(dirname):
    paths = list(Path(dirname).glob("*"))
    matcher = re.compile(".*img(\d*)_(\d*)us.*")
    matches = [matcher.search(str(path)) for path in paths]
    led_count = max([int(m.group(1)) for m in matches]) + 1
    exposures = sorted(list(set([int(m.group(2)) for m in matches])))
    return led_count, exposures
    
def load_dataset(dirname, indexes=None, as_uint8=False):
    """
    Make sure no other files are in this data dir.
    Including processed files generated with this script.
    """
    paths = list(Path(dirname).glob("*"))
    led_count, exposures = get_img_info(dirname)
    # matcher = re.compile(".*img(\d*)_(\d*)us.*")
    # matches = [matcher.search(str(path)) for path in paths]
    # led_count = max([int(m.group(1)) for m in matches]) + 1
    # exposures = sorted(list(set([int(m.group(2)) for m in matches])))
    print("found images for {} leds".format(led_count))
    print("found {} exposure times: ".format(len(exposures)))
    [print(e, end="\t") for e in exposures]
    print("")
    assert (len(paths) == led_count * len(exposures))
    if indexes == None:
        indexes = range(led_count) # all!!
    with multiprocessing.Manager() as manager:
        procs = []
        loaded_imgs = manager.dict()
        for i in indexes:
            p = multiprocessing.Process(target=load_images,
                                        args=(dirname, i, loaded_imgs, as_uint8))
            p.start()
            procs.append(p)
        for p in procs:
            p.join()
        loaded_imgs = dict(loaded_imgs)
    return (loaded_imgs, exposures)


def prev_cv_img(img):
    """
    For some strangeee reason, openCV stores the image as BGR instead of RGB.
    We need to keep this mind when interfacing with other modules.

    TODO detect and handle grayscale
    """
    Image.fromarray(cv.cvtColor(img, cv.COLOR_BGR2RGB)).show()


def combine_hdr(images, exposures, response = None):
    """
    expects a dict of color images of shape (height, width, channels), 
    and a list of exposures for those respective images.

    https://docs.opencv.org/master/d2/df0/tutorial_py_hdr.html

    expects float32 exposures, in seconds
    """
    try: 
        assert (len(exposures) == len(images) and len(exposures) != 0)
    except AssertionError as a:
        print("len(exposures)= {}\tlen(images)= {}".format(len(exposures), len(images)))
        raise a
    #print("images: type={}, len={}, shape={}".format(type(images), len(images), np.shape(images)))
    #print("exposures: type={}, len={}, shape={}".format(type(exposures), len(exposures), np.shape(exposures)))
    #print("response: type={}, len={}, shape={}".format(type(response), len(response), np.shape(response)))
    images = list(images)
    merge_devebec = cv.createMergeDebevec()
    if response is not None:
        hdr_devebec = merge_devebec.process(images, exposures, response)
    else:
        hdr_devebec = merge_devebec.process(images, exposures)
    #tonemap = cv.createTonemap(gamma=1.0)
    #res_devebec = tonemap.process(hdr_devebec.copy())
    return hdr_devebec

def batch_hdr(image_dict, exposures, response=None):
    """
    generate response and then run combine_hdr in batch.

    https://www.toptal.com/opencv/python-image-processing-in-computational-photography
    """
    exposures = np.float32([e / 1000000 for e in exposures])
    if response is None:
        calibration = cv.createCalibrateDebevec()
        response = calibration.process(image_dict[calibrate_img_idx], exposures)
    result = batch_process(combine_hdr, image_dict, exposures, response)
    return result

def demosaic_channel(img, channel=None):
    if channel == None:  # get color image
        return colour_demosaicing.demosaicing_CFA_Bayer_bilinear(
            np.sum(img, axis=2), 'BGGR').astype(img.dtype)
    else:
        return colour_demosaicing.demosaicing_CFA_Bayer_bilinear(
            img[:, :, channel], 'BGGR').astype(img.dtype)

def hdr_uint_convert(img, dtype, max_val):
    """
    """
    uint_max = np.array(-1, dtype=dtype) # intentional underflow
    #res_nbit = np.clip(img * max_val, 0, max_val).astype(dtype)
    tonemap = cv.createTonemap(gamma=1.0)
    out = tonemap.process(img)
    return (out*uint_max).astype(dtype)
    
def batch_process(func, imgs, *args):
    with multiprocessing.Manager() as manager:
        procs = []
        processed_imgs = manager.dict()
        if type(imgs) == dict:
            iterator = imgs.items()
        else:
            iterator = enumerate(imgs)
        for i, img in iterator:
            while (psutil.virtual_memory().available < 8000000000): # todo make this configurable maybe.
                print("waiting for mem to clear up...")
                time.sleep(1)
            p = multiprocessing.Process(target=_batch_wrapper,
                                        args=(func, i, img, processed_imgs,
                                              *args))
            p.start()
            procs.append(p)
        for p in procs:
            p.join()
        processed_imgs = dict(processed_imgs)
    return processed_imgs

def _batch_wrapper(func, i, img, out_dict, *args):
    out_dict[i] = func(img, *args)

def process_dataset(data, exposures, response, channel):
    for pxl, imgs in data.items():
        data[pxl] = list(batch_process(demosaic_channel, imgs, channel).values())
    if run_hdr:
        images = batch_hdr(data, exposures, response)
        images = batch_process(hdr_uint_convert, images, np.uint16, np.max(list(images.values())))
    else:
        images = {}
        for key in data.keys():
            images[key] = data[key][exposure_chosen_idx]
    for pxl, img in images.items():
        print("writing {}".format(str(dest_dir / Path("img{}.tiff".format(pxl)))))
        tiff.imwrite(str(dest_dir / Path("img{}.tiff".format(pxl))), img[:,:,channel])
        

if __name__ == '__main__':
    led_count, exposures = get_img_info(local_data_dir)
    
    cal_data = {}
    exp = np.float32([e / 1000000 for e in exposures])
    load_images(local_data_dir, 43, cal_data, as_uint8)
    response = cv.createCalibrateDebevec().process(cal_data[43], exp)

    for chunk_start in range(0, led_count, chunksize):
        chunk_end = min(chunk_start + chunksize, led_count)
        print("starting imgs {} -> {}".format(chunk_start, chunk_end - 1))
        data, exposures = load_dataset(local_data_dir, range(chunk_start, chunk_end), as_uint8)
        process_dataset(data, exposures, response, 0) # 0 = red channel
