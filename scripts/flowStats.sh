#!/bin/bash

# cookie value/mask
DETECT_EDGE="19/19"
DETECT_DEFAULT="35/35"
REDIR_EDGE="76/76"
REDIR_DEFAULT="140/140"

FLOWS="$DETECT_EDGE $DETECT_DEFAULT $REDIR_EDGE $REDIR_DEFAULT"
#for COOKIE in $FLOWS


echo "["
while true
do
    seconds=`date +%s`
    stats=`sudo ovs-ofctl dump-aggregate o-bs1 cookie=$DETECT_DEFAULT | cut -d : -f 2 | sed -e 's/\s/,"/g' | sed -e 's/=/":/g'`
    echo "{\"timestamp\":$seconds$stats},"
    sleep 1
done
