
// ----------- ----------- ----------- ----------- ----------- -----------
// ESP32 script to accept MQTT commands for UC2-control
// by: Rene Lachmann
// date: 11.09.2019
// based on Arduino-Interface by Rene Lachmann, Xavier Uwurukundu
// fixes:
//		> 20.01.2020 Ientercept based correcd display updating -> Thomas Combriat (Oslo)
//----------- ----------- ----------- ----------- ----------- -----------

// ----------------------------------------------------------------------------------------------------------------
//                          INCLUDES
#include <WiFi.h>
#include <PubSubClient.h>
#include <string.h>
#include <vector>
#include "Adafruit_GFX.h"
#include <FastLED_NeoMatrix.h> // #include "Adafruit_NeoMatrix.h"
#include <FastLED.h> // #include "Adafruit_NeoPixel.h"
//#include "SPI.h"
#include <sstream>

#include "secrets.h" // Alec Vercruysse (6/30/2020): seperate untracked header file containing network SSID and PASSWORD defines
// ----------------------------------------------------------------------------------------------------------------
//                          Global Defines
#define MAX_CMD 3
#define MAX_INST 10
#define NCOMMANDS 15
#define MAX_MSG_LEN 40
//#define LED_BUILTIN 26          // this isn't the case on the Node32s, is it?
#define LEDARR_PIN 26 //22

// ----------------------------------------------------------------------------------------------------------------
//                          Parameters
// saved in strings, so that later (if implemented) e.g. easily changeable via Bluetooth -> to avoid connection errors
std::string SETUP = "FPMSCOPE";     // setup "number" of the esp32.
std::string COMPONENT = "LEDMATRIX";
std::string DEVICE = "ESP32";
std::string DEVICENAME;
std::string CLIENTNAME;
std::string SETUP_INFO;

// ~~~~  Wifi  ~~~~
const char *ssid = SSID;
const char *password = PASSWORD;
WiFiClient espClient;
PubSubClient client(espClient);
// ~~~~  MQTT  ~~~~
const char *MQTT_SERVER = "192.168.1.148";
const char *MQTT_CLIENTID;
const char *MQTT_USER;
const char *MQTT_PASS = "23SPE";
const int MQTT_SUBS_QOS = 0;
//const int MAX_CONN = 10; // maximum tries to connect
const unsigned long period = 80000; // 80s
unsigned long time_now = 0;
// topics to listen to

std::string stopicREC = "/" + SETUP + "/" + COMPONENT + "/RECM";
std::string stopicSTATUS = "/" + SETUP + "/" + COMPONENT + "/STAT";
std::string stopicANNOUNCE = "/" + SETUP + "/" + COMPONENT + "/ANNO";

// Deliminators for CMDs (published via payload-string)
const char *delim_inst = "+";
const int delim_len = 1;
// ~~~~ LED ~~~~
#define matrix_width 8
#define matrix_height 8 
CRGB leds[matrix_width * matrix_height];
FastLED_NeoMatrix *matrix = new FastLED_NeoMatrix(leds, matrix_width, matrix_height,
                                               NEO_MATRIX_TOP + NEO_MATRIX_LEFT + NEO_MATRIX_ROWS +
                                               NEO_MATRIX_PROGRESSIVE);

const int nrows = 8;
const int ncols = 8;
const int npixels = ncols * nrows;
int ledNA = 4;
struct RGB
{
  byte r;
  byte g;
  byte b;
};
struct RGB rgb;
const int nPattern = 3;
int activePattern = 0;
bool light_pattern_bool[ncols][nrows][nPattern];
unsigned char light_pattern_color[ncols][nrows][nPattern][3];

// ~~~~ Commands ~~~~
const char *CMD;     //Commands like: PXL -> limited to size of 3?
int *INST[MAX_INST]; //Maximum number of possible instructions =
std::vector<int> INSTS;
std::string CMDS;

