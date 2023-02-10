#!/usr/bin/env python3

import random
import ipaddress
import struct
import sys


# https://stackoverflow.com/questions/70387792/how-can-i-generate-a-random-ip-address-from-a-list-of-ip-ranges-in-python
#
def random_ip(network):
    network = ipaddress.IPv4Network(network)
    network_int, = struct.unpack("!I", network.network_address.packed)  # make network address into an integer
    rand_bits = network.max_prefixlen - network.prefixlen  # calculate the needed bits for the host part
    rand_host_int = random.randint(0, 2**rand_bits - 1)  # generate random host part
    ip_address = ipaddress.IPv4Address(network_int + rand_host_int)  # combine the parts
    return ip_address.exploded


def readRanges(filename):
    ipRanges = []
    with open(filename) as file:
        for line in file:
            if '/' in line:
                ipRanges.append(line.strip())
    return ipRanges


def randIPs(ipRanges, count):

    result = {}  # dict to avoid duplicates

    # first, make sure each ipRange is used at least once
    #
    assert (count >= len(ipRanges))
    for subnet in ipRanges:
        result[random_ip(subnet)] = 1

    # fill up with random IPs in random subnets
    #
    while len(result) < count:
        subnet = random.choice(ipRanges)
        result[random_ip(subnet)] = 1
    return result


# MAIN
#
if __name__ == "__main__":
    subnets = {}
    ipAddies = {}
    random.seed()

    if len(sys.argv) < 3:
        print("Call:" + sys.argv[0] + " subnetFile numIPs", file=sys.stderr)
        exit(1)

    subnetFile = sys.argv[1]
    numIPs = int(sys.argv[2])

    ipRanges = readRanges(subnetFile)
    print("# numSubnets =", len(ipRanges))
    print("# numIPs =", numIPs)
    print("serviceAddr")  # csv header

    ipAddies = randIPs(ipRanges, numIPs)
    for ip in ipAddies:
        print(ip)
