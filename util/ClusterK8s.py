# Disable the warnings triggered by verify_ssl=False
#
import urllib3
urllib3.disable_warnings()  # https://urllib3.readthedocs.io/en/1.26.x/advanced-usage.html#ssl-warnings

from kubernetes import client
from kubernetes.client.rest import ApiException

from util.IPAddr import IPAddr
from util.Service import ServiceInstance, Service
from util.SocketAddr import SocketAddr

from logging import WARNING


class ClusterK8s:
    """
    Interface to a single Kubernetes cluster.
    """

    def __init__(self, apiServer, tokenFileName):

        # disable debug logs from the REST client
        client.rest.logger.setLevel(WARNING)

        self._ip = IPAddr(apiServer.split(":")[0])

        apiClient = self._apiClient(apiServer, tokenFileName)

        self._k8s = client.CoreV1Api(apiClient)
        self._k8sApps = client.AppsV1Api(apiClient)

    def _apiClient(self, apiServer, tokenFileName):

        token = self._readToken(tokenFileName)

        if token:
            cfg = client.Configuration()  # create new config object
            cfg.host = "https://" + apiServer  # specify the endpoint of our K8s cluster
            cfg.api_key = {"authorization": "Bearer " + token}

            # REVIEW: for simplicity, we do not verify the SSL certificate here
            #
            # if verification is used, then add: cfg.ssl_ca_cert="file name of certificate"
            #
            cfg.verify_ssl = False

            return client.ApiClient(cfg)  # create API client
        return None

    def _readToken(self, tokenFileName):
        """
        Reads the authentication token from the file given with the filename. 
        """
        try:
            with open(tokenFileName) as file:
                #
                # read auth token (see https://kubernetes.io/docs/tasks/access-application-cluster/access-cluster/)
                #
                return file.read()

        except FileNotFoundError:
            return None

    def getServices(self):

        services = []
        try:
            ret = self._k8s.list_service_for_all_namespaces(watch=False)
        except Exception as e:
            print(e)
            return services

        for item in ret.items:
            if "edge" == item.metadata.namespace:

                svcInstance = self.parseServiceInfo(item.to_dict())
                if svcInstance is not None:
                    services.append(svcInstance)

        return services

    def parseServiceInfo(self, data: dict) -> ServiceInstance:

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
            # ATTENTION: We use the 'node'Port as edgePort !! e.g. 31097
            ePort = ports[0].get('node_port')  # 'nodePort' when exported via kubectl
            if ePort == None:
                ePort = 0

        parts = domain.split(':')
        domain = parts[0]
        vPort = port  # default: same port as servicePort (to make things simpler)
        if len(parts) == 2:  # unless defined in the annotation
            vPort = parts[1]

        vAddr = SocketAddr(IPAddr.get_ipv4_by_hostname(domain)[0], vPort)
        eAddr = SocketAddr(self._ip, ePort)
        nAddr = SocketAddr(spec.get('cluster_ip'), port)  # nodeAddr; 'clusterIP' when exported via kubectl

        if domain == vAddr.ip:
            domain = ""

        return ServiceInstance(Service(vAddr, domain, name), eAddr, nAddr)

