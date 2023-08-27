from display_utils import *
from load_resources import *
from functional_processing import *


def main():
    path2save = './resources/'
    subj_id = 'sub-01'

    # 1. Tutorial by default we download Flanker Test
    # download_example_data('tutorial/ds000102-00001.sh')

    # 2. Preprocess the Flanker Test dataset
    # preprocessing_bids('tutorial/', 'tutorial/derivatives', 'sub-01', 'tutorial/derivatives/license.txt', nthreads=1)

    # 3. Download Atlas data
    download_atlas_parcellations()

    # 4. Compute and Generate the volumes to visualize interactively on Invesalius
    fmrisupp = SubjectFmriSupport('/home/chunhei/Desktop/fun/gsoc/processed_data/example_frmiprep/derivatives/{}'.format(subj_id), 
                                  '{}'.format(subj_id), 'task-flanker',path2save, cluster_smoothness=10)
    fmrisupp.compute_allvolumes()

    fmrisupp.save_volumes()

    # 5. Map the volumes (originally in MNI space) to original subject space
    fmrisupp.warping2subject()

    # 6. Clustering the generated volumes to have displayable arrays on Invesalius
    fmrisupp.save_displays()

if __name__ == "__main__":
   main()