const char *COMMANDSET[NCOMMANDS] = {"NA", "PXL", "HLINE", "VLINE", "RECT", "CIRC", "LEFT", "RIGHT", "TOP", "BOTTOM", "CLEAR", "PRESET", "SETPRE", "FLYBY", "ALIVE"};
const char *INSTRUCTS[NCOMMANDS] = {"1", "4", "4", "4", "8", "6", "3", "3", "3", "3", "0", "1", "1", "1", "1"};

// ----------------------------------------------------------------------------------------------------------------
//                          Additional Functions
void uc2wait(int period)
{
  unsigned long time_now = millis();
  while (millis() < time_now + period)
    {
      //wait approx. [period] ms
    };
}
/**
void matrix_show()
{
  //portDISABLE_INTERRUPTS(); // transmission to array should no be interrupted
  //matrix.show();
  //matrix.show();           // to remove glitchy green corner
  //portENABLE_INTERRUPTS(); // restore back interrupts
}
**/
void setup_device_properties()
{
  //std::time_t result = std::time(nullptr);
  //srand(result); // init randomizer with pseudo-random seed on boot
  //int randnum = rand() % 10000;
  int rand_number = random(1, 100000);
  std::stringstream srn;
  srn << rand_number;
  DEVICENAME = DEVICE + "_" + srn.str(); // random number generated up to macro MAX_RAND
  CLIENTNAME = SETUP + "_" + COMPONENT + "_" + DEVICENAME;
  SETUP_INFO = "This is:" + DEVICENAME + " on /" + SETUP + "/" + COMPONENT + ".";
  MQTT_CLIENTID = DEVICENAME.c_str(); //"S1_MOT2_ESP32"
  //////Serial.print("MQTT_CLIENTID=");Serial.println(MQTT_CLIENTID);
  MQTT_USER = DEVICE.c_str();
  //Serial.println(SETUP_INFO.c_str());
}
void setup_wifi()
{
  uc2wait(10);
  // We start by connecting to a WiFi network
  Serial.print("Device-MAC: ");
  Serial.println(WiFi.macAddress());
  Serial.print("Connecting to ");
  Serial.print(ssid);
  uc2wait(500);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED)
    {
      uc2wait(500);
      Serial.println(".");
    }
  Serial.print("WiFi connected with IP:");
  Serial.println(WiFi.localIP());
}

int separateMessage(byte *message, unsigned int length)
{

  //Serial.println("Seperating Message.");
  //Serial.print("Message=");
  char messageSep[length];
  for (int myc = 0; myc < length; myc++)
    {
      messageSep[myc] = (char)message[myc];
      //    Serial.print(messageSep[myc]);
    }
  messageSep[length] = NULL;
  ////Serial.println("");
  //Serial.print("Mess=");
  std::string mess(messageSep);
  //Serial.println(mess.c_str());
  size_t pos = 0;
  int i = 0;
  bool found_cmd = false;
  while ((pos = mess.find(delim_inst)) != std::string::npos)
    {
      if (!found_cmd)
        {
          //        Serial.print("CMD-del@");
          //        Serial.println(pos);
          CMDS = mess.substr(0, pos);
          //        Serial.print("CMDS=");
          CMD = CMDS.c_str();
          //        Serial.println(CMD);
          found_cmd = true;
          //        Serial.print("found_cmd set to true, exiting while loop");
        }
      else
        {
          INSTS.push_back(atoi(mess.substr(0, pos).c_str()));
          //        Serial.print("INST[");
          //        Serial.print(i);
          //        Serial.print("]=");
          //        Serial.println(INSTS[i]);
          i++;
        }
      mess.erase(0, pos + delim_len);
    }
  //Serial.print("while loop exited.");
  if (!found_cmd)
    {
      //    Serial.print("CMD-del@");
      //    Serial.println(pos);
      CMDS = mess.substr(0, pos);
      //    Serial.print("CMDS=");
      CMD = CMDS.c_str();
      //    Serial.println(CMD);
      found_cmd = true;
    }
  else if (mess.length() > 0)
    {
      INSTS.push_back(atoi(mess.substr(0, pos).c_str()));
      //    Serial.print("INST[");
      //    Serial.print(i);
      //    Serial.print("]=");
      //    Serial.println(INSTS[i]);
      i++;
    }
  else
    {
      //    Serial.println("Nothing found...");
    }
  return i;
  mess.clear();
}

