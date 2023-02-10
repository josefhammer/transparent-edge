#!/usr/bin/env python3

from flowTools import FlowTools
from functools import partial
import argparse
import sys

edgeServices = None  # (ip, port) -> 1


def addService(ft: FlowTools, row):

    global edgeServices

    ip, port = row['serviceAddr'].split(':')
    edgeServices[(ip, port)] = 1


def reqFilter(mySrcIP: str, ft: FlowTools, row):

    global edgeServices
    result = (edgeServices is None) or (row['dstIP'], row['dstPort']) in edgeServices
    proto = row.get('proto')
    result = result and (proto is None or proto == '6' or proto == '17')  # TCP, UDP

    return result if mySrcIP is None else result and mySrcIP == row['srcIP']


def getStats(ft: FlowTools, row):

    ft.addStats(row['srcIP'], None, row['dstIP'], int(row['dstPort']))


def sendRequest(isLive: bool, socket, ft: FlowTools, row):

    dstIP = row['dstIP']
    srcPort = int(row['srcPort'])
    dstPort = int(row['dstPort'])

    if isLive:
        timestamp = row.get('relStartTimestampInSec')
        timestamp = float(timestamp) * 1000 if timestamp is not None else int(row['timediff_ms'])
        ft.waitForRelativeTime(timestamp)

    if not socket:
        print(f"{ft.index} {dstIP}:{dstPort}", file=sys.stderr)  # stderr is unbuffered
    else:
        # create packet (TCP or UDP)
        #
        if row['proto'] == '6':
            packet = TCP(sport=srcPort, dport=dstPort)
        else:
            packet = UDP(sport=srcPort, dport=dstPort)

        # send packet with Scapy
        #
        socket.send(IP(dst=dstIP, ttl=0) / packet)  # TTL=0 so packet will not leave the network


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('requestsCSV', help='CSV file containing the requests')
    parser.add_argument('--srcIP', help='Process only requests from this srcIP')
    parser.add_argument('--live', action='store_true', help='Process requests according to timestamps')
    parser.add_argument('--scapy', action='store_true', help='Send TCP/UDP packets using Scapy')
    parser.add_argument('--servicesCSV', help='Process only requests to these destination addresses')
    args = parser.parse_args()

    srcfile = args.requestsCSV
    svcfile = args.servicesCSV

    if svcfile:
        edgeServices = {}
        ft = FlowTools()
        ft.processCsv(svcfile, addService)

    fnFilter = partial(reqFilter, args.srcIP)

    ft = FlowTools()
    ft.processCsv(srcfile, getStats, fnFilter)

    # print stats
    print("# Num Unique SrcIPs:", len(ft.srcIPs))
    print("# Num Unique DestIP-Port Combinations:", len(ft.dsts))
    print(f"# Num Requests: {ft.cntStatsCalls} of {ft.cntTotal} ({ft.percent(ft.cntStatsCalls,ft.cntTotal)} %)")

    ft = FlowTools()
    socket = None
    if not args.scapy:
        ft.processCsv(srcfile, partial(sendRequest, args.live, socket), fnFilter)

    else:
        from scapy.layers.inet import IP, TCP, UDP
        from scapy.config import conf as scapyConf

        # to speed up sending: create a single socket and reuse that for sending
        # https://home.regit.org/2014/04/speeding-up-scapy-packets-sending/
        #
        socket = scapyConf.L3socket(iface=scapyConf.iface)

        ft.processCsv(srcfile, partial(sendRequest, args.live, socket), fnFilter)
