#!/usr/bin/env python3
"""
Takes a Request CSV file as input an filters requests with the destination port in a given range.

Can print unique destination IP/port combinations or unique destination ports (for redirection to a file).
"""

from collections import defaultdict
import argparse
import csv

numReqestsPerReport = 1000

# 1024 49151: The range of port numbers from 1024 to 49151 (2^10 to 2^14 + 2^15 − 1) are the *registered* ports.
# 49152 65535: The range 49152–65535 (2^15 + 2^14 to 2^16 − 1) contains *dynamic* or *private* ports that cannot be registered with IANA.
# https://en.wikipedia.org/wiki/List_of_TCP_and_UDP_port_numbers


def filter(filename: str, destPortStart: int, destPortEnd: int):
    """
    Filter for values in CSV file
    """

    cnt = 0
    cntDest = 0
    dests = defaultdict(lambda: 0)
    destPorts = defaultdict(lambda: 0)

    with open(filename, newline='') as csvfile:
        next(csvfile)  # skip header line

        data = csv.reader(csvfile)
        for timediff_ms, proto, srcIP, srcPort, dstIP, dstPort in data:
            dstPort = int(dstPort)
            cnt += 1

            if dstPort >= destPortStart and dstPort <= destPortEnd:
                cntDest += 1
                destPorts[dstPort] += 1
                dests[(dstIP, dstPort)] += 1

    return cnt, cntDest, dests, destPorts


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
    args = parser.parse_args()

    srcfile = args.csvFile
    dstPortStart = args.dstPortStart
    dstPortEnd = args.dstPortEnd or dstPortStart

    cnt, cntDest, destinations, destPorts = filter(srcfile, dstPortStart, dstPortEnd)

    print(f"# --- Requests in '{srcfile}' for ports {dstPortStart}..{dstPortEnd} ---")
    print(f"# Num Requests: {cntDest} of {cnt} ({(cntDest*1000//cnt+5)//10} %)")  # +5: round up/down
    print("# Num Unique Destination Ports:", len(destPorts))
    print("# Num Unique DestIP-Port Combinations:", len(destinations))
    print('#')

    if args.printAddrs:
        for (ip, port) in sorted(destinations):
            print(f"{ip}:{port}")

    if args.printPorts:
        for port in sorted(destPorts):
            print(port)
