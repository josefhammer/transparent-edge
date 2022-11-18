#!/usr/bin/env python3

import shutil
import os
import sys


def readIPs(filename):
    ips = []
    with open(filename) as file:
        for line in file:
            if not line.startswith('#') and '.' in line:
                ips.append(line.strip())
    return ips


# MAIN
#
if __name__ == "__main__":
    template = "/var/emu/services/at.aau.scalingtest.17.yml"
    baseFolder = "/var/emu/"

    if len(sys.argv) < 2:
        print("Call:" + sys.argv[0] + " ipFile", file=sys.stderr)
        exit(1)

    ipFile = sys.argv[1]

    ips = readIPs(ipFile)
    setName = os.path.basename(ipFile).rsplit(".", 1)[0]
    print("#IPs =", len(ips), "Set =", setName, file=sys.stderr)

    folder = os.path.join(baseFolder, setName)

    print(folder)

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
        os.symlink(template, os.path.join(folder, addr + ".scalingtest.17.yml"))  # port 17:
