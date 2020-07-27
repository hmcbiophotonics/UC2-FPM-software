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
    "~/Documents/brake_2020_summer/data/fpm_data_2020-07-24".format(
        datetime.today().strftime('%Y-%m-%d'))).expanduser()

dest_dir = Path(
    "~/Documents/brake_2020_summer/data/in_progress"
).expanduser()
# ============================================================================
def load_images(dirname, pxl, to_dict):
    paths = Path(dirname).glob("img{}_*".format(pxl))
    # the -1 flag makes it return a 16-bit image (instead of 8-bit)
    to_dict[pxl] = [
        tiff.imread(str(path)) for path in sorted(
            paths,
            key=lambda x: int( # sort by exposure time
                re.search(r".*img(\d*)_(\d*)us.*", str(x)).group(2)))
    ]


def load_dataset(dirname, indexes=None):
    paths = list(Path(dirname).glob("*"))
    matcher = re.compile(".*img(\d*)_(\d*)us.*")
    matches = [matcher.search(str(path)) for path in paths]
    led_count = max([int(m.group(1)) for m in matches]) + 1
    exposures = sorted(list(set([int(m.group(2)) for m in matches])))
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
                                        args=(dirname, i, loaded_imgs))
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
    expects a list of color images of shape (height, width, channels), 
    and a list of exposures for those respective images.

    https://docs.opencv.org/master/d2/df0/tutorial_py_hdr.html

    FIXME: I sometimes get a malloc() and then my python core dumps.....?
    I think it's only when I call it wrong though...
    """
    assert (len(exposures) == len(images) and len(exposures) != 0)
    exposures = np.float32([1/e for e in exposures])
    merge_devebec = cv.createMergeDebevec()
    if response:
        hdr_devebec = merge_devebec.process(src=images, times=exposures, response=response)
    else:
        hdr_devebec = merge_devebec.process(src=images, times=exposures)
    tonemap = cv.createTonemap(gamma=1.0)
    res_devebec = tonemap.process(hdr_devebec.copy())
    #max_val = np.array(-1, dtype=images[0].dtype) # intentional underflow
    #res_nbit = np.clip(res_devebec * max_val, 0, max_val).astype(images[0].dtype)
    return res_devebec

def batch_hdr(image_dict, exposures, calibrate_img_idx):
    """
    generate response and then run combine_hdr in batch.

    https://www.toptal.com/opencv/python-image-processing-in-computational-photography
    """
    #flat_imgs = list(chain(*content.values()))
    #flat_exposures = np.array([exposures for _ in range(len(image_dict))]).flatten().astype(np.float32)
    cv_exposures = np.float32([1/e for e in exposures])
    response = cv.createCalibrateDebevec().process(image_dict[calibrate_img_idx], cv_exposures)
    result = batch_process(combine_hdr, image_dict.values(), exposures)
    return result

def demosaic_channel(img, channel=None):
    if channel == None:  # get color image
        return colour_demosaicing.demosaicing_CFA_Bayer_bilinear(
            np.sum(img, axis=2), 'BGGR').astype(img.dtype)
    else:
        return colour_demosaicing.demosaicing_CFA_Bayer_bilinear(
            img[:, :, channel], 'BGGR').astype(img.dtype)


def batch_process(func, imgs, *args):
    with multiprocessing.Manager() as manager:
        procs = []
        processed_imgs = manager.dict()
        for i, img in enumerate(imgs):
            while (psutil.virtual_memory().available < 8000000000):
                print("waiting for mem to clear up...")
                time.sleep(1)
            p = multiprocessing.Process(target=_batch_wrapper,
                                        args=(func, i, img, processed_imgs,
                                              *args))
            p.start()
            procs.append(p)
        for p in procs:
            p.join()
        # for i, img in enumerate(processed_imgs):
        #     cv.imwrite(str(dest_dir / Path("img{}.hdr".format(i))), processed_imgs[i])
        #     processed_imgs[i] = None
        processed_imgs = dict(processed_imgs)
    return processed_imgs # [img for _, img in sorted(processed_imgs.items())]


def _batch_wrapper(func, i, img, out_dict, *args):
    out_dict[i] = func(img, *args)


def process_dataset(data, exposures, best_pxl):
    for pxl, imgs in data.items():
        data[pxl] = batch_process(demosaic_channel, imgs, 0)
    images = batch_hdr(data, exposures, best_pxl)
    for pxl, img in images.values():
        tiff.save(str(local_data_dir / Path("img{}.tiff".format(pxl))))
        

if __name__ == '__main__':
    data, exposures = load_dataset(local_data_dir, range(32))
    process_dataset(data, exposures, 31)
    data, exposures = load_dataset(local_data_dir, range(32, 64))
    process_dataset(data, exposures, 43)
