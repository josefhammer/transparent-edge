from __future__ import annotations

# Disable the warnings triggered by verify_ssl=False
#
import urllib3

urllib3.disable_warnings()  # https://urllib3.readthedocs.io/en/1.26.x/advanced-usage.html#ssl-warnings

from kubernetes import client, config, utils, watch
from kubernetes.client.rest import ApiException

from util.IPAddr import IPAddr
from util.Service import Deployment, Pod, ServiceInstance, Service
from util.K8sService import K8sService
from cluster.Cluster import Cluster

from logging import WARNING, getLogger
from functools import partial


class K8sCluster(Cluster):
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
            self._log = getLogger("K8s." + str(self._ip))

        self._apiClient = self._apiClient(apiServer, tokenFileName)

        self._k8s = client.CoreV1Api(self._apiClient)
        self._k8sApps = client.AppsV1Api(self._apiClient)

    def deployService(self, service: K8sService):

        assert (service and service.yaml)

        self.applyYaml(yml=service.yaml)
        self._log.info("Service <" + str(service) + "> deployed.")
        svcInst = next(iter(self.services(service.label)), None)

        assert (svcInst)
        self.scaleDeployment(svcInst)
        return svcInst

    def scaleDeployment(self, svc: ServiceInstance):

        assert (svc)

        if not svc.deployment or not svc.deployment.replicas:  # we need to scale up
            self._scaleDeployment(svc.service.label, 1)
            self._log.info("Scaling up from zero: " + str(svc))

    def watchDeployment(self, svcInst: ServiceInstance):

        assert (svcInst)

        # REVIEW Monitoring should/could be done in a separate thread
        #
        w = watch.Watch()
        events = partial(w.stream, self._k8sApps.list_namespaced_deployment, self._namespace)

        for event in events(label_selector=self._labelSelector(svcInst.service.label), _request_timeout=60):
            evObj = event['object']

            dpm = self._toDeployment(evObj)
            self._log.debug(f"Deployment: event={event['type']} {dpm}")

            # It does not matter which of the two values (`updated` or `ready`) we choose: Both approaches work for the
            # user. While the waiting time here is significantly shorter with `updated_replicaes`, the total time for
            # the user stays the same.
            #
            # However, if we use Pod routing, then we need to wait for the Pod anyway to get the IP address!
            #
            # if dpm.updated_replicas or dpm.ready_replicas:
            if dpm.ready_replicas:
                svcInst.deployment = dpm
                w.stop()

        return svcInst

    def _scaleDeployment(self, label: str, replicas: int):
        api_response = self._k8sApps.patch_namespaced_deployment_scale(Service.uniqueName(label), self._namespace,
                                                                       {'spec': {
                                                                           'replicas': replicas
                                                                       }})

    def services(self, label: str):

        return self._toMap(label, self.rawServices, lambda i: self._apiResponseToService(i))

    def _apiResponseToService(self, i):

        i.kind = "Service"  # unfortunately, it's returned as None
        return K8sService(label=None, yml=[i.to_dict()]).toService(self._ip)

    def deployments(self, label=None):

        return self._toMap(label, self.rawDeployments, lambda i: self._toDeployment(i))

    def pods(self, label=None):

        return self._toMap(label, self.rawPods, lambda i: Pod(i.status.pod_ip, i.status.phase))

    def rawServices(self, label=None):

        return self._getItems(label, self._k8s.list_namespaced_service, self._k8s.list_service_for_all_namespaces)

    def rawDeployments(self, label=None):

        return self._getItems(label, self._k8sApps.list_namespaced_deployment,
                              self._k8sApps.list_deployment_for_all_namespaces)

    def rawPods(self, label=None):
        #
        # Filter out all pods marked for deletion.
        #
        # Unfortunately, filtering pods by label is not perfectly reliable. Should use pod-template-hash instead:
        # (https://stackoverflow.com/questions/52957227/kubectl-command-to-list-pods-of-a-deployment-in-kubernetes)
        #
        # NOTE: Actually, the info from the link above did not solve my issue. The 'pod-template-hash' was the same
        # for all pods. In the end, the solution was to filter out pods with metadata.deletion_timestamp != None.
        #
        # While the 'pod-template-hash' shows a connection to a specific deployment, if the same deployment is
        # deleted and created again immediately, the only solution is to filter by deletion_timestamp.
        #
        return filter(lambda p: p.metadata.deletion_timestamp is None,
                      self._getItems(label, self._k8s.list_namespaced_pod, self._k8s.list_pod_for_all_namespaces))

    def rawEndpoints(self, label=None):

        return self._getItems(label, self._k8s.list_namespaced_endpoints, self._k8s.list_endpoints_for_all_namespaces)

    def _label(self, item):

        return None if not item.metadata.labels else item.metadata.labels.get(self._labelName)

    def applyYaml(self, filename=None, yml=None):
        """
        Pass either filename or file content (`yaml.safe_load_all(filename)`).
        
        See <https://github.com/kubernetes-client/python/blob/0553bba32dd5f2029a086131c893f0b295ac4297/kubernetes/utils/create_from_yaml.py#L97>
        """
        try:
            utils.create_from_yaml(self._apiClient, yaml_file=filename, yaml_objects=yml, namespace=self._namespace)
        except Exception as e:
            self._log.warn(e)

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
            ret = self._getFunc(label, funcNs, funcAll)()

            return self._filterNamespace(self._filterLabelAvailable(ret.items))

        except ApiException as e:
            self._log.warn(e)
            return []

    def _getFunc(self, label, funcNs, funcAll):

        if self._namespace is None:
            return partial(funcAll, label_selector=self._labelSelector(label))
        else:
            return partial(funcNs, self._namespace, label_selector=self._labelSelector(label))

    def _toDeployment(self, response):

        return Deployment(replicas=response.spec.replicas or 0, ready_replicas=response.status.ready_replicas or 0)
