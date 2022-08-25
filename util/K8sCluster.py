from __future__ import annotations

# Disable the warnings triggered by verify_ssl=False
#
import urllib3
urllib3.disable_warnings()  # https://urllib3.readthedocs.io/en/1.26.x/advanced-usage.html#ssl-warnings

from kubernetes import client, config, utils
from kubernetes.client.rest import ApiException

from collections import defaultdict

from util.IPAddr import IPAddr
from util.Service import Deployment, Pod, ServiceInstance, Service
from util.SocketAddr import SocketAddr
from util.K8sService import K8sService

from logging import WARNING, getLogger

import time


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

    def deployService(self, service: K8sService, target: str):  # REVIEW Remove target param?

        assert (service and service.yaml)
        self.applyYaml(yml=service.yaml)
        self._log.info("Service " + str(service) + " deployed.")

        svcInsts = self.services(service.label, target)

        if svcInsts:
            svcInst = svcInsts[0]
            if not svcInst:
                return None

            # TODO Replace with 'watch'
            #
            # Unfortunately, filtering pods by label is not perfectly reliable. Should use pod-template-hash instead:
            # (https://stackoverflow.com/questions/52957227/kubectl-command-to-list-pods-of-a-deployment-in-kubernetes)
            #
            # E.g., here the IP of a previous POD is used (and thus it does not work):
            #
            # [K8s        ] Deployment: ready=1 podStatus=Running podIP=10.1.100.160     # <-- should be 162 already
            # [ServiceMngr] ServiceInstance @ #1: 143.205.180.80:80 (at.aau.hostinfo) @ 10.0.2.100 (10.1.100.160:80)
            #
            while (True):

                pods = self.pods(service.label)
                deps = self.deployments(service.label)

                if len(pods) and len(deps):
                    self._log.debug("Deployment: ready={} podStatus={} podIP={}".format(
                        deps[0].ready_replicas, pods[0].status, pods[0].ip))

                if len(deps) and deps[0].ready_replicas:

                    svcInst.deployment = deps[0]
                    break
                time.sleep(0.1)

            return svcInst
        return None

    def services(self, label: str, target: str):

        return self._toMap(label, self.rawServices, lambda i: self._apiResponseToService(i, target))

    def _apiResponseToService(self, i, target):

        i.kind = "Service"  # unfortunately, it's returned as None
        return K8sService(label=None, yml=[i.to_dict()]).toService(self._ip, target)

    def deployments(self, label=None):

        return self._toMap(label, self.rawDeployments,
            lambda i: Deployment(self._noneToZero(i.status.available_replicas),
                self._noneToZero(i.status.ready_replicas)))

    def pods(self, label=None):

        return self._toMap(label, self.rawPods, lambda i: Pod(i.status.pod_ip, i.status.phase))

    def rawServices(self, label=None):

        return self._getItems(label, self._k8s.list_namespaced_service, self._k8s.list_service_for_all_namespaces)

    def rawDeployments(self, label=None):

        return self._getItems(label, self._k8sApps.list_namespaced_deployment,
                              self._k8sApps.list_deployment_for_all_namespaces)

    def rawPods(self, label=None):

        return self._getItems(label, self._k8s.list_namespaced_pod, self._k8s.list_pod_for_all_namespaces)

    def rawEndpoints(self, label=None):

        return self._getItems(label, self._k8s.list_namespaced_endpoints, self._k8s.list_endpoints_for_all_namespaces)

    def _toMap(self, label, rawFunc, func):

        items = rawFunc(label)

        # single label requested -> return array
        #
        if label:
            return [func(i) for i in items]

        # otherwise -> return dict[label]
        #
        result = defaultdict(list)
        for i in items:
            result[None if not i.metadata.labels else i.metadata.labels.get(self._labelName)].append(func(i))
        return result

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

        if self._ip == IPAddr("127.0.0.1"):
            #
            # REVIEW Different behavior on localhost to bypass bug:
            # - https://github.com/krestomatio/container_builder/issues/54
            # - https://github.com/kubernetes-client/python/issues/1333
            #
            config.load_kube_config()
            return client.ApiClient()

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

        if self._labelName is None:
            return items
        return filter(lambda i: i.metadata and i.metadata.labels and i.metadata.labels.get(self._labelName), items)

    def _filterNamespace(self, items):

        if self._namespace is None:
            return items
        return filter(lambda item: self._namespace == item.metadata.namespace, items)

    def _getItems(self, label, funcNs, funcAll):

        try:
            if self._namespace is None:
                ret = funcAll(label_selector=self._labelSelector(label))
            else:
                ret = funcNs(self._namespace, label_selector=self._labelSelector(label))

            return self._filterNamespace(self._filterLabelAvailable(ret.items))

        except ApiException as e:
            self._log.warn(e)
            return []
