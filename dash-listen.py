# The following script is an adjusted version of Aaron Bell's script
# http://www.aaronbell.com/how-to-hack-amazons-wifi-button/

# improvement from original script:
# - New dash buttons can be added by just adding a new nickname to the macs dictionary
# - Will not trigger multiple events for one press (see trigger_timeout below)
# - Does lots of Chromecast media stuff in-line 

import socket
import struct
import binascii
import time
import json
import urllib2
import datetime
import os
import pychromecast
import string
import BaseHTTPServer
import os
import random
import sys
from threading import Thread

# global to control whether polling should be running
DO_ARP_POLLING = True

# Use your own IFTTT key, not this fake one
ifttt_key = 'xxxxxx'
# the number of seconds after a dash button is pressed that it will not trigger another event
# the reason is that dash buttons may try to send ARP onto the network during several seconds
# before giving up
# this is long b/c I'm using one as a doorbell...
trigger_timeout = 10

# radio toggle tracking - hack because chromecast status retrival isn't working
# (maybe because this process has the interface in promisc mode??)
radio_is_playing = False

# hang on to the chromecasts 
all_casts = [];

# ip/hostname and port to serve local media from
MEDIA_HTTP_HOST = "192.168.1.102"
MEDIA_HTTP_PORT = 4101

# Replace these fake MAC addresses and events
# the event will be parsed to decide what to do. currently there are two things: trigger
# ifttt maker channel event, or start a Chromecast radio station
# note: media events shouldn't have spaces in their path; this should get fixed sometime
#
# format is event_type:event_details
#
# for Chromecast events (media or radio), details are <device_name>,<media_path_or_url>,<mime_type>
# note: if mime_type is omitted, 'audio/mpeg' will be assumed
macs = {
    # '44650de9a1a8' : 'ifttt:dash_doorbell',
    '44650d6a9a56' : 'radio:kitchen,http://18153.live.streamtheworld.com/WVTFHD2_128.mp3,audio/mpeg',
    '44650de9a1a8' : 'radio:kitchen,http://media.wmra.org:8000/wmra,audio/mpeg',
    '50f5da150bd7' : 'media:kitchen,/data/audio/Kenny_Rogers/03-Just_Dropped_in.mp3,audio/mpeg'
    #'50f5da150bd7' : 'radio:kitchen,http://18153.live.streamtheworld.com/WVTFHD2_128.mp3,audio/mpeg',
    #'50f5da150bd7' : 'radio:kitchen,http://media.wmra.org:8000/wmra,audio/mpeg',
}

# for recording the last time the event was triggered to avoid multiple events fired
# for one press on the dash button
trigger_time = {}

def lcitem(i):
    return i.lower()

def play_error(mc):
    print "error..."

# creates an http server that will present the data for the 
# passed-in file
#
# resulting URL will always be http://MEDIA_HTTP_HOST:MEDIA_HTTP_PORT/
#
# note: should be launched in a thread!
def file_streamserve(path,size,mime,host,port):
    # local media streamer class definition
    class LocalHTTPMediaStreamer(BaseHTTPServer.BaseHTTPRequestHandler):
        global has_processed_req
        def do_HEAD(s):
            s.send_response(200)
            s.send_header("Content-Type", mime)
            s.end_headers()
        def do_GET(s):
            # get the file info and data
            fh = open(path,'r')

            s.send_response(200)
            s.send_header("Content-Type", mime)
            s.send_header("Content-Length", size)
            s.end_headers()
            s.wfile.write(fh.read())
            fh.close()
            s.server.shutdown()
    # end class def

    httpd = BaseHTTPServer.HTTPServer((host, port), LocalHTTPMediaStreamer)
    try:
        httpd.serve_forever()
    except:
        print "httpd server failure!"

    # quit the thread
    sys.exit()

def get_all_casts():
    global all_casts
    if len(all_casts) == 0:
        all_casts = pychromecast.get_chromecasts()

    return all_casts

