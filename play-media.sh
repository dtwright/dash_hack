#!/bin/sh

PID_FILE=/tmp/running-radio.pid

# if the radio on, kill the running station
if [ -f $PID_FILE ]; then
    kill `cat $PID_FILE`
    rm $PID_FILE
    sleep 1
fi

# clean up any other stray junk that might interfere
pids=`ps ax | grep castnow | grep -v grep | awk '{print $1}'`
kill $pids
sleep 1

# start with given path
path=$1
if [ ""$path = "" ]; then
    echo "ERROR: path must be provided!"
    exit
fi

# start in bg...
cat "$path" | castnow --quiet - &
