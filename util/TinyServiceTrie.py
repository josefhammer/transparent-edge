from util.SocketAddr import SocketAddr
from util.IPAddr import IPAddr
from util.Service import Service
from TinyTricia import TinyTricia


class TinyServiceTrie(object):
    def __init__(self, numBits=48, keysOnly=False):
        self._trie = TinyTricia(numBits, keysOnly=keysOnly)

    def set(self, addr: SocketAddr, svc: Service = None):
        self._trie.set(addr.ip.ip << 16 | addr.port, svc)

    def get(self, addr: SocketAddr) -> Service:
        key, value = self._trie.get(addr.ip.ip << 16 | addr.port)

        if key is None:
            return None

        if value is None:
            return Service(addr)
        return value

    def contains(self, addr: SocketAddr) -> bool:
        return self._trie.contains(addr.ip.ip << 16 | addr.port)

    def containsIP(self, ip: IPAddr) -> bool:
        return self._trie.containsFirstNBits(ip.ip << 16) >= 32

    def uniquePrefix(self, ip: IPAddr):  # uniquePrefix for IP (not including the port)
        return self._trie.containsFirstNBits(ip.ip << 16) + 1  # +1: the next bit must match too

    def __setitem__(self, key: SocketAddr, item):
        self.set(key, item)

    def __getitem__(self, key: SocketAddr):
        return self.get(key)

    def __len__(self):
        return self._trie.numKeys()

    def __iter__(self):
        return self._trie.__iter__()
