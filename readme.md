This contains the relevant code for the UC2 FPM setup for the HMC Biophotonics lab (summer '20).

 - ~modules~ contains esp32 code (for z-stage and led matrix control via mqtt).
 - ~rpi~ contains the raspberry Pi code (running a mosquitto server and controlling the camera).
 - ~server~ contains the code for the machine processing the data. ~server/run_fpm.py~ is ultimately the code that interfaces with the Pi to capture a dataset.
