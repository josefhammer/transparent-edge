#!/bin/bash

SERVICE=143.205.180.42
DIRECT=10.0.3.100

IF=`ip route | grep 10.42.0.0  | grep -o -e "dev \w*" | cut -f2 -d " "`

if [ "$IF" == "eth0" ]
then
    NODE=3
    VLAN=103
else
    NODE=15
    VLAN=115
fi

DIRECT_PORT=`ssh node$NODE kubectl get svc | grep edge-nginx | egrep -o "5000:[0-9]*" | cut -f2 -d ":"`

sudo ovs-ofctl del-flows o-cloudgw "tcp,nw_dst=$SERVICE"
sudo ovs-ofctl del-flows o-cloudgw "tcp,nw_src=$DIRECT"

echo "--- Empty ---"
sudo ovs-ofctl dump-flows o-cloudgw
echo ""
sudo ovs-ofctl add-flow o-cloudgw "priority=65535,tcp,nw_src=10.0.0.0/16,nw_dst=$SERVICE,tp_dst=80 actions=mod_dl_dst:02:00:00:00:03:01,mod_nw_dst:$DIRECT,mod_tp_dst:$DIRECT_PORT,output:$IF.$VLAN"
sudo ovs-ofctl add-flow o-cloudgw "priority=65535,tcp,nw_src=$DIRECT,nw_dst=10.0.1.100,tp_src=$DIRECT_PORT actions=mod_dl_src:02:00:00:00:00:03,mod_nw_src:$SERVICE,mod_tp_src:80,output:v-cloudgw-bs1"

echo "--- Configured ---"
sudo ovs-ofctl dump-flows o-cloudgw
