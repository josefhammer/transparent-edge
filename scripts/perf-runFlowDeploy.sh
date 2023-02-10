#!/bin/bash

# *** Run e.g. with ***
# nohup ../transparent-edge-synced/scripts/perf-runFlowDeploy.sh perf-cfg/d.asm-hello.p tcpreplay-bigFlows.pcap.flows.csv perf-cfg/nodes20.txt 1  > ../nohup-out.txt 2>&1 &
# tail -f ../nohup-out.txt

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

if [ $# -eq 0 ]
then
    "$DIR/perf-flowDeploy.sh"
    exit 1
fi


CONFIG_BASE=$1
shift

TIMEOUTS=(5 20)
# TIMEOUTS=(20)
UNIQUE=(S P M)
#UNIQUE=(S)

SVCS=(100k-65k)

# AAG services 
#
# SVC_BASE=uniqueMask/services-aag-
# SVC_END=S.txt

# Random services
#
SVC_BASE=uniqueMask/services-rnd-
SVC_END=B.txt


for s in ${SVCS[@]}; do
    for t in ${TIMEOUTS[@]}; do
        for u in ${UNIQUE[@]}; do

            CURFILE="$CONFIG_BASE.t$t.u$u.cfg"
            echo ""
            echo "Executing $CURFILE ..."
            echo ""

            "$DIR/perf-flowDeploy.sh" "$CURFILE" "$@" "$SVC_BASE$s$SVC_END" nowait
            echo "Waiting for 20s"
            sleep 20
        done
    done
done

