#!/bin/bash

if [ $# -eq 0 ]
then
    echo "Usage: $0 imageName"
    exit 1
fi

echo ""
echo "Make sure first that no layers are in use by other images/containers!"
echo ""

TIMESTAMP=$(date +"%Y%m%d-%H%M%S")

NAME=$1
IMAGE=$1
if [ $# -gt 1 ]
then
    shift  # first param is the name
    IMAGE=$@
fi
NAME="${NAME//\//__}"  # replace / with __

BASE_FOLDER="/home/edge/perf-measure-data/pull-times/"
JSON="$BASE_FOLDER/$NAME/$NAME.json"  
LOG="$BASE_FOLDER/$NAME/$NAME.log"  
INSPECT="$BASE_FOLDER/$NAME/$NAME.inspect.json"


mkdir -p "$BASE_FOLDER/$NAME"

echo "{\"image\":\"$IMAGE\",\"timestamp\":\"$TIMESTAMP\",\"real\":[" > "$JSON"
echo "$TIMESTAMP" > "$LOG"


for i in {1..20}
do
    docker image rm $IMAGE >> "$LOG" 2>&1 
    sleep 1
    echo "Pull #$i"
    /usr/bin/time -f "%e," -a -o "$JSON" bash -c "echo $IMAGE | xargs -P4 -n1 docker pull" >> "$LOG" 2>&1 
    # time docker pull $IMAGE
    sleep 5
done

# REVIEW Not working yet with multiple images
SIZE=$(docker image inspect $IMAGE | grep -v VirtualSize | grep "Size")

echo "],${SIZE//,/\}}" >> "$JSON"

sed -i -zr 's/,\n\]/\]/' "$JSON"  # remove last comma in array

docker image inspect $IMAGE > "$INSPECT"

less "$LOG"
