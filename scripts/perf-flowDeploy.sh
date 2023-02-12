#!/bin/bash

# Configuration (default values; can be overwritten in config file)
#
RYU_logLevel='INFO'

CREATE_SCRIPT="createServiceIDsFromIPList.py"
FLOWS_SCRIPT="flowStats.sh"
FILTER_SCRIPT="csvFilter.py"
REPLAY_SCRIPT="replayRequests.py"
SCP_FILES=("flowTools.py")

COLLECT_DIR=~/perf-measure-data/
NODE_DIR="./_jh_test"  # work folder on the nodes
RESULTS_DIR="results"  # subfolder of NODE_DIR
RYU_READY_FILE="/var/emu/ryuReady.txt"


# ***** Off-limits from here on *****


# Additional config vars read from config file
CONFIG_VARS=('TEMPLATE' 'SERVICE_NAME' 'USE_TIMECURL' 'RYU_CONFIG' 'SWITCH' 'DEST_PORTS' 'idleTimeout' 'uniquePrefix' 'uniqueMask')
#
# optional config vars
#
CURL_PARAMS=
CURL_DATA=


checkVar() {  
    # https://stackoverflow.com/questions/1921279/how-to-get-a-variable-value-if-variable-name-is-stored-as-string
    if [ -z "${!1}" ]; then 
        echo "Please define '$1'."
        exit 1
    fi
}

killOldProcesses() {
    checkVar REPLAY_SCRIPT
    checkVar RYU_EDGE  # SSH session gets killed if not defined ;)
    checkVar FLOWS_SCRIPT
    
    # Kill old running processes
    #
    PID_SCRIPTS=$(ps -ef | grep "$REPLAY_SCRIPT" | grep -v grep | tr -s ' ' | cut -d ' ' -f2)

    # Kill old SDN Controller instances (in case they exist)
    #
    PID_RYU=$(ps -ef | grep "$RYU_EDGE" | grep -v grep | tr -s ' ' | cut -d ' ' -f2)

    # Kill old flow count scripts
    #
    PID_FLOWS=$(ps -ef | grep "$FLOWS_SCRIPT" | grep -v grep | tr -s ' ' | cut -d ' ' -f2)

    kill $PID_SCRIPTS $PID_RYU $PID_FLOWS 2>/dev/null
    # suppress bash TERMINATED messages: 
    # https://stackoverflow.com/questions/81520/how-to-suppress-terminated-message-after-killing-in-bash
    wait $PID_SCRIPTS $PID_RYU $PID_FLOWS 2>/dev/null
}


if [ "$#" -lt 4 ]
  then
    echo "Usage: $0 configFile replayFlows.csv nodes.txt minNumRequests [svcFile] ['nowait']"
    # e.g.: ~/data-eval-synced/bigFlows-conv-destPorts/bigFlows-conv-addrs-dstPort-80-minReq20.csv
    exit 1
fi
CONFIG_FILE="$1"
REPLAY_FILE="$2"
NODES_FILE="$3"
MIN_NUM_REQUESTS=$4
SVC_FILE=$5
NO_WAIT=$6

WORKDIR="$(pwd)"
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
source "$DIR/../bash-aliases.sh"  # for RYU_EDGE etc.

CFG_DIR="$( cd "$( dirname "$CONFIG_FILE" )" >/dev/null 2>&1 && pwd )"
source "$CONFIG_FILE" "$CFG_DIR"  # for config vars; pass its folder as first param for convenience


# Check whether configuration vars are defined
for v in ${CONFIG_VARS[@]}; do
    checkVar $v
done


# Kill old processes
killOldProcesses


# INFO
#
echo
echo
echo
echo "***  You might want to stop / remove existing service instances first!  ***" 
echo
echo
echo
if [ "$NO_WAIT" != "nowait" ]; then
    read -p "Press any key to resume ..."
fi


