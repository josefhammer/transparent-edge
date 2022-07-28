#!/bin/bash

alias miniedit='sudo ~/mininet/examples/miniedit.py'

export RYU_EDGE="ryu-manager ./EdgeMainRyu.py --log-config-file=./config/ryu-log.cfg"

alias ry="EDGE_CONFIG='config/edge-single.json' $RYU_EDGE"
alias ryperf="EDGE_LOGLEVEL='WARN' EDGE_CONFIG='config/edge-single.json' $RYU_EDGE"
alias ryperfeport="EDGE_LOGLEVEL='WARN' EDGE_CONFIG='config/edge-single-eport.json' $RYU_EDGE"
alias ryeport="EDGE_CONFIG='config/edge-single-eport.json' $RYU_EDGE"

alias ry2="EDGE_CONFIG='config/edge-double.json' $RYU_EDGE"

alias dfl="sudo ovs-ofctl dump-flows o-bs1 | grep -v 'table=3' | grep -v 'table=4';echo '--';sudo ovs-ofctl dump-flows o-cloudgw"
