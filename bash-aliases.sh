#!/bin/bash

alias miniedit='sudo python2 ~/mininet/examples/miniedit.py'

alias lsEdgeDocker='docker ps --filter label=edge.service --filter label=edge.port'
alias lsallEdgeDocker='lsEdgeDocker -a'
alias stopEdgeDocker='docker container stop $(lsEdgeDocker -q)'
alias killEdgeDocker='echo $(lsEdgeDocker -q | wc -l); docker kill $(lsEdgeDocker -q)'
alias rmEdgeDocker='echo $(lsEdgeDocker -a -q | wc -l); docker container rm $(lsEdgeDocker -a -q)'
alias lsEdgeK8s='kubectl -n edge get svc'
alias killEdgeK8s='echo $(lsEdgeK8s --no-headers 2>/dev/null | wc -l); kubectl -n edge scale --replicas=0 deployments -l edge.service'
# without removing the replicasets, pods keep getting created
alias rmEdgeK8s='echo $(lsEdgeK8s --no-headers 2>/dev/null | wc -l); kubectl -n edge delete svc,deployments,replicasets,pod --all'

export RYU_EDGE="ryu-manager ./EdgeMainRyu.py --log-config-file=./config/ryu-log.cfg"
export EDGE_SINGLE="EDGE_CONFIG='config/edge-single.json'"
export EDGE_SINGLE_EPORT="EDGE_CONFIG='config/edge-single-eport.json'"
export EDGE_DOUBLE="EDGE_CONFIG='config/edge-double.json'"
export EDGE_GATEWAY="EDGE_CONFIG='config/edge-gateway.json'"
export EDGE_GATEWAYD="EDGE_CONFIG='config/edge-gateway-docker.json'"
export EDGE_GW8="EDGE_CONFIG='config/edge-gw8.json'"
export EDGE_GWD="EDGE_CONFIG='config/edge-gwd.json'"

export LL_INFO="logLevel='INFO'"
export LL_WARN="logLevel='WARN'"
export LL_DEBUG="logLevel='DEBUG'"

alias ry="$LL_INFO $EDGE_SINGLE $RYU_EDGE"
alias ryd="$LL_DEBUG $EDGE_SINGLE $RYU_EDGE"
alias ryperf="$LL_WARN $EDGE_SINGLE $RYU_EDGE"
alias ryperfeport="$LL_WARN $EDGE_SINGLE_EPORT $RYU_EDGE"
alias ryeport="$EDGE_SINGLE_EPORT $RYU_EDGE"
alias rygw="$LL_INFO $EDGE_GATEWAY $RYU_EDGE"
alias rygwdocker="$LL_INFO $EDGE_GATEWAYD $RYU_EDGE"
alias rygw8="$LL_INFO $EDGE_GW8 $RYU_EDGE"
alias rygwd="$LL_INFO $EDGE_GWD $RYU_EDGE"

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
