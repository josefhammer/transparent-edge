#!/bin/bash

if [ "$#" -ne 1 ]
then
    echo "Usage: $0 <switch>"
    exit 1
fi
switch=$1


# cookie value/mask
#
# https://stackoverflow.com/questions/1494178/how-to-define-hash-tables-in-bash
#
declare -A COOKIES=( ["edgeDetect"]="19/19" ["defaultDetect"]="35/35" ["edgeRedir"]="76/76" ["defaultRedir"]="140/140" )


echo "["
while true
do
    seconds=`date +%s`
    stats=""
    for COOKIE in "${!COOKIES[@]}"; do
        stats=$stats`sudo ovs-ofctl dump-aggregate $switch cookie="${COOKIES[$COOKIE]}" | cut -d : -f 2 | sed -e 's/\s/,"/g' | sed -e 's/=/":/g' | sed -e "s/_count/_count_$COOKIE/g"`
    done
    echo "{\"ts_sec\":$seconds$stats},"
    sleep 1
done
