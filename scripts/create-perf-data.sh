#!/bin/bash

SERVICE=143.205.180.80
DIRECT=10.0.2.100:31602

# print output to check systems are working correctly
#
wget -O - $SERVICE
wget -O - $DIRECT

# avoid cold start
#
timecurl.sh loop 10 sleep 1 $SERVICE
timecurl.sh loop 10 sleep 1 $DIRECT

# measure redirection
#
echo "Measure redirection"
timecurl.sh loop 2 sleep 2 $SERVICE > /dev/null  # set up flow
timecurl.sh loop 1000 sleep 0 $SERVICE > perf-data-redir-sl0.json

echo "Measure direct access"
timecurl.sh loop 2 sleep 2 $DIRECT > /dev/null  # set up flow
timecurl.sh loop 1000 sleep 0 $DIRECT > perf-data-direct-sl0.json

# measure flow setup time
#
echo "Measure flow setup time"
sleep 4  # get rid of existing flow
timecurl.sh loop 1000 sleep 4 $SERVICE > perf-data-redir-1st.json
