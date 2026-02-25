# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
# --------------------------------------------------------------------------

import numpy as np

# _ is usually injected by gettext in InVesalius, but we need a fallback for import safety
try:
    _
except NameError:
    def _(s): return s


def check_is_mask(data):
    """
    Validate and normalize NIfTI data for use as a binary label map.

    Converts input to uint8 and enforces binary encoding:
        0 → 0 (background)
        non-zero → 255 (mask)

    Args:
        data: numpy array (raw NIfTI voxel data, any numeric dtype)

    Returns:
        Cleaned uint8 numpy array with values 0 and 255 only.

    Raises:
        ValueError: if data is not 3D, contains NaN, or is not numeric.
    """
    if not np.issubdtype(data.dtype, np.number):
        raise ValueError(_("Mask data must be numeric, got dtype: {}").format(data.dtype))

    if np.issubdtype(data.dtype, np.floating) and np.any(np.isnan(data)):
        raise ValueError(_("Mask data contains NaN values."))

    if data.ndim != 3:
        raise ValueError(_("Mask must be 3D. Got {}D data.").format(data.ndim))

    # Binary label-map encoding: 0=background, 255=mask
    return (data > 0).astype(np.uint8) * 255


def validate_mask_compatibility(mask_shape, slice_shape):
    """
    Validate that the imported mask dimensions match the project volume.

    Args:
        mask_shape: tuple of (x, y, z) — NIfTI data shape
        slice_shape: tuple of (x, y, z) — project volume shape (reversed from internal ZYX)

    Raises:
        ValueError: if shapes do not match exactly.
    """
    if mask_shape != slice_shape:
        raise ValueError(
            _("Dimension mismatch.\n\nProject: {} voxels\nMask:    {} voxels\n\n"
              "Masks must match the volume dimensions exactly.").format(slice_shape, mask_shape)
        )
