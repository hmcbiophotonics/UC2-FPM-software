import paho.mqtt.client as mqtt
import time

client = mqtt.Client("pi") #create new instance
client.connect("localhost") #connect to broker
client.publish("/FPMSCOPE/LEDMATRIX/RECM","CLEAR")

for i in range(64):
    client.publish("/FPMSCOPE/LEDMATRIX/RECM", "PXL+{}+255+0+0".format(i))
    time.sleep(0.1)
