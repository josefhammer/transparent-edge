#!/usr/bin/env python3
"""
Takes a Request CSV file as input an filters requests with the destination port in a given range.

Can print unique destination IP/port combinations or unique destination ports (for redirection to a file).
"""

from flowTools import FlowTools
from functools import partial
import argparse

# 1024 49151: The range of port numbers from 1024 to 49151 (2^10 to 2^14 + 2^15 − 1) are the *registered* ports.
# 49152 65535: The range 49152–65535 (2^15 + 2^14 to 2^16 − 1) contains *dynamic* or *private* ports that cannot be registered with IANA.
# https://en.wikipedia.org/wiki/List_of_TCP_and_UDP_port_numbers


def findDestIPsInPortRange(destPortStart, destPortEnd, ft: FlowTools, row):

    dstIP = row['dstIP']
    dstPort = int(row['dstPort'])

    if dstPort >= destPortStart and dstPort <= destPortEnd:

        # ip will most likely be a public IP, but better safe than sorry
        if not ft.isPrivateIP(dstIP):  # only public IP address can be a serviceIP
            ft.addStats(row['srcIP'], None, dstIP, dstPort)


def findDestInDict(dests, ft: FlowTools, row):

    dstPort = int(row['dstPort'])
    search = (row['dstIP'], dstPort)

    if search in dests:
        ft.addStats(row['srcIP'], None, row['dstIP'], dstPort)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('csvFile', help='CSV file containing the requests')
    parser.add_argument('dstPorts', nargs='?', help='These destination ports only (e.g., 80 or 80-1024)')
    parser.add_argument('--printAddrs', action='store_true', help='Print unique IP/port cominations')
    parser.add_argument('--printPorts', action='store_true', help='Print unique ports')
    parser.add_argument('--printSrcIPs', action='store_true', help='Print unique srcIPs')
    parser.add_argument('--plain', action='store_true', help='Print single column only w/o headers')
    parser.add_argument('--minNumRequests',
                        type=int,
                        nargs='?',
                        default=1,
                        help='Min number of requests to address (default: 1)')
    args = parser.parse_args()

    srcfile = args.csvFile
    minNumRequests = args.minNumRequests
    isPlain = args.plain

    dstPortStart, dstPortEnd = 0, 65535
    if args.dstPorts:
        limits = args.dstPorts.split('-')
        dstPortStart = int(limits[0])
        dstPortEnd = int(limits[1]) if len(limits) > 1 else dstPortStart

    ft = FlowTools()
    rowFn = partial(findDestIPsInPortRange, dstPortStart, dstPortEnd)

    ft.processCsv(srcfile, rowFn)

    # filter for minNumRequests
    #
    destsMinReq = {k: v for k, v in ft.dsts.items() if v >= minNumRequests}

    if minNumRequests > 1:  # need to filter again against destsMinReq
        ft = FlowTools()
        rowFn = partial(findDestInDict, destsMinReq)
        ft.processCsv(srcfile, rowFn)

    print(f"# --- Requests in '{srcfile}' for ports {dstPortStart}..{dstPortEnd} ---")
    print(f"# Num Requests: {ft.cntStatsCalls} of {ft.cntTotal} ({ft.percent(ft.cntStatsCalls,ft.cntTotal)} %)")
    print("# Num Unique SrcIPs:", len(ft.srcIPs))
    print("# Num Unique DestPorts:", len(ft.dstPorts))
    print("# Num Unique DestIP-Port Combinations:", len(ft.dsts))
    print("# Num Unique DestIP-Port Combinations >=", minNumRequests, "requests:", len(destsMinReq))
    print('#')

    if args.printAddrs:
        if not isPlain:
            print("serviceAddr,numRequests")  # header line
        for (ip, port), cnt in dict(sorted(destsMinReq.items(),
                                           key=lambda item: item[1])).items():  # sort by value, not key
            if isPlain:
                print(f"{ip}:{port}")
            else:
                print(f"{ip}:{port},{cnt}")

    if args.printPorts:
        print("servicePort")  # header line
        for port in sorted(ft.dstPorts):
            print(port)

    if args.printSrcIPs:
        if not isPlain:
            print("srcIP,numRequests")  # header line

        # sort srcIPs by request count
        #
        for ip, cnt in dict(sorted(ft.srcIPs.items(), key=lambda item: item[1])).items():  # sort by value, not key
            if isPlain:
                print(ip)
            else:
                print(f"{ip},{cnt}")
