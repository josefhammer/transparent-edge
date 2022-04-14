from .Context import Context
from util.EdgeTools import Edge
from util.SocketAddr import SocketAddr
from util.Service import ServiceInstance, Service
from util.RyuDPID import DPID
from util.IPAddr import IPAddr
from util.TinyServiceTrie import TinyServiceTrie

import os
import glob
import json
import socket


class ServiceManager:
    """
    Manages the available services.
    """

    # REVIEW Might have to be synchronized due to parallel access.

    def __init__(self, context: Context, log, svcFolder, fileExt):

        self.ctx = context
        self.log = log

        self._services: TinyServiceTrie = TinyServiceTrie(keysOnly=True)  # SocketAddr

        if svcFolder != None:
            self.loadServices(svcFolder, fileExt)

    def isService(self, addr: SocketAddr):
        return self._services.contains(addr)

    def isServiceIP(self, ip: IPAddr):
        return self._services.containsIP(ip)

    def uniquePrefix(self, ip: IPAddr):
        return self._services.uniquePrefix(ip)

    def isServer(self, dpid, addr: SocketAddr):
        return dpid in self.ctx.edges and addr in self.ctx.edges[dpid].nServices

    def loadServices(self, folder, fileExt):

        files = glob.glob(os.path.join(folder, '*' + fileExt))

        for filename in files:
            with open(filename) as file:

                edgeIP = os.path.basename(filename).split(fileExt)[0]

                switch = None
                for dpid, edge in self.ctx.edges.items():
                    if edge.ip == IPAddr(edgeIP):
                        switch = dpid
                        break

                edge = self.ctx.edges.get(switch)
                if edge is not None:  # included in the current configuration?
                    self.parseServices(switch, edge, json.load(file))

    def parseServices(self, switch: DPID, edge: Edge, data: dict):

        for item in data['items']:
            svcInstance = self.parseServiceInfo(edge, item)

            if svcInstance is not None:
                svc = svcInstance.service

                # Add Service to global ServiceTrie
                #
                if not self._services.contains(svc.vAddr):
                    self._services.set(svc.vAddr)
                    self.log.info("ServiceID {}:{} {} -> {}".format(
                        svc.vAddr.ip, svc.vAddr.port, '(' + svc.domain + ')' if svc.domain else '', svc.name))
                # else:
                #     assert service.domain == svc.domain and service.name == svc.name  # same service in all edges

                # Add ServiceInstance to edge (register with IP addresses for both directions if different)
                #
                edge.vServices[svcInstance.service.
                               vAddr] = svcInstance  # REVIEW Requires to have a single instance only
                edge.eServices[svcInstance.eAddr] = svcInstance
                edge.nServices[svcInstance.nAddr] = svcInstance

                self.log.info("ServiceInstance @ {}: {}".format(switch, svcInstance))

    def parseServiceInfo(self, edge: Edge, data: dict) -> ServiceInstance:

        meta = data['metadata']
        spec = data['spec']
        ports = spec.get('ports')
        domain = meta.get('annotations', {}).get('edge.serviceDomain')

        if not domain or meta.get('namespace') != 'edge':
            return None

        name = meta.get('labels', {}).get('run')
        if not name:
            name = meta.get('name')
        type = spec.get('type')  # e.g. "LoadBalancer"

        # TODO/REVIEW: Currently, we only consider the first ports entry. That might not be the closest one.
        # So we might have to create multiple instances (unless we use NodePort forwarding anyway).

        port = ports[0].get('port')  # servicePort e.g. 5000
        if type == "LoadBalancer":
            ePort = port
        else:
            ePort = ports[0].get('nodePort')  # ATTENTION: We use the 'node'Port as edgePort !! e.g. 31097
            if ePort == None:
                ePort = 0

        parts = domain.split(':')
        domain = parts[0]
        vPort = port  # default: same port as servicePort (to make things simpler)
        if len(parts) == 2:  # unless defined in the annotation
            vPort = parts[1]

        vAddr = SocketAddr(self.get_ipv4_by_hostname(domain)[0], vPort)
        eAddr = SocketAddr(edge.ip, ePort)
        nAddr = SocketAddr(spec.get('clusterIP'), port)  # nodeAddr

        if domain == vAddr.ip:
            domain = ""

        return ServiceInstance(Service(vAddr, domain, name), eAddr, nAddr)

    def get_ipv4_by_hostname(self, hostname):
        #
        # Source: https://stackoverflow.com/questions/2805231/how-can-i-do-dns-lookups-in-python-including-referring-to-etc-hosts
        #
        return list(i  # raw socket structure
                    [4]  # internet protocol info
                    [0]  # address
                    for i in socket.getaddrinfo(
                        hostname,
                        0  # port, required
                    ) if i[0] is socket.AddressFamily.AF_INET  # ipv4

                    # ignore duplicate addresses with other socket types
                    and i[1] is socket.SocketKind.SOCK_RAW)
