#!/bin/bash

alias miniedit='sudo ~/mininet/examples/miniedit.py'

export RYU_EDGE="ryu-manager ./EdgeMainRyu.py --log-config-file=./config/ryu-log.cfg"
export EDGE_SINGLE="EDGE_CONFIG='config/edge-single.json'"
export EDGE_SINGLE_EPORT="EDGE_CONFIG='config/edge-single-eport.json'"
export EDGE_DOUBLE="EDGE_CONFIG='config/edge-double.json'"
export EDGE_GATEWAY="EDGE_CONFIG='config/edge-gateway.json'"

export LL_INFO="EDGE_LOGLEVEL='INFO'"
export LL_WARN="EDGE_LOGLEVEL='WARN'"
export LL_DEBUG="EDGE_LOGLEVEL='DEBUG'"

alias ry="$LL_INFO $EDGE_SINGLE $RYU_EDGE"
alias ryd="$LL_DEBUG $EDGE_SINGLE $RYU_EDGE"
alias ryperf="$LL_WARN $EDGE_SINGLE $RYU_EDGE"
alias ryperfeport="$LL_WARN $EDGE_SINGLE_EPORT $RYU_EDGE"
alias ryeport="$EDGE_SINGLE_EPORT $RYU_EDGE"
alias rygw="$LL_INFO $EDGE_GATEWAY $RYU_EDGE"

alias ry2="$EDGE_DOUBLE $RYU_EDGE"

alias dfl="sudo ovs-ofctl dump-flows o-bs1 | grep -v 'table=3' | grep -v 'table=4';echo '--';sudo ovs-ofctl dump-flows o-cloudgw"

# cookie value/mask
DETECT_EDGE="19/19"
DETECT_DEFAULT="35/35"
REDIR_EDGE="76/76"
REDIR_DEFAULT="140/140"
FLOWS="$DETECT_EDGE $DETECT_DEFAULT $REDIR_EDGE $REDIR_DEFAULT"

alias stats='(
for COOKIE in $FLOWS
do
    sudo ovs-ofctl dump-aggregate o-bs1 cookie=$COOKIE | cut -d ':' -f 2 
done
)'
