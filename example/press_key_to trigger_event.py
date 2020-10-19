import msvcrt # NOTE: this module is windows only! Required to detect keypress.
import time
import sys
import argparse

from pythonosc import osc_message_builder
from pythonosc import udp_client

# Define default and static values
osc_identifier1 = '/pyBinSimSoundevent'
ip = '127.0.0.1'
port = 10000

# Handle input variables
parser = argparse.ArgumentParser()
parser.add_argument("--ip", default=ip, help="The ip of the OSC server")
parser.add_argument("--port", type=int, default=port, help="The port the OSC server is listening on")
args = parser.parse_args()

# Create OSC client
client = udp_client.SimpleUDPClient(args.ip, args.port)
print("OSC client is running.")
print("Waiting for button press...\n\tq - start event 004 on channel 0\n\tq - start event 002 on channel 1")
try:
    while 1:

        if msvcrt.kbhit():
            char = msvcrt.getch()
            #print("Pressed Button:{} ({})".format(char, ord(char)))
	
            if ord(char) == 113: #q
                print('char ',char)
                message = ['004', 'start', 0]
                client.send_message(osc_identifier1, message) 
            
            if ord(char) == 119: #w
                message = ['002', 'start', 1]
                client.send_message(osc_identifier1, message) 

            if ord(char) == 101: #e
                message = ['002', 'pause']
                client.send_message(osc_identifier1, message) 
        
        sys.stdout.flush()
        time.sleep(0.1)        

except KeyboardInterrupt:	
    """Break if ctrl+c is pressed"""
    print("Exit by Keyboard interrupt.")
