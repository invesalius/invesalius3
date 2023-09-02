from src.constants import *

##### OS-LEVEL #####
def preprocessing_bids(inputpath, outputpath, subjectname, path2license, nthreads=1):
    os.system("fmriprep-docker {} {} participant --participant-label {} --skip-bids-validation --fs-license-file {} --output-spaces MNI152NLin2009cAsym:res-2  --nthreads {} --stop-on-first-crash".format(
        inputpath, outputpath, subjectname, path2license, nthreads))

def download_example_data(path2bash):
    os.system('bash {}'.format(path2bash))

def download_atlas_parcellations(parcel_dir=None):
    if parcel_dir is None:
        datasets.fetch_atlas_yeo_2011()
    else:
        datasets.fetch_atlas_yeo_2011(parcel_dir)

def verify_loading():
    assert os.path.exists('./resources/')
