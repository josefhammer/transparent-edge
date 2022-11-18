#!/usr/bin/env python3

import random
import sys


def randRanges(count: int):
    """
    Creates a random list of /16 subnets.
    """
    ipRanges = {}

    while len(ipRanges) < count:
        o1 = random.randint(0, 255)
        o2 = random.randint(0, 255)

        ipRanges[f"{o1}.{o2}.0.0/16"] = 1
    return ipRanges


# MAIN
#
if __name__ == "__main__":
    random.seed()

    if len(sys.argv) < 2:
        print("Call:" + sys.argv[0] + " count", file=sys.stderr)
        exit(1)

    numSubnets = int(sys.argv[1])

    ipRanges = randRanges(numSubnets)
    for ipRange in ipRanges:
        print(ipRange)
