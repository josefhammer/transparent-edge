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
IMAGE=$1
BASE_FOLDER="/home/edge/perf-measure-data/pull-times/"
BASE_NAME="${IMAGE//\//__}"  # replace / with __
JSON="$BASE_FOLDER/$BASE_NAME/$BASE_NAME.json"  
LOG="$BASE_FOLDER/$BASE_NAME/$BASE_NAME.log"  
INSPECT="$BASE_FOLDER/$BASE_NAME/$BASE_NAME.inspect.json"


mkdir -p "$BASE_FOLDER/$BASE_NAME"

echo "{\"image\":\"$IMAGE\",\"timestamp\":\"$TIMESTAMP\",\"real\":[" > "$JSON"
echo "$TIMESTAMP" > "$LOG"


for i in {1..20}
do
    docker image rm $IMAGE >> "$LOG" 2>&1 
    sleep 1
    echo "Pull #$i"
    /usr/bin/time -f "%e," -a -o "$JSON" docker pull $IMAGE >> "$LOG" 2>&1 
    # time docker pull $IMAGE
    sleep 5
done

SIZE=$(docker image inspect $IMAGE | grep -v VirtualSize | grep "Size")

echo "],${SIZE//,/\}}" >> "$JSON"

sed -i -zr 's/,\n\]/\]/' "$JSON"  # remove last comma in array

docker image inspect $IMAGE > "$INSPECT"

less "$LOG"
