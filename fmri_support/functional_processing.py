from src.utils import *
from src.constants import *
from display_utils import *


##### VOLUMES LOADING #####
class SubjectFmriSupport:
    def __init__(self, subjectfolder, subjectname, ftask, volume_path='./resources/',cluster_smoothness=10):
        
        self.volume_path = volume_path
        self.subjectfolder = subjectfolder
        self.subjectname = subjectname
        self.ftask = ftask
        self.cluster_smoothness = cluster_smoothness

        # Intermediate variables
        self.func = None

        # Results variables
        self.yeo7parcellation = None
        self.yeo17parcellation = None
        self.functional_slice = None
        self.principal_gradient = None
        self.functional_connectivity = None


    def _load_initial_volumes(self):
        # Functional Slice
        funcslice = 'func/{}_{}_{}'.format(self.subjectname, self.ftask, EXTENSION_FUNC)
        self.func = nib.load(self.subjectfolder + '/' + funcslice)
        self.functional_slice = nib.Nifti1Image(self.func.get_fdata()[:,:,:,0], self.func.affine)
        print('######')
        print('Functional Slice Loaded !')

        # Atlases with resampling and mapping
        atlas_yeo_2011 = datasets.fetch_atlas_yeo_2011()
        yeo7 = nib.load(atlas_yeo_2011.thick_7)
        yeo17 = nib.load(atlas_yeo_2011.thick_17)

        self.yeo7parcellation = nimg.resample_to_img(yeo7, self.func, interpolation = 'nearest')
        self.yeo17parcellation = nimg.resample_to_img(yeo17, self.func, interpolation = 'nearest')
        print('######')
        print('Parcelation Atlases Loaded !')

    def _generate_volumes(self):
        T = self.func.shape[-1]
        # 1. Extract all voxels and respective timecourses
        brain_timecourses = manual_flatten(self.func.get_fdata())

        # 2. Select only Gray Matter
        # gm_mask_func = nib.load(self.subjectfolder + '/anat/{}_space-MNI152NLin2009cAsym_res-2_label-GM_probseg.nii.gz'.format(self.subjectname))
        # gm_timecourses = brain_timecourses[(gm_mask_func.get_fdata() > 0.5).flatten(),:]

        # 3. Select Parcellations that we wish to average from
        # we use Schaefer parcellations
        n_schf = 414
        atlas_schaeffer = datasets.fetch_atlas_schaefer_2018(n_rois=400,data_dir=self.volume_path)
        region_labels = connected_label_regions(atlas_schaeffer['maps'])
        resampled_schf = nimg.resample_to_img(region_labels, self.func, interpolation = 'nearest')


        # 4. Region averaging (across parcel groups)
        schf_map = resampled_schf.get_fdata()

        avg_timecourses = np.zeros((n_schf, T))
        for k in range(n_schf):
            avg_timecourses[k,:] = brain_timecourses[(schf_map == k + 1).flatten()].mean(axis=0)

        # 5. Compute FC matrix
        fc_matrix = FC(np.nan_to_num(avg_timecourses.T))
        print('######')
        print('FC matrix computed Loaded !')

        # 6. Compute Functional gradients
        g_map  = GradientMaps(n_components=nb_comp, approach=embedding, kernel=aff_kernel, random_state=rs)
        g_map.fit(fc_matrix)

        G1 = g_map.gradients_[:,0]

        # 7. Project Principal gradients back on volume
        schf_gradients_vol = np.zeros_like(schf_map)
        x,y,z = resampled_schf.shape
        for nx in range(x):
            for ny in range(y):
                for nz in range(z):
                    vidx = int(schf_map[nx,ny,nz])
                    if vidx == 0: continue
                    schf_gradients_vol[nx,ny,nz] = G1[vidx-1]

        curmat = deepcopy(np.abs(schf_gradients_vol))
        curmat[curmat == 0] = np.nan
        # careful it needs to be 'func.affine' here
        schf_grads = nib.Nifti1Image(curmat-curmat[~np.isnan(curmat)].min(), self.func.affine)
        print('######')
        print('Gradients projected !')

        self.functional_connectivity = fc_matrix
        self.principal_gradient = schf_grads

    def compute_allvolumes(self):
        print('Loading Initial Volumes ...')
        self._load_initial_volumes()

        print('Computing FC and Gradients Volumes ...')
        self._generate_volumes()

    def save_volumes(self):
        nib.save(self.yeo7parcellation,self.volume_path+'/'+'yeo7_mnispace-{}.nii.gz'.format(self.subjectname))
        nib.save(self.yeo17parcellation,self.volume_path+'/'+'yeo17_mnispace-{}.nii.gz'.format(self.subjectname))
        nib.save(self.functional_slice,self.volume_path+'/'+'funcslice_mnispace-{}.nii.gz'.format(self.subjectname))
        nib.save(self.principal_gradient,self.volume_path+'/'+'G1_mnispace-{}.nii.gz'.format(self.subjectname))
        np.save(self.volume_path+'/'+'funcconnectivity-{}.npy'.format(self.subjectname), self.functional_connectivity)

    def save_displays(self):
        # Load the warpped volumes (in subject space)
        V1 = nib.load(self.volume_path + '/' + 'yeo7_subjectspace-{}.nii.gz'.format(self.subjectname))
        V2 = nib.load(self.volume_path + '/' + 'yeo17_subjectspace-{}.nii.gz'.format(self.subjectname))
        V3 = nib.load(self.volume_path + '/' + 'funcslice_subjectspace-{}.nii.gz'.format(self.subjectname))
        V4 = nib.load(self.volume_path + '/' + 'G1_subjectspace-{}.nii.gz'.format(self.subjectname))

        # Generate in displays
        D1,_ = volume2display(V1.get_fdata(), 'Yeo-7', cluster_smoothness=10)
        D2,_ = volume2display(V2.get_fdata(), 'Yeo-17', cluster_smoothness=10)
        D3,_ = volume2display(V3.get_fdata(), 'timeframe', cluster_smoothness=10)
        D4,_ = volume2display(V4.get_fdata(), 'gradients', cluster_smoothness=10)


        # Encapsulate in nifti
        nD1 = nib.Nifti1Image(D1, V1.affine)
        nD2 = nib.Nifti1Image(D2, V2.affine)
        nD3 = nib.Nifti1Image(D3, V3.affine)
        nD4 = nib.Nifti1Image(D4, V4.affine)

        nib.save(nD1,self.volume_path+'/'+'yeo7_display-{}.nii.gz'.format(self.subjectname))
        nib.save(nD2,self.volume_path+'/'+'yeo17_display-{}.nii.gz'.format(self.subjectname))
        nib.save(nD3,self.volume_path+'/'+'funcslice_display-{}.nii.gz'.format(self.subjectname))
        nib.save(nD4,self.volume_path+'/'+'G1_display-{}.nii.gz'.format(self.subjectname))


    def warping2subject(self, involume='G1_func.nii.gz', outvolume='G1_func_subspace.nii.gz', 
                        reference='sub-08_T1w.nii.gz',transform_mat='sub-08_transform_MNI_to_T1.h5'):
        
        reference = self.subjectfolder  + '/anat/' + '{}_{}'.format(self.subjectname, EXTENSION_REF)
        transform_mat = self.subjectfolder  + '/anat/' + '{}_{}'.format(self.subjectname, EXTENSION_TRANSFORM)


        involume = self.volume_path+'/'+'yeo7_mnispace-{}.nii.gz'.format(self.subjectname)
        outvolume = self.volume_path+'/'+'yeo7_subjectspace-{}.nii.gz'.format(self.subjectname)
        command = '{} -d 3 --float 1 --verbose 1 -i {} -o {} -r {} -t {} -n NearestNeighbor'.format(EXTENSION_ANTS, involume, outvolume, reference, transform_mat)
        os.system(command)

        involume = self.volume_path+'/'+'yeo17_mnispace-{}.nii.gz'.format(self.subjectname)
        outvolume = self.volume_path+'/'+'yeo17_subjectspace-{}.nii.gz'.format(self.subjectname)
        command = '{} -d 3 --float 1 --verbose 1 -i {} -o {} -r {} -t {} -n NearestNeighbor'.format(EXTENSION_ANTS, involume, outvolume, reference, transform_mat)
        os.system(command)

        involume = self.volume_path+'/'+'funcslice_mnispace-{}.nii.gz'.format(self.subjectname)
        outvolume = self.volume_path+'/'+'funcslice_subjectspace-{}.nii.gz'.format(self.subjectname)
        command = '{} -d 3 --float 1 --verbose 1 -i {} -o {} -r {} -t {} -n NearestNeighbor'.format(EXTENSION_ANTS, involume, outvolume, reference, transform_mat)
        os.system(command)

        involume = self.volume_path+'/'+'G1_mnispace-{}.nii.gz'.format(self.subjectname)
        outvolume = self.volume_path+'/'+'G1_subjectspace-{}.nii.gz'.format(self.subjectname)
        command = '{} -d 3 --float 1 --verbose 1 -i {} -o {} -r {} -t {} -n NearestNeighbor'.format(EXTENSION_ANTS, involume, outvolume, reference, transform_mat)
        os.system(command)