#!/usr/bin/env python3
"""
Tools for filtering Pcap/CSV files.
"""

from ipaddress import ip_address
from collections import defaultdict
import itertools as it
import csv
import time


class FlowTools(object):

    def __init__(self):

        self.cntTotal = 0
        self.cntStatsCalls = 0
        self.srcs = defaultdict(lambda: 0)
        self.dsts = defaultdict(lambda: 0)
        self.srcIPs = defaultdict(lambda: 0)
        self.srcPorts = defaultdict(lambda: 0)
        self.dstIPs = defaultdict(lambda: 0)
        self.dstPorts = defaultdict(lambda: 0)

        self.cntSleep = 0
        self.startTime = None

    def addStats(self, srcIP, srcPort, dstIP, dstPort):

        self.cntStatsCalls += 1
        self.srcs[(srcIP, srcPort)] += 1
        self.dsts[(dstIP, dstPort)] += 1
        self.srcIPs[srcIP] += 1
        self.dstIPs[dstIP] += 1
        self.srcPorts[srcPort] += 1
        self.dstPorts[dstPort] += 1
        return self

    def processCsv(self, filename, rowFn):
        """
        Calls rowFn(row) for each CSV line (unless line is a header or comment).
        """
        with open(filename, newline='') as csvfile:
            #
            # use a filter to exclude comment lines (starting with '#')
            #
            dictReader = csv.DictReader(filter(lambda row: row[0] != '#', csvfile))

            self.startTime = time.time_ns()

            for row in dictReader:
                self.cntTotal += 1
                rowFn(self, row)

    def waitForRelativeTime(self, relTimeInMs):

        # wait until correct time difference
        #
        diffTime = relTimeInMs - (time.time_ns() - self.startTime) / 1000000

        while diffTime > 0:
            self.cntSleep += 1
            time.sleep(diffTime / 1000)  # sleep seconds
            diffTime = relTimeInMs - (time.time_ns() - self.startTime) / 1000000

    def isPrivateIP(self, ip):
        return ip_address(ip).is_private

    def percent(self, count, total):

        return (count * 1000 // total + 5) // 10  # +5: round up/down

