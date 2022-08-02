#!/bin/bash

alias miniedit='sudo ~/mininet/examples/miniedit.py'

export RYU_EDGE="ryu-manager ./EdgeMainRyu.py --log-config-file=./config/ryu-log.cfg"
export EDGE_SINGLE="EDGE_CONFIG='config/edge-single.json'"
export EDGE_SINGLE_EPORT="EDGE_CONFIG='config/edge-single-eport.json'"
export EDGE_DOUBLE="EDGE_CONFIG='config/edge-double.json'"

export LL_INFO="EDGE_LOGLEVEL='INFO'"
export LL_WARN="EDGE_LOGLEVEL='WARN'"
export LL_DEBUG="EDGE_LOGLEVEL='DEBUG'"

alias ry="$LL_INFO $EDGE_SINGLE $RYU_EDGE"
alias ryd="$LL_DEBUG $EDGE_SINGLE $RYU_EDGE"
alias ryperf="$LL_WARN $EDGE_SINGLE $RYU_EDGE"
alias ryperfeport="$LL_WARN $EDGE_SINGLE_EPORT $RYU_EDGE"
alias ryeport="$EDGE_SINGLE_EPORT $RYU_EDGE"

alias ry2="$EDGE_DOUBLE $RYU_EDGE"

alias dfl="sudo ovs-ofctl dump-flows o-bs1 | grep -v 'table=3' | grep -v 'table=4';echo '--';sudo ovs-ofctl dump-flows o-cloudgw"
