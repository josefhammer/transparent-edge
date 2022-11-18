#!/usr/bin/env python3

from scapy.layers.inet import IP, TCP, UDP
from scapy.sendrecv import send, sr
from scapy.config import conf
from collections import defaultdict
import argparse
import csv
import time

numReqestsPerReport = 1000


def getStats(filename: str):
    """
    Calculate statistics from CSV file
    """

    cnt = 0
    destIPs = {}
    srcIPs = defaultdict(lambda: 0)

    with open(filename, newline='') as csvfile:
        next(csvfile)  # skip header line

        data = csv.reader(csvfile)
        for timediff_ms, proto, srcIP, srcPort, dstIP, dstPort in data:
            cnt += 1

            destIPs[(dstIP, dstPort)] = dstIP
            srcIPs[srcIP] += 1

        print("Num Unique DestIP-Port Combinations:", len(destIPs))
        print("Num Unique SrcIPs:", len(srcIPs))
        print("Num Requests:", cnt)


def sendRequests(filename: str):
    """
    Send all requests according to timestamps in CSV file.
    """

    # to speed up sending: create a single socket and reuse that for sending
    # https://home.regit.org/2014/04/speeding-up-scapy-packets-sending/
    #
    socket = conf.L3socket(iface=conf.iface)

    cnt = cntSleep = 0
    with open(filename, newline='') as csvfile:
        next(csvfile)  # skip header line

        lastTime = startTime = time.time_ns()

        data = csv.reader(csvfile)
        for timediff_ms, proto, srcIP, srcPort, dstIP, dstPort in data:

            timediff_ms = int(timediff_ms)
            dstPort = int(dstPort)
            srcPort = int(srcPort)

            # create packet (TCP or UDP)
            #
            if proto == "6":
                packet = TCP(sport=srcPort, dport=dstPort)
            elif proto == "17":
                packet = UDP(sport=srcPort, dport=dstPort)
            else:
                print("Unexpected protocol:", proto)

            # wait until correct time difference
            #
            diffTime = timediff_ms - (time.time_ns() - startTime) / 1000000

            while diffTime > 0:
                cntSleep += 1
                time.sleep(diffTime / 1000)  # sleep seconds
                diffTime = timediff_ms - (time.time_ns() - startTime) / 1000000

            # send packet with Scapy
            #
            socket.send(IP(dst=dstIP, ttl=0) / packet)  # TTL=0 so packet will not leave the network
            cnt += 1

            if cnt >= numReqestsPerReport:

                curTime = time.time_ns()
                diff_millis = (curTime - lastTime) / 1000000
                lastTime = curTime
                print(numReqestsPerReport, "requests in", diff_millis, "ms, slept", cntSleep, "times.")
                cnt = cntSleep = 0


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('csvFile', help='CSV file containing the requests')
    args = parser.parse_args()

    srcfile = args.csvFile

    getStats(srcfile)
    sendRequests(srcfile)
