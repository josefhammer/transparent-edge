#!/usr/bin/env python3

import random
import sys


def readRanges(filename):
    ipRanges = []
    with open(filename) as file:
        for line in file:
            if '/' in line:
                ipRanges.append(line.strip())
    return ipRanges


def selSubnets(ipRanges, count):

    if count < (len(ipRanges) // 2):
        result = {}  # dict to avoid duplicates
        while len(result) < count:
            result[random.choice(ipRanges)] = 1
        return result
    else:
        #
        # Alternative: Remove random item from ipRanges (better when count close to len(ipRanges))
        #
        while len(ipRanges) > count:
            sel = random.randint(0, len(ipRanges))
            del ipRanges[sel]
        return ipRanges


# MAIN
#
if __name__ == "__main__":
    random.seed()

    if len(sys.argv) < 3:
        print("Call:" + sys.argv[0] + " subnetsFile count", file=sys.stderr)
        exit(1)

    ipRangesFile = sys.argv[1]
    numSubnets = int(sys.argv[2])

    ipRanges = readRanges(ipRangesFile)

    print("# Total number of available subnets:", len(ipRanges), file=sys.stderr)

    subnets = selSubnets(ipRanges, numSubnets)
    for subnet in subnets:
        print(subnet)
