from src.constants import *


def volume2display(volume, flag, cluster_smoothness=10):
    """
    Information:
    ------------
    From the computed volumes (e.g functional gradients ...) 
    we generate integer-valued arrays (in the same shape as the input)
    that can be displayed / visualized via clustering the values

    Parameters
    ----------
    volume::[3darray<float>]
        Input volume that we want to visualize after clustering
    flag::[string]
        Either "timeframe" / "gradients" / "Yeo-7" / "Yeo-17"
    cluster_smoothness::[int]
        Number of class used in displaying different colors 
        or gradients of colors
    Returns
    -------
    clust_vol::[3darray<float>]
        Clustered volumes    
    cluster_smoothness::[int]
        Same as input
    """
    if (flag == "timeframe") or (flag == "gradients"):
        tmp = deepcopy(volume)
        # -> Idea is to generate one hue but with different intensity for the whole volume, intensity depending on the BOLD value
        # 0. Clustering of colors and values from tmp
        tmp[np.isnan(tmp)] = -10000 # artificially cluster together the nans

        kmeans = KMeans(init="k-means++", n_clusters=cluster_smoothness, n_init=4, random_state=0)
        res = kmeans.fit_predict(tmp.flatten().reshape(-1,1))
        # convert the clustered regions back to volume shape
        clust_vol = res.reshape(tmp.shape).astype(int)
        return clust_vol, cluster_smoothness

    elif flag == "Yeo-7":
        cluster_smoothness = 7
        tmp = deepcopy(volume)
        clust_vol = tmp.astype(int)
        return clust_vol, cluster_smoothness

    elif flag == "Yeo-17":
        cluster_smoothness = 17
        tmp = deepcopy(volume)
        clust_vol = tmp.astype(int)
        return clust_vol, cluster_smoothness
    
    return 