def get_cc_by_name(name):
    ac = get_all_casts()
    return next(cc for cc in ac if cc.device.friendly_name.lower() == name)

def get_chromecast_names():
    ccs = get_all_casts()
    return [cc.device.friendly_name for cc in ccs]

def force_stop_cc(cc_name):
    # hack to stop media playing when MediaStatus/MediaController stuff isn't working right
    cast = get_cc_by_name(cc_name)
    cast.media_controller.play_media('http://bad_url/','application/bad-mime')

def play_on_chromecast(ev_type,ev_detail):
    global radio_is_playing

    # short delay to make sure raw socket shutdown has finished
    time.sleep(0.3)

    # parse for device name
    parts = ev_detail.split(',')
    dev_name = parts[0].lower()
    media_path = parts[1]
    if len(parts) < 3:
        print "MIME not specified; assuming audio/mpeg"
        mime = 'audio/mpeg'
    else: 
        mime = parts[2]

    # make sure this is a valid device
    devs = map(lcitem, get_chromecast_names())
    try:
        i = devs.index(dev_name)
    except ValueError:
        # we're done; specificied chromecast don't exist...
        return "no such chromecast found: "+dev_name

    # send the requested media to the device
    cast = get_cc_by_name(dev_name)

    # get media controller
    mc = cast.media_controller
    try:
        mc.update_status()
    except:
        pass

    # depending on whether we're radio or media, we need to treat things somewhat
    # differently... 

    if ev_type == 'radio':
        # radio acts as a toggle: stop playing if something is currently playing, 
        # else play the requested thing
        if mc.is_playing:
            mc.stop()
            radio_is_playing = False
            return "stopped"
        else:
            mc.play_media(media_path,mime)
            radio_is_playing = True
            # check status after a brief delay
            # NOTE: isn't working due to status issues...
            time.sleep(2)
            if mc.is_idle and mc.status.idle_reason == 'ERROR':
                # play the error tone using this media controller
                play_error(mc)
                radio_is_playing = False
                return "error playing!"
            else:
                return "playing radio"

    elif ev_type == 'media':
        mc.stop()
        # get the file length -- check to be sure it exists at the same time
        try:
            media_size = os.path.getsize(media_path)
        except:
            play_error(mc)
            return "media file "+media_path+" does not exist"

        # launch http streamer in a thread
        strm_port = MEDIA_HTTP_PORT + random.randint(0,1024)
        try:
            t = Thread(target=file_streamserve, args=(media_path,media_size,mime,MEDIA_HTTP_HOST,strm_port,))
            t.daemon = True
            t.start()
        except Exception as e: 
            print "http server launch error: ", e
            return "Error launching streamer thread!"

        url = "http://" + MEDIA_HTTP_HOST + ":" + str(strm_port) + "/"
        print("streaming from: "+url)
        mc.play_media(url,mime)
        # check status after a brief delay
        # NOTE: isn't working due to status issues...
        time.sleep(2)
        if mc.is_idle and mc.status.idle_reason == 'ERROR':
            # play the error tone using this media controller
            play_error(mc)
            return "error playing!"
        else:
            return "playing media file"


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
        DO_ARP_POLLING = False
        result = play_on_chromecast('radio',trigger[6:])
        DO_ARP_POLLING = True
        return result
    elif trigger[0:5] == 'media':
        DO_ARP_POLLING = False
        result = play_on_chromecast('media',trigger[6:])
        DO_ARP_POLLING = True
        return result
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

# the following setup polls a raw socket for ARP packets, EXCEPT when interrupted by control 
# variable DO_ARP_POLLING. this is needed because having the raw socket open interferes with
# controlling the chromecast and getting status.
socket_alloc = False
while True:
    while DO_ARP_POLLING:
        if not socket_alloc:
            rawSocket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))

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
    
    # we'll only get here if DO_ARP_POLLING has been set false
    if socket_alloc:
        rawSocket.shutdown()
        rawSocket.close()
        socket_alloc = False

    # only run this outer loop every 1s
    time.sleep(1)


