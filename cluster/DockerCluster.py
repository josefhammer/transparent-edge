from __future__ import annotations

import docker

from util.IPAddr import IPAddr
from util.Service import Deployment, ServiceInstance, Service
from util.K8sService import K8sService
from util.SocketAddr import SocketAddr
from cluster.Cluster import Cluster
from concurrent.futures import ThreadPoolExecutor as PoolExecutor

from logging import WARNING, getLogger

from util.Performance import PerfCounter

import tempfile
import os


class DockerCluster(Cluster):
    """
    Interface to a single Docker cluster.
    """

    def __init__(self,
                 apiServer,
                 tokenFileName,
                 namespace="edge",
                 labelName="edge.service",
                 labelPort="edge.port",
                 log=None):

        self._ip = IPAddr(apiServer.split(":")[0])
        self._namespace = namespace
        self._labelName = labelName
        self._labelPort = labelPort
        self._log = log
        self._executor = PoolExecutor()

        if self._log is None:
            self._log = getLogger("Docker." + str(self._ip))

        # disable DEBUG logs
        getLogger("urllib3").setLevel(WARNING)
        getLogger("docker").setLevel(WARNING)

        self._client = docker.from_env()

        # TODO Implement remote access:
        # https://stackoverflow.com/questions/38286564/docker-tls-verify-docker-host-and-docker-cert-path-on-ubuntu
        #
        # client = docker.DockerClient(base_url='tcp://127.0.0.1:1234')

    def connect(self):
        pass

    def deploy(self, serviceDef: K8sService):

        assert (serviceDef and serviceDef.yaml)

        containers = []
        futures = []
        hostPaths = serviceDef.volumes()

        perf = PerfCounter()
        contTodo = serviceDef.containers()

        # do we need to create temp volumes ('emptyDir' in Kubernetes)?
        #
        for name, path in hostPaths.items():
            if not path:
                try:
                    tempDir = tempfile.mkdtemp(prefix='edgeD-')  # create temp folder # REVIEW Should be cleaned up
                    os.chmod(tempDir, 0o777)  # REVIEW not readable in container otherwise
                    hostPaths[name] = tempDir
                    self._log.info(f'Created temp mount folder: {tempDir}')
                except Exception as e:
                    self._log.error(f'Error creating temp folder: {e}')
                    return None

        # if more than one container: launch in separate thread
        for cont in contTodo[1:]:
            futures.append(self._executor.submit(self._deployFunc, serviceDef, cont, hostPaths))

        # launch first container in current thread (there must be at least one container!)
        containers.append(self._deployFunc(serviceDef, contTodo[0], hostPaths))
        if len(contTodo) > 1:
            self._log.info(f"Service <{ str(serviceDef) }>: First container deployed ({ round(perf.ms()) } ms).")

        # wait for and add containers from other threads
        for future in futures:
            containers.append(future.result())

        self._log.info(f"Service <{ str(serviceDef) }> deployed ({ round(perf.ms()) } ms).")

        svc = self._apiResponseToService(containers[0])  # REVIEW port from first container only
        svc.containers = containers
        return svc

    def _scale(self, svc: ServiceInstance, replicas: int):
        #
        # NOTE: If svc is running already, this method won't be called (see Cluster.scale()).

        futures = []

        # if more than one container: launch in separate thread
        for cont in svc.containers[1:]:
            futures.append(self._executor.submit(self._scaleFunc, svc, replicas, cont))

        # launch first container in current thread (there must be at least one container!)
        svc.deployment = self._scaleFunc(svc, replicas, svc.containers[0])
        if len(svc.containers) > 1:
            self._log.info(f"Service <{ str(svc) }>: First container scaled up ({svc.containers[0].image}).")

        # wait for and add containers from other threads
        for future in futures:
            svc.deployment = svc.deployment or future.result()  # in case port is in another container

        if replicas and (not svc.deployment or not svc.deployment.ready_replicas):
            self._log.error("Failed to scale: " + str(svc))

    def _deployFunc(self, serviceDef, cont, hostPaths):

        # generate volume mounts list
        #
        volumes = [hostPaths[name] + ':' + path for name, path in cont.volumes.items()]

        # create command and args list
        contCommand = list(cont.command) if cont.command else []  # _copy_ list
        contCommand.extend(cont.args or [])

        func = self._client.containers.run if serviceDef.replicas else self._client.containers.create
        cont = func(
            cont.image,
            command=contCommand,
            # auto_remove=True,  # we want to keep them after scaling down to zero
            detach=True,
            environment=None,  # dict or list
            labels={
                self._labelName: serviceDef.label,
                self._labelPort: str(serviceDef.port),
            },
            ports={
                port: None  # if specific IP only: (self._ip, None)
                for port in cont.ports
            },  # None -> random host port; TCP by default
            volumes=volumes,
            publish_all_ports=False)

        # NOTE: for debugging only
        # for line in containers[-1].logs(stream=True):  #, follow=False):
        #     self._log.debug(line.strip())

        if serviceDef.replicas:
            # update attrs to get the new auto-assigned ports
            # ports are assigned only on run, not on create!
            cont.reload()
        return cont

    def _scaleFunc(self, svc, replicas, cont):
        if replicas:
            cont.start()
            # update attrs to get the new auto-assigned ports
            # ports are assigned only on run, not on create!
            cont.reload()

            if cont.ports:  # REVIEW Duplicate from _apiResonseToService()
                svc.clusterAddr = SocketAddr(self._ip, self._getLocalPort(cont))  # REVIEW For K8s in K8sService
                return Deployment(1, 1)
            return None
        else:
            cont.stop()
            return None

    def services(self, label: str):

        svcs = self._toMap(label, self.rawServices, lambda i: self._apiResponseToService(i))

        if isinstance(svcs, list):
            svcs = self._combine(svcs)
        else:
            for k, v in svcs.items():
                svcs[k] = self._combine(v)
        return svcs

    def _combine(self, svcs):
        sMap = {}

        # merge services with multiple containers
        for svc in svcs:
            if not svc.service.vAddr in sMap:
                sMap[svc.service.vAddr] = svc
            else:
                sMap[svc.service.vAddr].containers.extend(svc.containers)

        return [v for _, v in sMap.items()]

    def _apiResponseToService(self, i) -> ServiceInstance:

        service = Service(None, label=i.labels.get(self._labelName), port=int(i.labels.get(self._labelPort)))
        svc = ServiceInstance(service, self._ip)
        svc.containers.append(i)  # REVIEW Works only if service consists of a single container
        if i.ports:
            svc.clusterAddr = SocketAddr(self._ip, self._getLocalPort(i))  # REVIEW For K8s in K8sService
            svc.deployment = Deployment(replicas=1, ready_replicas=1)
        else:
            svc.deployment = Deployment()  # deployed, but no instance running
        return svc

    def rawServices(self, label=None):

        return self._getItems(label, self._client.containers.list)

    def _label(self, item):

        return None if not item else item.labels.get(self._labelName)

    def _labelSelector(self, label):

        return {} if not label else {'label': f'{self._labelName}={label}'}

    def _filterLabelAvailable(self, items):

        if self._labelName is None:
            return items
        return filter(lambda i: self._labelName in i.labels and self._labelPort in i.labels, items)

    def _getItems(self, label, func):

        try:
            ret = func(filters=self._labelSelector(label), all=True)  # all: include stopped containers
            return self._filterLabelAvailable(ret)

        except Exception as e:
            self._log.warn(e)
            return []

    def _getLocalPort(self, container):

        # container.ports:
        # {'8080/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '49153'}, {'HostIp': '::', 'HostPort': '49153'}]}
        #
        localPorts = {k: v for k, v in container.ports.items() if v}  # v might be None
        return int(localPorts[next(iter(localPorts))][0]['HostPort'])  # only first port in first mapping
