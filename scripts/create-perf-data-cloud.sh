#!/bin/bash

SERVICE=143.205.180.42

# print output to check systems are working correctly
#
wget -O - $SERVICE

# avoid cold start
#
timecurl.sh loop 10 sleep 1 $SERVICE

# measure redirection
#
echo "Measure access"
timecurl.sh loop 2 sleep 2 $SERVICE > /dev/null  # set up flow
timecurl.sh loop 1000 sleep 0 $SERVICE > perf-data-cloud-sl0.json

# measure flow setup time
#
echo "Measure flow setup time"
sleep 4  # get rid of existing flow
timecurl.sh loop 1000 sleep 4 $SERVICE > perf-data-cloud-first.json
