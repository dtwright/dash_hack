# The following script is an adjusted version of Aaron Bell's script
# http://www.aaronbell.com/how-to-hack-amazons-wifi-button/

# improvement from original script:
# - New dash buttons can be added by just adding a new nickname to the macs dictionary
# - Will not trigger multiple events for one press (see trigger_timeout below)

# if you want to run this script as an ubuntu service, check out
# http://askubuntu.com/questions/175751/how-do-i-run-a-python-script-in-the-background-and-restart-it-after-a-crash

import socket
import struct
import binascii
import time
import json
import urllib2
import datetime
import os
import pychromecast

# Use your own IFTTT key, not this fake one
ifttt_key = 'cwFZ6OfWoaUYQWiP7zilna'
# the number of seconds after a dash button is pressed that it will not trigger another event
# the reason is that dash buttons may try to send ARP onto the network during several seconds
# before giving up
# this is long b/c I'm using one as a doorbell...
trigger_timeout = 10

# base directory where this script (and the radio script) lives
base_dir = '/home/dtwright/dash_hack'

# Replace these fake MAC addresses and events
# the event will be parsed to decide what to do. currently there are two things: trigger
# ifttt maker channel event, or start a Chromecast radio station
# note: media events shouldn't have spaces in their path; this should get fixed sometime
macs = {
    # '44650de9a1a8' : 'ifttt:dash_doorbell',
    # '0c47c96c1d01' : 'radio:http://media.wmra.org:8000/wmra',
    # ^^^this button seems to be broken...
    '44650d6a9a56' : 'radio:http://pubint.ic.llnwd.net/stream/pubint_wvtf128',
    '44650de9a1a8' : 'radio:http://media.wmra.org:8000/wmra',
    '50f5da150bd7' : 'media:/data/audio/Kenny_Rogers/03-Just_Dropped_in.mp3'
}

# for recording the last time the event was triggered to avoid multiple events fired
# for one press on the dash button
trigger_time = {}

# hack to make sure chromecast has an appid - needs real fixing
def force_cc_appid():
    cast = pychromecast.get_chromecast()
    cast.media_controller.play_media('','')

# Trigger a IFTTT URL where the event is the same as the strings in macs (e.g. dash_gerber)
# Body includes JSON with timestamp values.
def trigger_url_generic(trigger):
    # parse the trigger 
    if trigger[0:5] == 'ifttt':
        # ifttt maker event
        event = trigger[6:]
        data = '{ "value1" : "' + time.strftime("%Y-%m-%d") + '", "value2" : "' + time.strftime("%H:%M") + '" }'
        req = urllib2.Request( 'https://maker.ifttt.com/trigger/'+event+'/with/key/'+ifttt_key , data, {'Content-Type': 'application/json'})
        f = urllib2.urlopen(req)
        response = f.read()
        f.close()
        return response
    elif trigger[0:5] == 'radio':
        # radio station
        url = trigger[6:]
        force_cc_appid()
        out = os.system(base_dir + '/toggle-radio.sh ' + url)
        if out == 0: 
            return "success"
        else:
            return "radio script fail"
    elif trigger[0:5] == 'media':
        path = trigger[6:]
        force_cc_appid()
        out = os.system(base_dir + '/play-media.sh "' + path + '"')
        if out == 0: 
            return "success"
        else:
            return "castnow failure"
    else:
        return "unknown trigger type: "+trigger

def record_trigger(trigger):
    print 'triggering '+ trigger +' event, response: ' + trigger_url_generic(trigger)

def is_within_secs(last_time, diff):
    return (datetime.datetime.now() - last_time).total_seconds() < (diff +1)

# check if event has triggered within the timeout already
def has_already_triggered(trigger):
    global trigger_time
    
    if trigger in trigger_time:
        if (is_within_secs(trigger_time[trigger], trigger_timeout)):
            return True

    trigger_time[trigger] = datetime.datetime.now()
    return False

rawSocket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))

while True:
    packet = rawSocket.recvfrom(2048)
    ethernet_header = packet[0][0:14]
    ethernet_detailed = struct.unpack("!6s6s2s", ethernet_header)
    # skip non-ARP packets
    ethertype = ethernet_detailed[2]
    if ethertype != '\x08\x06':
        continue
    arp_header = packet[0][14:42]
    arp_detailed = struct.unpack("2s2s1s1s2s6s4s6s4s", arp_header)
    source_mac = binascii.hexlify(arp_detailed[5])
    source_ip = socket.inet_ntoa(arp_detailed[6])
    dest_ip = socket.inet_ntoa(arp_detailed[8])
    if source_mac in macs:
        
        if has_already_triggered(macs[source_mac]):
            print "Culled duplicate trigger " + macs[source_mac]
        else:
            record_trigger(macs[source_mac])

    elif source_ip == '0.0.0.0':
        print "Unknown dash button detected with MAC " + source_mac
