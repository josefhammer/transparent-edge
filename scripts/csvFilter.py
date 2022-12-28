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

    dstPort = int(row['dstPort'])

    if dstPort >= destPortStart and dstPort <= destPortEnd:
        ft.addStats(row['srcIP'], None, row['dstIP'], dstPort)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('csvFile', help='CSV file containing the requests')
    parser.add_argument('dstPortStart', type=int, help='Destination port (lower limit)')
    parser.add_argument('dstPortEnd',
                        type=int,
                        nargs='?',
                        help='Destination port (upper limit) (default: dstPortStart)')
    parser.add_argument('--printAddrs', action='store_true', help='Print unique IP/port cominations')
    parser.add_argument('--printPorts', action='store_true', help='Print unique ports')
    parser.add_argument('--printSrcIPs', action='store_true', help='Print unique srcIPs')
    parser.add_argument('--minNumRequests',
                        type=int,
                        nargs='?',
                        default=1,
                        help='Min number of requests to address (default: 1)')
    args = parser.parse_args()

    srcfile = args.csvFile
    dstPortStart = args.dstPortStart
    dstPortEnd = args.dstPortEnd or dstPortStart
    minNumRequests = args.minNumRequests

    ft = FlowTools()
    rowFn = partial(findDestIPsInPortRange, dstPortStart, dstPortEnd)

    ft.processCsv(srcfile, rowFn)

    # filter for minNumRequests
    #
    destsMinReq = {k: v for k, v in ft.dsts.items() if v >= minNumRequests}

    print(f"# --- Requests in '{srcfile}' for ports {dstPortStart}..{dstPortEnd} ---")
    print(f"# Num Requests: {ft.cntStatsCalls} of {ft.cntTotal} ({ft.percent(ft.cntStatsCalls,ft.cntTotal)} %)")
    print("# Num Unique Destination Ports:", len(ft.dstPorts))
    print("# Num Unique DestIP-Port Combinations:", len(ft.dsts))
    print("# Num Unique DestIP-Port Combinations >=", minNumRequests, "reqests:", len(destsMinReq))
    print('#')

    if args.printAddrs:
        print("serviceAddr")  # header line
        for (ip, port) in sorted(destsMinReq):

            # ip will most likely be a public IP, but better safe than sorry
            if not ft.isPrivateIP(ip):  # only public IP address can be a serviceIP
                print(f"{ip}:{port}")

    if args.printPorts:
        print("servicePort")  # header line
        for port in sorted(ft.dstPorts):
            print(port)

    if args.printSrcIPs:
        print("srcIP")  # header line
        for ip in sorted(ft.srcIPs):
            print(ip)
