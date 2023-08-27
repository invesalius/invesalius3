from src.constants import *


def volume2display(volume, flag, cluster_smoothness=10):
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