bool isActivePixel()
{
  return ((rgb.r + rgb.g + rgb.b) != 0);
}

void switchCurrentPreset(int num)
{
  activePattern = num >= nPattern ? (nPattern - 1) : num;
  if (activePattern < 0)
    activePattern = 0;
}

void clearPattern()
{
  //int xpos = 0;
  //int ypos = 0;
  Serial.println("ClearPAT.");
  matrix->clear();
  matrix->show();

  //if (!doNotDisturb)
  //{
  for (int xpos = 0; xpos < ncols; xpos++)
    {
      for (int ypos = 0; ypos < nrows; ypos++)
        {
          light_pattern_color[xpos][ypos][activePattern][0] = 0;
          light_pattern_color[xpos][ypos][activePattern][1] = 0;
          light_pattern_color[xpos][ypos][activePattern][2] = 0;
        }
    }
  //Serial.println("ClearPAT done.");
  //}
}

void reloadPresetPattern()
{
  //int xpos = 0;
  //int ypos = 0;

  matrix->fillScreen(0);
  matrix->show();

  for (int xpos = 0; xpos < ncols; xpos++)
    {
      for (int ypos = 0; ypos < nrows; ypos++)
        {
          if (light_pattern_bool[xpos][ypos][activePattern])
            {
              rgb.r = (uint8_t)light_pattern_color[xpos][ypos][activePattern][0];
              rgb.g = (uint8_t)light_pattern_color[xpos][ypos][activePattern][1];
              rgb.b = (uint8_t)light_pattern_color[xpos][ypos][activePattern][2];
              matrix->drawPixel(xpos, ypos, matrix->Color(rgb.r, rgb.g, rgb.b));
            }
          else
            {
              //if (!doNotDisturb)
              //{
              light_pattern_color[xpos][ypos][activePattern][0] = 0;
              light_pattern_color[xpos][ypos][activePattern][1] = 0;
              light_pattern_color[xpos][ypos][activePattern][2] = 0;
              //}
            }
        }
    }
  matrix->show();
}

void drawRect(int x, int y, int w, int h, bool fill)
{
  int offset_x = (ncols - ledNA * 2) * 0.5;
  int offset_y = (nrows - ledNA * 2) * 0.5;
  if (x < offset_x)
    x = offset_x;
  if (y < offset_y)
    y = offset_y;
  if (x > ncols - offset_x)
    x = ncols - offset_x;
  if (y > nrows - offset_y)
    y = nrows - offset_y;
  if ((x + w) > (ncols - offset_y))
    w = ncols - offset_y - x;
  if ((y + h) > (nrows - offset_x))
    h = nrows - offset_x - y;

  //Serial.print("Corrected val for Rect = ");
  //Serial.print(x);
  //Serial.print(",");
  //Serial.print(y);
  //Serial.print(",");
  //Serial.print(w);
  //Serial.print(",");
  //Serial.print(h);
  //Serial.print(",");
  //Serial.print(rgb.r);
  //Serial.print(",");
  //Serial.print(rgb.g);
  //Serial.print(",");
  //Serial.print(rgb.b);
  //Serial.println(".");
  if (fill)
    matrix->fillRect(x, y, w, h, matrix->Color(rgb.r, rgb.g, rgb.b));
  else
    matrix->drawRect(x, y, w, h, matrix->Color(rgb.r, rgb.g, rgb.b));
  matrix->show();
}

void setRGB(int r, int g, int b)
{
  rgb.r = r;
  rgb.g = g;
  rgb.b = b;
}

void setNA(int select)
{
  //if (select<5 & select> 0)      //// MOD
  if (select < 5 && select > 0)
    {
      ledNA = select;
      Serial.print("NA set to: ");
      Serial.print(ledNA);
      Serial.println(".");
      setRGB(255, 255, 255);
      //   Serial.println("Call drawRect with: [0,0,8,8,255,255,255]. ");
      drawRect(0, 0, 8, 8, true);
      matrix->show();
    }
  else
    {
      Serial.print("NA not btwn 1-4, set to 0.");
      select = 0;
      ledNA = select;
      matrix->clear();
      matrix->show();
    }
}

