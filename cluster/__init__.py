from cluster.Cluster import Cluster


def initCluster(clusterType: str, apiServer: str, cfgFilename: str) -> Cluster:
    """
    Factory method to allow different kinds of clusters.
    """

    if clusterType == 'k8s':
        from cluster.K8sCluster import K8sCluster
        cluster = K8sCluster
    elif clusterType == 'docker':
        from cluster.DockerCluster import DockerCluster
        cluster = DockerCluster
    else:
        return None

    return cluster(apiServer, cfgFilename)
