from util.K8sCluster import K8sCluster
from util.K8sService import K8sService


class Cluster:
    """
    Factory class for different kinds of clusters.
    """

    @staticmethod
    def init(clusterType: str, apiServer: str, cfgFilename: str):
        """
        Factory method to allow different kinds of clusters.
        """

        if clusterType == "k8s":
            return K8sCluster(apiServer, cfgFilename)
        return None

    @staticmethod
    def initService(label=None, port=None, filename=None, yml: dict = None):
        """
        Factory method to create a service from its definition (file or yaml).
        
        Currently, only K8s Yaml files are supported.
        """
        return K8sService(label, port, filename, yml)
