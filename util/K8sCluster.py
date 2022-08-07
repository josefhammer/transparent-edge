from __future__ import annotations

# Disable the warnings triggered by verify_ssl=False
#
import urllib3
urllib3.disable_warnings()  # https://urllib3.readthedocs.io/en/1.26.x/advanced-usage.html#ssl-warnings

from kubernetes import client, utils
from kubernetes.client.rest import ApiException

from util.IPAddr import IPAddr
from util.Service import Deployment, ServiceInstance, Service
from util.SocketAddr import SocketAddr
from util.K8sService import K8sService

from logging import WARNING, getLogger


class K8sCluster:
    """
    Interface to a single Kubernetes cluster.
    """

    def __init__(self, apiServer, tokenFileName, namespace="edge", labelName="edge.service", log=None):

        # disable debug logs from the REST client
        client.rest.logger.setLevel(WARNING)

        self._ip = IPAddr(apiServer.split(":")[0])
        self._namespace = namespace
        self._labelName = labelName
        self._log = log
        if self._log is None:
            self._log = getLogger("K8s")

        self._apiClient = self._apiClient(apiServer, tokenFileName)

        self._k8s = client.CoreV1Api(self._apiClient)
        self._k8sApps = client.AppsV1Api(self._apiClient)

    def services(self, label: str, target: str):

        result = []
        services = self._getItems(label, self._k8s.list_namespaced_service)

        for item in services:
            item.kind = "Service"  # unfortunately, it's returned as None

            svcInstance = K8sService(label=None, yml=[item.to_dict()]).toService(self._ip, target)

            if isinstance(svcInstance, ServiceInstance):
                result.append(svcInstance)

            # REVIEW What should happen if no ClusterIP is yet set up and thus we don't get a ServiceInstance?
        return result

    def deployments(self, label=None):

        items = self._getItems(label, self._k8sApps.list_namespaced_deployment)

        return [
            Deployment(
                i.metadata.labels.get(self._labelName), self._noneToZero(i.status.available_replicas),
                self._noneToZero(i.status.ready_replicas)) for i in items
        ]

    def pods(self, label=None):

        items = self._getItems(label, self._k8s.list_namespaced_pod)

        return [i.to_dict() for i in items]

    def endpoints(self, label=None):

        items = self._getItems(label, self._k8s.list_namespaced_endpoints)

        return [i.to_dict() for i in items]

    def applyYaml(self, filename=None, yml=None):
        """
        Pass either filename or file content (`yaml.safe_load_all(filename)`).
        
        See <https://github.com/kubernetes-client/python/blob/0553bba32dd5f2029a086131c893f0b295ac4297/kubernetes/utils/create_from_yaml.py#L97>
        """
        try:
            utils.create_from_yaml(self._apiClient, yaml_file=filename, yaml_objects=yml, namespace=self._namespace)
        except Exception as e:
            self._log.warn(e)

    def _noneToZero(self, value):

        return 0 if value is None else value

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

    def _labelSelector(self, label):

        return None if not label else self._labelName + "=" + label

    def _filterLabelAvailable(self, items):

        return filter(lambda i: i.metadata and i.metadata.labels and i.metadata.labels.get(self._labelName), items)

    def _filterNamespace(self, items):

        return filter(lambda item: self._namespace == item.metadata.namespace, items)

    def _getItems(self, label, func):

        try:
            ret = func(self._namespace, label_selector=self._labelSelector(label))
            # return self._filterNamespace(self._filterLabelAvailable(ret.items))
            return self._filterLabelAvailable(ret.items)

        except ApiException as e:
            self._log.warn(e)
            return []
