#!/bin/bash

if [ $# -eq 0 ]
  then
    echo "Usage: $0 imageName"
    exit 1
fi

IMAGE=$1

docker image rm $IMAGE
time docker pull $IMAGE
echo
docker image inspect $IMAGE | grep -v VirtualSize | grep "Size"