void updateColor(uint8_t r, uint8_t g, uint8_t b)
{
  rgb.r = r;
  rgb.g = g;
  rgb.b = b;
}

void callback(char *topic, byte* message, unsigned int length)
{
  //Serial.println("Callback-func called.");
  // test topics
  if (std::string(topic) == stopicREC)
    {
      //    //Serial.println(stopicREC.c_str());
      int nINST = separateMessage(message, length);
      if (strcmp(CMD, COMMANDSET[0]) == 0) // NA
        {
          setNA(INSTS[0]);
        }
      else if (strcmp(CMD, COMMANDSET[1]) == 0) // PXL
        {
          //        Serial.print("PXL working. :) -> nINST=");
          //        Serial.println(nINST);
          int xpos = INSTS[0] % ncols;
          int ypos = INSTS[0] / ncols;
          updateColor(INSTS[nINST - 3], INSTS[nINST - 2], INSTS[nINST - 1]);
          matrix->drawPixel(xpos, ypos, matrix->Color(rgb.r, rgb.g, rgb.b));
          matrix->show();

          //if (!doNotDisturb)
          //{
          light_pattern_bool[xpos][ypos][activePattern] = true;
          light_pattern_color[xpos][ypos][activePattern][0] = INSTS[nINST - 3];
          light_pattern_color[xpos][ypos][activePattern][1] = INSTS[nINST - 2];
          light_pattern_color[xpos][ypos][activePattern][2] = INSTS[nINST - 1];
          //}
          client.publish(stopicSTATUS.c_str(), "PXL DONE");
        }
      else if (strcmp(CMD, COMMANDSET[4]) == 0)
        {
          //updateColor(INSTS[nINST - 4], INSTS[nINST - 3], INSTS[nINST - 2]);
          updateColor(INSTS[nINST - 3], INSTS[nINST - 2], INSTS[nINST - 1]);
          bool fill = !(INSTS[nINST - 1] == 1);
          drawRect(INSTS[0], INSTS[1], INSTS[2], INSTS[3], fill);
        }
      else if (strcmp(CMD, COMMANDSET[5]) == 0)
        {
          updateColor(INSTS[nINST - 3], INSTS[nINST - 2], INSTS[nINST - 1]);
          drawRect(INSTS[0], INSTS[1], INSTS[2], INSTS[3], true);
        }
      else if (strcmp(CMD, COMMANDSET[6]) == 0)
        {
          updateColor(INSTS[nINST - 3], INSTS[nINST - 2], INSTS[nINST - 1]);
          drawRect(0, 0, 4, 8, true);
        }
      else if (strcmp(CMD, COMMANDSET[7]) == 0)
        {
          updateColor(INSTS[nINST - 3], INSTS[nINST - 2], INSTS[nINST - 1]);
          drawRect(4, 0, 4, 8, true);
        }
      else if (strcmp(CMD, COMMANDSET[8]) == 0)
        {
          updateColor(INSTS[nINST - 3], INSTS[nINST - 2], INSTS[nINST - 1]);
          drawRect(0, 0, 8, 4, true);
        }
      else if (strcmp(CMD, COMMANDSET[9]) == 0)
        {
          updateColor(INSTS[nINST - 3], INSTS[nINST - 2], INSTS[nINST - 1]);
          drawRect(0, 4, 8, 4, true);
        }
      else if (strcmp(CMD, COMMANDSET[10]) == 0) // CLEAR
        {
          clearPattern();
        }
      else if (strcmp(CMD, COMMANDSET[11]) == 0)
        {
          switchCurrentPreset(INSTS[0]);
          reloadPresetPattern();
          client.publish(stopicSTATUS.c_str(), "CLEAR DONE");
        }
      else if (strcmp(CMD, COMMANDSET[12]) == 0)
        {
          switchCurrentPreset(INSTS[0]);
        }
      else if (strcmp(CMD, COMMANDSET[13]) == 0)
        {
          //doNotDisturb = (INSTS[0] == 1);
          Serial.println("-DoNotDisturb- invoked. Not implemented.");
        }
      else if (strcmp(CMD, COMMANDSET[14]) == 0)
        {
          Serial.print("alive!");
        }
      else
        {
          Serial.print("CMD not found.");
        }
    }
  else if (std::string(topic) == stopicSTATUS)
    {
      Serial.println(stopicSTATUS.c_str());
    }
  else if (std::string(topic) == stopicANNOUNCE)
    {
      Serial.println(stopicANNOUNCE.c_str());
    }
  else
    {
      Serial.print("Assortion Error: Nothing found for topic=");
      Serial.println(topic);
    }
  INSTS.clear();
}

