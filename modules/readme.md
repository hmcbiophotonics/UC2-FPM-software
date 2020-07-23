* Module Code
This directory contains the arduino code that is used for the Z-stage and LED matrix esp32s.

 - [follow this tutorial to set up the esp32 on the arduino IDE](https://randomnerdtutorials.com/installing-the-esp32-board-in-arduino-ide-windows-instructions/)
   - This contains the board manager link you need to add
   - The HILETGO boards we bought from amazon seem to work as Node32s boards.
 - For both esp32s:
   - you need to create a "secrets.h" file (not tracked by git) with two defines: `SSID` and `PASSWORD`. This is so that your network ssid/password will not get uploaded to github.
   - need to install `PubSubClient`
   - try the test wifi scanning sketch to ensure everything works. I had to hold down the boot switch until the arduino IDE tried to connect to the esp32 to get the connection to work.
   - Read up on the MQTT api [here](http://mosquitto.org/man/mqtt-7.html).
 - For the LED matrix esp32:
   - The regular `Adafruit_neomatrix` lib won't work (see [adafruit/Adafruit_NeoPixel#139](https://github.com/adafruit/Adafruit_NeoPixel/issues/139)).
   - Need to install https://github.com/marcmerlin/FastLED_NeoMatrix] (and dependencies: `Adafruit_GFX`, `FastLED`, https://github.com/marcmerlin/Framebuffer_GFX).
   - connect the 5v/ground rails to those of the neopixel, and the data pin to pin 26 of the esp32
 - For the zstage esp32:
   - Do not try to power the stepper motor driver from the esp32.
     - The stepper motor driver board takes 5-12V, but you want to keep it as close to 5V as possible otherwise the 3.3v esp32 signals won't register.
     - `IN1-->IN4` were assigned to `P25-->P14`, respectively.

Please update this documentation with any PRs.
