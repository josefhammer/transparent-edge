from __future__ import annotations
from util.SocketAddr import SocketAddr
from util.IPAddr import IPAddr
from util.Service import Service
from TinyTricia import TinyTricia

import os


class TinyServiceTrie(object):

    def __init__(self, servicesDir: str, numBits=48):
        self._trie = TinyTricia(numBits)
        self._servicesDir = servicesDir

        if not os.path.exists(servicesDir):
            os.makedirs(servicesDir)
        else:
            # remove existing folder to get rid of previously created links
            #
            # remove files one by one instead of the entire folder (safer!)
            #
            for file in os.scandir(servicesDir):
                if file.path.endswith(".yml"):
                    os.remove(file)

    def set(self, addr: SocketAddr, svcFilename: str):

        if not self.contains(addr):
            self._createLink(addr, svcFilename)

        self._trie.set(addr.ip.ip << 16 | addr.port)

    def get(self, addr: SocketAddr) -> Service:
        value = self._trie.get(addr.ip.ip << 16 | addr.port)

        if value is not None:  # to save memory space, we do not store values but regenerate them on demand
            #
            # symlinks created by us do not contain the label (but: avoid resolving other symlinks)
            #
            filename = os.readlink(self.serviceFilename(addr))
            label = Service.labelFromServiceFilename(filename)

            return Service(addr, label)
        return None

    def contains(self, addr: SocketAddr) -> bool:
        return self._trie.contains(addr.ip.ip << 16 | addr.port)

    def containsIP(self, ip: IPAddr) -> bool:
        return self._trie.containsFirstNBits(ip.ip << 16)[0] >= 32

    def uniquePrefix(self, ip: IPAddr) -> tuple[int, list[int]]:
        """
        Returns (uniquePrefix, prefixes); (0,[]) if tree is empty.
        
        `uniquePrefix`: uniquePrefix for the IP (not including the port).
        `prefixes`: The parent prefixes at which the closest key is attached.
        """
        firstN, prefixes = self._trie.containsFirstNBits(ip.ip << 16)

        return firstN + 1, prefixes  # +1: the next bit must match too

    def serviceFilename(self, addr: SocketAddr):

        return os.path.join(self._servicesDir, str(addr) + '.yml')

    def _createLink(self, vAddr: SocketAddr, svcFilename: str):
        #
        # create a symlink to the original file to be able to load the service details at any time
        #
        assert svcFilename is not None
        filename = self.serviceFilename(vAddr)
        tempfilename = filename + ".tmp"
        os.symlink(svcFilename, tempfilename)  # create symlink with tempname first in case it exists already
        os.replace(tempfilename, filename)  # replace vs remove first avoids a race condition

    def __setitem__(self, key: SocketAddr, item):
        self.set(key, item)

    def __getitem__(self, key: SocketAddr):
        return self.get(key)

    def __len__(self):
        return self._trie.numKeys()

    def __iter__(self):
        return self._trie.__iter__()

    def __str__(self):
        return "[\n" + '\n'.join([
            "{} {} {} {}".format(nodeID, (self._trie.MAX_PREFIX - prefix) * ' ', prefix, value)
            for nodeID, prefix, value in self._trie
        ]) + "\n]"
