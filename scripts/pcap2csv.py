#!/usr/bin/env python3

from scapy.utils import RawPcapReader
from scapy.layers.l2 import Ether
from scapy.layers.inet import IP
from ipaddress import ip_address
from collections import defaultdict
import argparse
import os

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('pcapFile', help='pcap file')
    parser.add_argument('--excludeSource',
                        help="Exclude (srcIP, srcPort) from result",
                        action='store_true',
                        default=False)
    parser.add_argument('--dupsInterval',
                        help='Skip identical requests within this interval (ms; default=1000; 0 for all requests)',
                        type=int,
                        default=1000,
                        required=False)
    args = parser.parse_args()

    excludeSource = args.excludeSource
    dupsInterval = args.dupsInterval
    srcfile = args.pcapFile

    dstbase = srcfile + ('.all' if not dupsInterval else ('.tiny' if excludeSource else '.flows'))
    dstfile = dstbase + ".csv"
    statsfile = dstbase + ".stats.json"
    uniquefile = dstbase + ".unique.csv"

    # config
    maxBuffer = 5000

    #Required internal vars
    cntPcap = 0
    cntWritten = 0
    cntInternal = 0
    cntDups = 0
    cntBuffer = 0
    buffer = []

    firstTimestampSec = 0
    firstTimestampUSec = 0
    prevTimes = defaultdict(lambda: 0)

    containsPrivateIPs = containsEtherPacket = "CAIDA" not in dstfile
    chooseDirection = "CAIDA" in dstfile

    with open(dstfile, 'w') as dst:
        dst.write('timediff_ms,proto,')
        if not excludeSource: dst.write('srcIP,srcPort,')
        dst.write('dstIP,dstPort\n')

        for (pkt_data, pkt_metadata) in RawPcapReader(srcfile):

            cntPcap += 1

            if containsEtherPacket:
                ether_pkt = Ether(pkt_data)

                if 'type' not in ether_pkt.fields: continue  # LLC frames will have 'len' instead of 'type'.
                if ether_pkt.type != 0x0800: continue  # disregard non-IPv4 packets

                ip_pkt = ether_pkt[IP]
            else:
                # CAIDA data contains not Ethernet packets
                #
                ip_pkt = IP(pkt_data)

            if ip_pkt.payload:
                try:
                    if ip_pkt.proto == 6 or ip_pkt.proto == 17:  # if UDP or TCP
                        srcPort, dstPort = ip_pkt.payload.sport, ip_pkt.payload.dport
                    else:
                        continue  # filter non TCP-UDP packets
                except:
                    continue

            proto = ip_pkt.proto
            srcIP = ip_pkt.src
            dstIP = ip_pkt.dst

            # which direction?
            #
            if chooseDirection and (dstPort > srcPort):  # rough assumption: the lower port# is the destination address
                (srcIP, srcPort) = (dstIP, dstPort)  # reverse direction

            # skip network internal traffic
            #
            if containsPrivateIPs:
                if ip_address(dstIP).is_private:  # only requests to public IP addresses
                    cntInternal += 1
                    continue

            # timestamp
            timestampSec = pkt_metadata.sec
            timestampUSec = pkt_metadata.usec

            if not firstTimestampSec:
                firstTimestampSec = timestampSec
                firstTimestampUSec = timestampUSec

            # calculate relative time to first request in ms
            #
            timestamp = (timestampSec - firstTimestampSec) * 1000 + ((timestampUSec - firstTimestampUSec) // 1000)

            if dupsInterval:
                # skip identical requests with a certain time period
                #
                key = (proto, dstIP, dstPort) if excludeSource else (proto, srcIP, srcPort, dstIP, dstPort)

                prevTime = prevTimes.get(key)
                if None == prevTime:
                    prevTimes[key] = timestamp
                else:
                    if timestamp < (prevTime + dupsInterval):
                        cntDups += 1
                        continue  # skip request (same flow)  # do not update timestamp to keep flow in switch alive (1 request every second)
                    else:
                        # update timestamp for the following requests (but do not skip this one)
                        #
                        prevTimes[key] = timestamp

            # add CSV line to buffer
            #
            if excludeSource:
                buffer.append('{},{},{},{}'.format(timestamp, proto, dstIP, dstPort))
            else:
                buffer.append('{},{},{},{},{},{}'.format(timestamp, proto, srcIP, srcPort, dstIP, dstPort))
            cntBuffer += 1

            if cntBuffer >= maxBuffer:
                #
                # write buffer to disk
                #
                dst.write('\n'.join(buffer) + '\n')
                cntWritten += cntBuffer
                cntBuffer = 0
                buffer = []
                print('Parsed packets: {}, written: {}'.format(cntPcap, cntWritten), end='\r')

        # write items remaining in buffer
        #
        if cntBuffer > 0:
            dst.write('{}\n'.format('\n'.join(buffer)))
            cntWritten += cntBuffer
            print('Parsed packets: {}, written: {}'.format(cntPcap, cntWritten))

    print('Done. Total packets={}, written packets={}'.format(cntPcap, cntWritten))

    numOther = cntPcap - cntInternal - cntDups - cntWritten
    numUnique = len(prevTimes)

    with open(statsfile, 'w') as stats:
        stats.write(
            '{\n' + f'"src":"{os.path.basename(srcfile)}",\n"excludeSource":{str(excludeSource).lower()},\n' +
            f'"numPcap":{cntPcap},\n"numInternal":{cntInternal},\n"numOther":{numOther},\n' +
            f'"numDups":{cntDups},\n"dupsIntervalMSec":{dupsInterval},\n"numUnique":{numUnique},\n' +
            f'"numCSV":{cntWritten},\n"baseTimeSec":{firstTimestampSec},\n"baseTimeUSec":{firstTimestampUSec}\n' +
            '}\n')

    if dupsInterval:  # otherwise we did not create the dict (for performance reasons)
        with open(uniquefile, 'w') as uniq:
            if excludeSource:
                uniq.write('proto,dstIP,dstPort\n')
                for (proto, dstIP, dstPort) in prevTimes:
                    uniq.write(f'{proto},{dstIP},{dstPort}\n')
            else:
                uniq.write('proto,srcIP,srcPort,dstIP,dstPort\n')
                for (proto, srcIP, srcPort, dstIP, dstPort) in prevTimes:
                    uniq.write(f'{proto},{srcIP},{srcPort},{dstIP},{dstPort}\n')
