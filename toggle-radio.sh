#!/bin/sh

PID_FILE=/tmp/running-radio.pid

# if the radio is already on, kill the running station and exit
if [ -f $PID_FILE ]; then
    kill `cat $PID_FILE`
    rm $PID_FILE
    exit
fi

# clean up any stray junk that might interfere
pids=`ps ax | grep castnow | grep -v grep | awk '{print $1}'`
kill $pids
sleep 1

# start with given URL
url=$1
if [ ""$url = "" ]; then
    echo "ERROR: URL must be provided!"
    exit
fi

# start in bg...
curl -s $url | castnow --quiet - &
# ...and save the pid.
echo $! > $PID_FILE