# Get the basename without extension
# https://stackoverflow.com/questions/3362920/get-just-the-filename-from-a-path-in-a-bash-script
#
REPLAY_FILE_BASE=$(basename "$REPLAY_FILE")
EXT=${REPLAY_FILE_BASE##*.}
REPLAY_NAME=${REPLAY_FILE_BASE%.*}
if [ "$EXT" != "csv" ]; then
    echo "Second param needs to be a ReplayFlows file (.csv)."
    exit 1
fi
echo ReplayFlows: $(basename "$REPLAY_FILE")
echo

CONFIG_FILE_BASE=$(basename "$CONFIG_FILE")
CONFIG_NAME=${CONFIG_FILE_BASE%.*}


# Define services names
#
if [ -z "$SVC_FILE" ]; then   # param empty
    SERVICES="services"
else
    SERVICES_FILE_BASE=$(basename "$SVC_FILE")
    SERVICES=${SERVICES_FILE_BASE%.*}
fi


# Create collect folder
#
RUN_NAME="$SERVICES.$CONFIG_NAME.min$MIN_NUM_REQUESTS"
TIMESTAMP=$(date +"%Y%m%d-%H%M%S") 
COLLECT_DIR="$COLLECT_DIR/$REPLAY_NAME/$CONFIG_NAME/$RUN_NAME.$TIMESTAMP/"
mkdir -p "$COLLECT_DIR"
echo 
echo "Collecting data in: $COLLECT_DIR"
LOG="$COLLECT_DIR/log.txt"
echo "$@" > "$LOG"


if [[ ! -z "$SVC_FILE" ]]; then   # param not empty
    # Collect input file
    cp "$SVC_FILE" "$COLLECT_DIR"  
else
    SERVICES="$RUN_NAME"
    SERVICES_FILE_BASE="$SERVICES.csv"
fi
SERVICES_FILE="$COLLECT_DIR/$SERVICES_FILE_BASE"


if [ ! -f "$SERVICES_FILE" ]; then
    #
    # Generate service addresses
    #
    $DIR/$FILTER_SCRIPT "$REPLAY_FILE" $DEST_PORTS --minNumRequests $MIN_NUM_REQUESTS --printAddrs > "$SERVICES_FILE"
fi

# Generate jobs
#
$DIR/$FILTER_SCRIPT "$REPLAY_FILE" $DEST_PORTS --minNumRequests $MIN_NUM_REQUESTS --printSrcIPs --plain > "$COLLECT_DIR/jobs.txt"

# Create services
#
$DIR/$CREATE_SCRIPT --template "$TEMPLATE" --serviceName "$SERVICE_NAME" "$SERVICES_FILE"


# Read nodes
#
NODES=()
while read NODE; do 
    NODES+=($NODE)
done < "$NODES_FILE"

# Read jobs
#
JOBS=()
while read JOB; do 
    [[ $JOB =~ ^#.* ]] && continue  # ignore comment lines starting with '#'
    JOBS+=($JOB)
done < "$COLLECT_DIR/jobs.txt"
echo "${#JOBS[@]} jobs"
echo "${#JOBS[@]} jobs" >> "$LOG"


# Collect input data
#
cp "$CONFIG_FILE" "$COLLECT_DIR/" 
cp "$REPLAY_FILE" "$COLLECT_DIR/replay.csv"
cp "$REPLAY_FILE" "$COLLECT_DIR/"
cp "$NODES_FILE" "$COLLECT_DIR/"
cp "$TEMPLATE" "$COLLECT_DIR/"
pushd "$DIR/.." > /dev/null
zip -r "$COLLECT_DIR/code.zip" "$(pwd)" > /dev/null
popd > /dev/null
ls -l "/var/emu/$SERVICES/" > "$COLLECT_DIR/services-ls.txt"
zip "$COLLECT_DIR/services-ls.txt.zip" "$COLLECT_DIR/services-ls.txt" > /dev/null
rm -rf "$COLLECT_DIR/services-ls.txt"


# Start SDN Controller
#
rm -rf "$RYU_READY_FILE"
pushd "$DIR/.." > /dev/null
servicesGlob="/var/emu/$SERVICES/*.yml" \
EDGE_CONFIG="$RYU_CONFIG" \
logLevel=$RYU_logLevel \
flowIdleTimeout=$idleTimeout \
useUniquePrefix=$uniquePrefix \
useUniqueMask=$uniqueMask \
readyFile="$RYU_READY_FILE" \
$RYU_EDGE > "$COLLECT_DIR/ctrl.log" &  # in background
PID_RYU=$!
echo Ryu PID = $PID_RYU
popd > /dev/null

# Show log for monitoring
#
tail -f "$COLLECT_DIR/ctrl.log" &  # in background
PID_TAIL=$!


# Copy files to NODEs (while controller is initializing its services)
#
SCP_FILES_MOD=
for file in "${SCP_FILES[@]}"; do
    SCP_FILES_MOD="$SCP_FILES_MOD $DIR/$file"
done
for node in "${NODES[@]}"; do
    echo "Copying files to $node..."
    ssh $node "mkdir -p $NODE_DIR/$RESULTS_DIR/"  # create folder
    scp -q "$DIR/$REPLAY_SCRIPT" "$REPLAY_FILE" "$SERVICES_FILE" "$CURL_DATA" $SCP_FILES_MOD $(which timecurl.sh) "$node:$NODE_DIR" # -q quiet mode
done


# Wait until controller is ready
#
while [ ! -f "$RYU_READY_FILE" ]
do
    sleep 1
done
rm -rf "$RYU_READY_FILE"


# Start flow count monitoring
#
$DIR/$FLOWS_SCRIPT $SWITCH> "$COLLECT_DIR/flowCounts.json" &  # in background
PID_FLOWS=$!

# Log CPU/memory/network stats
#
vmstat -t -w 1 > "$COLLECT_DIR/vmstat.log" &  # in background
PID_VMSTAT=$!

S_TIME_FORMAT="ISO" pidstat -d -r -u -h 1 > "$COLLECT_DIR/pidstat.log" &  # in background 
PID_PIDSTAT=$!

dstat -cdny -N enp6s0 --socket --tcp --udp --unix --aio --lock -C 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,total --output "$COLLECT_DIR/dstat.log" --noheaders --epoch >/dev/null &
PID_DSTAT=$!

# Send requests
#
# Write result file on remote device for better performance and copy it afterwards
#
SSH_PIDS=()
NODE_IDX=0
if [ ! -z "$CURL_DATA" ]; then
    CURL_DATA_BASE=$(basename "$CURL_DATA")
    CURL_PARAMS="$CURL_PARAMS --data '@$NODE_DIR/$CURL_DATA_BASE'"
fi
echo "CURL_PARAMS: $CURL_PARAMS"

echo "Start sending: $(date +'%Y%m%d-%H%M%S')" >> "$LOG"

for job in "${JOBS[@]}"; do

    # loop through nodes
    if [[ $NODE_IDX -eq ${#NODES[@]} ]]; then
        NODE_IDX=0
    fi
    node=${NODES[$NODE_IDX]}
    NODE_IDX=$((NODE_IDX+1))

    echo "Running $job at $node..."

    if [ "$USE_TIMECURL" -eq 1 ]; then
        ssh $node "unbuffer sudo python3 $NODE_DIR/$REPLAY_SCRIPT --srcIP $job --live --servicesCSV '$NODE_DIR/$SERVICES_FILE_BASE' '$NODE_DIR/$REPLAY_FILE_BASE' 2>&1 | $NODE_DIR/timecurl.sh --stdin $CURL_PARAMS > $NODE_DIR/$RESULTS_DIR/timecurl-$job-$node.json" & # run in background
    else
        ssh $node "unbuffer sudo python3 $NODE_DIR/$REPLAY_SCRIPT --srcIP $job --live --scapy '$NODE_DIR/$REPLAY_FILE_BASE' > $NODE_DIR/$RESULTS_DIR/replayRequests-$job-$node.log 2>&1" & # run in background
    fi
    SSH_PIDS+=($!)
    echo "Started $job @ $node @ $(date +'%Y%m%d-%H%M%S')" >> "$LOG"
done

echo ""
echo "Waiting for PIDs ${SSH_PIDS[*]}..."
wait ${SSH_PIDS[@]}
kill ${SSH_PIDS[@]} 2>/dev/null  # if wait is killed: kill all SSH processes
echo "End sending: $(date +'%Y%m%d-%H%M%S')" >> "$LOG"

# Collect results
#
for node in "${NODES[@]}"; do
    scp "$node:$NODE_DIR/$RESULTS_DIR/*" "$COLLECT_DIR/"
    ssh $node "rm -rf $NODE_DIR/$RESULTS_DIR/"
done


# Stop all background processes
#
kill -SIGINT $PID_RYU $PID_TAIL $PID_FLOWS $PID_VMSTAT $PID_PIDSTAT $PID_DSTAT 2>/dev/null  # be nice first (for cleanup)
sleep 1
kill $PID_RYU $PID_TAIL $PID_FLOWS $PID_VMSTAT $PID_PIDSTAT $PID_DSTAT 2>/dev/null  # send SIGTERM
# suppress bash TERMINATED messages: 
# https://stackoverflow.com/questions/81520/how-to-suppress-terminated-message-after-killing-in-bash
wait $PID_RYU $PID_TAIL $PID_FLOWS $PID_VMSTAT $PID_PIDSTAT 2>/dev/null  


# Collect remaining data
#
# FlowCounts: Replace last ',' with ']' to make it valid JSON
#
sed -i -zr 's/,([^,]*$)/\1]/' "$COLLECT_DIR/flowCounts.json"

pushd "$COLLECT_DIR" > /dev/null
echo
echo "$COLLECT_DIR"
ls -l  # or -1

# Remove provided services file (too big and in version control anyway)
#
#if [[ ! -z "$SVC_FILE" ]]; then   # param not empty
#    rm -rf "$SERVICES_FILE"
#fi


# Remove color codes from log
#
cat "$COLLECT_DIR/ctrl.log" | sed -r "s/\x1B\[([0-9]{1,3}(;[0-9]{1,2};?)?)?[mGK]//g" > "$COLLECT_DIR/ctrl.log.txt"

# Extract JSON data from log
#
# Format: #<name>: ...  -> {"<name>": ...}
#
FILE="$COLLECT_DIR/ctrl.log.json"
echo "[" > "$FILE"
cat "$COLLECT_DIR/ctrl.log.txt" | grep "\] #[a-zA-Z]" | sed -E 's/^.*\] #([^:]+)(.+)/\{\"\1\"\2\},/g' >> "$FILE"
echo "]" >> "$FILE"
# remove the last comma in the file using sed: 
# https://stackoverflow.com/questions/36823741/how-delete-last-comma-in-json-file-using-bash
sed -i -zr 's/,([^,]*$)/\1/' "$FILE"

# Fix Dstat CSV output
#
head -n 5 "$COLLECT_DIR/dstat.log" | sed 's/^/# /' > "$COLLECT_DIR/dstat.csv"  # comment out first lines
tail -n +6 "$COLLECT_DIR/dstat.log" | head -n 1 | \
    sed 's/"lis/"tcp_lis/' | sed 's/"act/"tcp_act/' | \
    sed 's/"lis/"udp_lis/' | sed 's/"act/"udp_act/' | \
    sed 's/"lis/"unix_lis/' | sed 's/"act/"unix_act/' | \
    sed 's/"epoch/"ts_sec/' >> "$COLLECT_DIR/dstat.csv" # fix duplicate names
tail -n +7 "$COLLECT_DIR/dstat.log" >> "$COLLECT_DIR/dstat.csv"  # add remaining lines
