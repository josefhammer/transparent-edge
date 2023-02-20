#!/usr/bin/env python3

from flowTools import FlowTools

import shutil
import os
import sys
import argparse

ips = []


def addService(ft: FlowTools, row):

    global ips
    ips.append(row['serviceAddr'])


# MAIN
#
if __name__ == "__main__":
    # template = "/var/emu/services/at.aau.scalingtest.17.yml"
    template = "/var/emu/services/at.aau.helloworld-asm.8081.yml"
    baseFolder = "/var/emu/"

    parser = argparse.ArgumentParser()
    parser.add_argument('ipFile', help='File containing the IP addresses')
    parser.add_argument('--template', help='Template file for services to be generated')
    parser.add_argument('--serviceName', help='Name of the service to be generated')
    args = parser.parse_args()

    ipFile = args.ipFile
    template = args.template or template
    svcName = args.serviceName or "scalingtest"

    ft = FlowTools()
    ft.processCsv(ipFile, addService)

    setName = os.path.basename(ipFile).rsplit(".", 1)[0]  # the name of the set of service IPs
    print("#IPs =", len(ips), "Set =", setName, file=sys.stderr)

    folder = os.path.join(baseFolder, setName)

    print(folder)

    if not os.path.exists(baseFolder):
        print("BaseFolder does not exist")
        exit(1)

    # remove existing folder
    if os.path.exists(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)

    for addr in ips:
        #
        # Port 17: The Quote of the Day (QOTD) service is a member of the Internet protocol suite, defined in RFC 865.
        # As indicated there, the QOTD concept predated the specification, when QOTD was used by mainframe sysadmins
        # to broadcast a daily quote on request by a user. It was then formally codified both for prior purposes as
        # well as for testing and measurement purposes.
        #
        port = '17'  # default port: highly unlikely to collide with any IP/port combination

        parts = addr.split(':')
        if len(parts) > 1:
            addr = parts[0]
            port = parts[1]

        os.symlink(template, os.path.join(folder, f"{addr}.{svcName}.{port}.yml"))