void reconnect()
{
  //Serial.print("reconnect called!!!!");
  // Loop until we're reconnected
  while (!client.connected())
    {
      //    Serial.print("MQTT_CLIENTID=");
      //    Serial.println(MQTT_CLIENTID);
      //    Serial.print("topicSTATUS=");
      //    Serial.println(stopicSTATUS.c_str());
      //    Serial.print("Attempting MQTT connection...");
      // Attempt to connect

      if (client.connect(MQTT_CLIENTID, stopicSTATUS.c_str(), 2, 1, "0"))
        {
          // client.connect(MQTT_CLIENTID,MQTT_USER,MQTT_PASS,"esp32/on",2,1,"off")
          //        Serial.println("connected");
          // Subscribe
          client.subscribe(stopicREC.c_str());
          client.publish(stopicSTATUS.c_str(), "1");
          client.publish(stopicANNOUNCE.c_str(), SETUP_INFO.c_str());
        }
      else
        {
          //        Serial.print("failed, rc=");
          //        Serial.print(client.state());
          //        Serial.println(" try again in 5 seconds");
          // Wait 5 seconds before retrying
          uc2wait(5000);
        }
    }
}

// ----------------------------------------------------------------------------------------------------------------
//                          SETUP
void setup()
{
  Serial.begin(115200);
  // check for connected motors
  //status = bme.begin();
  setup_device_properties();
  //Serial.print("VOID SETUP -> topicSTATUS=");
  //Serial.println(stopicSTATUS.c_str());
  setup_wifi();
  //Serial.println("setup_wifi done, setting server:");
  client.setServer(MQTT_SERVER, 1883);
  client.setCallback(callback);
  //Serial.println("done");
  //pinMode(LED_BUILTIN, OUTPUT);
  time_now = millis();
  //testCPP();
  uc2wait(100);
  FastLED.addLeds<NEOPIXEL,LEDARR_PIN>(leds, matrix_width*matrix_height);
  
  matrix->begin();
  matrix->setBrightness(255);
  matrix->setTextWrap(false);
  Serial.println("If the code crashes here, decrease the brightness or turn off the all white display below");
  for(int i = 0; i < matrix_height*matrix_width; i++){
    matrix->drawPixel(i%matrix_width, i/matrix_width, matrix->Color(255,0,0));
    matrix->show();
    delay(10);
  }
    delay(1000);
  
  matrix->clear();
  matrix->show();
  
  // matrix.fillScreen(0);
  // //matrix.setCursor(x, 0);
  // matrix.setTextColor(matrix.Color(40, 127, 200));
  // matrix.print(F("UC2"));
  // matrix_show();
  // uc2wait(1000);
  // matrix.fillScreen(0);
  // matrix_show();
  // uc2wait(100);
  //Serial.print("setup done. entering main loop");
}
// ----------------------------------------------------------------------------------------------------------------
//                          LOOP
void loop()
{
  uc2wait(1000);
  if (!client.connected())
    {
      reconnect();
    }
  client.loop();
  if (time_now + period < millis())
    {
      client.publish(stopicSTATUS.c_str(), "1");
      time_now = millis();
    }
}
// ----------------------------------------------------------------------------------------------------------------
