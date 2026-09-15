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

import glob
import logging
import os
import re
import shutil
import sys
import tempfile

import numpy as np
import wx

import invesalius.constants as const
import invesalius.data.transformations as tr
import invesalius.session as ses
import invesalius.utils as utils
from invesalius.data import imagedata_utils, simnibs_efield
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher

log = logging.getLogger(__name__)

_KEY_M2M_DIR = "simnibs_m2m_dir"
_KEY_SUBJECTS_DIR = "simnibs_subjects_dir"
_KEY_OUTPUT_DIR = "simnibs_output_dir"
_KEY_COIL_FILE = "simnibs_coil_file"
_KEY_T1_FILE = "simnibs_t1_file"
_KEY_T2_FILE = "simnibs_t2_file"
_KEY_EFIELD_FILE = "simnibs_efield_file"
_KEY_POSE_FILE = "simnibs_pose_file"

TOPIC_LOAD_RESULT = "Load SimNIBS efield into viewer"
TOPIC_SET_SURFACES = "Set SimNIBS efield surfaces"
TOPIC_EFIELD_PAINTED = "SimNIBS efield painted"
TOPIC_SURFACE_ADDED = "Update surface info in GUI"
TOPIC_SHOW_SURFACES = "Show multiple surfaces"
TOPIC_REMOVE_EFIELD = "Remove SimNIBS efield from viewer"
TOPIC_SET_OPACITY = "Set SimNIBS efield opacity"
TOPIC_SET_COLORMAP = "Set SimNIBS efield colormap"
TOPIC_SET_THRESHOLD = "Set SimNIBS efield threshold"
TOPIC_HIGHLIGHT_ABOVE_THRESHOLD = "Show area above threshold"
TOPIC_EFIELD_LOADED = "SimNIBS efield loaded"
TOPIC_PROGRESS = "SimNIBS progress"
TOPIC_ERROR = "SimNIBS error"
TOPIC_CHARM_DONE = "Charm done"
TOPIC_COIL_POSE = "From Neuronavigation: Send coil pose"
TOPIC_SET_TARGET = "Set target"
TOPIC_UNSET_TARGET = "Unset target"
# The colour series the real-time E-field uses.
_VTK_COLORMAP = "BluePurple (E-field)"

# Columns = SimNIBS coil axes in InVesalius ones: y is +x (away from handle), z is -z (into head).
_AXES_INV_TO_SIMNIBS = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])


def _matsimnibs_from_coord(coord):
    """Turn an InVesalius coil pose [x, y, z, alpha, beta, gamma] into a matsimnibs matrix."""
    position, orientation = imagedata_utils.convert_invesalius_to_world(
        position=coord[:3],
        orientation=coord[3:],
    )
    if position[0] is None:
        return None

    mat = tr.compose_matrix(angles=np.radians(orientation), translate=position)
    mat[:3, :3] = mat[:3, :3] @ _AXES_INV_TO_SIMNIBS
    return mat


def _coil_markers() -> dict:
    """The coil poses of the marker list, as {display name: marker}."""
    from invesalius.data.markers.marker import MarkerType
    from invesalius.navigation.markers import MarkersControl

    poses = (MarkerType.COIL_TARGET, MarkerType.COIL_POSE)
    return {
        "{}: {}".format(marker.marker_id, marker.label or _("(unnamed)")): marker
        for marker in MarkersControl().list
        if marker.marker_type in poses and None not in marker.orientation
    }


def _find_charm() -> str | None:
    path = shutil.which("charm")
    if path:
        return path
    for root in [
        os.path.expanduser("~/SimNIBS-4.6"),
        os.path.expanduser("~/SimNIBS-4.5"),
        os.path.expanduser("~/SimNIBS-4"),
        os.path.expanduser("~/SimNIBS-3.2"),
        os.path.expanduser("~/.local"),
        "/usr/local",
        "/opt/simnibs",
    ]:
        candidate = os.path.join(root, "bin", "charm")
        if os.path.isfile(candidate):
            return candidate
    return None


def _simnibs_site_packages() -> str | None:
    charm_exe = _find_charm()
    if not charm_exe:
        return None

    simnibs_root = os.path.dirname(os.path.dirname(charm_exe))
    if sys.platform == "win32":
        candidates = glob.glob(os.path.join(simnibs_root, "simnibs_env", "Lib", "site-packages"))
    else:
        candidates = glob.glob(
            os.path.join(simnibs_root, "simnibs_env", "lib", "python*", "site-packages")
        )

    return candidates[0] if candidates else None


def _read_lut() -> dict:
    """Parse final_tissues_FreeSurferColorLUT.txt bundled with SimNIBS.
    Returns {label: (name, (r, g, b))}. Returns {} if SimNIBS is not installed locally.
    """
    sp = _simnibs_site_packages()
    if not sp:
        return {}
    lut_path = os.path.join(sp, "simnibs", "resources", "final_tissues_FreeSurferColorLUT.txt")
    if not os.path.isfile(lut_path):
        return {}
    result: dict = {}
    with open(lut_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            try:
                label = int(parts[0])
                name = parts[1]
                r, g, b = int(parts[2]), int(parts[3]), int(parts[4])
                result[label] = (name, (r, g, b))
            except ValueError:
                continue
    return result


def _label_info(present_labels: list) -> dict:
    """Return {label: (name, (r, g, b))} for each label.
    Names come from the SimNIBS LUT when available; unknown labels get tissue_N.
    """
    lut = _read_lut()
    result: dict = {}
    for label in present_labels:
        if label in lut:
            result[label] = lut[label]
        else:
            result[label] = (f"tissue_{label}", (200, 200, 200))
    return result


class _CheckListPopup(wx.ComboPopup):
    """The ticked list shown when the dropdown opens."""

    def __init__(self, on_check, on_refresh):
        wx.ComboPopup.__init__(self)
        self._on_check = on_check
        self._on_refresh = on_refresh
        self.listbox = None

    def Create(self, parent):
        self.listbox = wx.CheckListBox(parent, choices=[])
        self.listbox.Bind(wx.EVT_CHECKLISTBOX, self._OnCheck)
        return True

    def GetControl(self):
        return self.listbox

    def GetStringValue(self):
        return ", ".join(self.GetCheckedStrings())

    def GetAdjustedSize(self, min_width, pref_height, max_height):
        # wx measures the popup before showing it
        self._on_refresh()
        rows = max(self.listbox.GetCount() if self.listbox else 0, 1)
        return wx.Size(min_width, min(max_height, 8 + rows * 22))

    def _OnCheck(self, evt):
        evt.Skip()
        self._on_check()

    def SetItems(self, names):
        if self.listbox is not None:
            self.listbox.Set(list(names))

    def GetCheckedStrings(self):
        return list(self.listbox.GetCheckedStrings()) if self.listbox else []

    def SetCheckedStrings(self, names):
        if self.listbox is None:
            return
        known = set(self.listbox.GetStrings())
        self.listbox.SetCheckedStrings([name for name in names if name in known])


class CheckCombo(wx.ComboCtrl):
    """A dropdown where more than one entry can be ticked."""

    def __init__(self, parent, on_change, on_refresh, empty_label):
        wx.ComboCtrl.__init__(self, parent, style=wx.CB_READONLY)
        self._on_change = on_change
        self._empty_label = empty_label
        self._popup = _CheckListPopup(self._OnCheck, on_refresh)
        self.SetPopupControl(self._popup)
        self._ShowChecked()

    def _OnCheck(self):
        self._ShowChecked()
        self._on_change()

    def _ShowChecked(self):
        checked = self.GetChecked()
        self.SetValue(", ".join(checked) if checked else self._empty_label)

    def SetItems(self, names):
        """List `names`, keeping whichever of them were already ticked."""
        checked = [name for name in self.GetChecked() if name in names]
        self._popup.SetItems(names)
        self._popup.SetCheckedStrings(checked)
        self._ShowChecked()

    def GetChecked(self):
        return self._popup.GetCheckedStrings()

    def SetChecked(self, names):
        self._popup.SetCheckedStrings(names)
        self._ShowChecked()


_SIM_OUT_PREFIX = "simnibs_simulation"
_MAX_TARGET_NAME = 40


def _subject_id_from_m2m(m2m_path: str) -> str:
    """Return <subjectID> from a .../m2m_<subjectID> folder, or "" if not an m2m folder."""
    name = os.path.basename(os.path.normpath(m2m_path))
    return name[4:] if name.lower().startswith("m2m_") else ""


def _sanitize_for_folder(name: str, limit: int = _MAX_TARGET_NAME) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
    return cleaned[:limit].rstrip("._-")


def _coil_model_name(coil_path: str) -> str:
    return os.path.splitext(os.path.basename(coil_path))[0]


def _derive_sim_output_dir(m2m_path: str, target_name: str = "", coil_name: str = "") -> str:
    """Default output folder for a given m2m folder, coil target and coil model."""
    if not m2m_path:
        return ""
    parent = os.path.dirname(os.path.normpath(m2m_path))
    parts = [_SIM_OUT_PREFIX]
    subject = _subject_id_from_m2m(m2m_path)
    if subject:
        parts.append(subject)
    parts += [part for part in map(_sanitize_for_folder, (target_name, coil_name)) if part]
    return os.path.join(parent, "_".join(parts))


class TaskPanel(wx.ScrolledWindow):
    def __init__(self, parent):
        wx.ScrolledWindow.__init__(self, parent, style=wx.TAB_TRAVERSAL)

        self.SetSize(wx.Size(400, 300))
        self.SetScrollRate(5, 5)

        inner_panel = InnerTaskPanel(self)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(inner_panel, 1, wx.EXPAND | wx.GROW | wx.ALL, 0)
        self.SetSizer(sizer)
        self.Layout()
        self.Update()
        self.SetAutoLayout(1)


class InnerTaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        self.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR))

        self.session = ses.Session()
        self._m2m_path = None
        self._matsimnibs = None
        self._running = None
        # Coil poses of the marker list, as {display name: marker}.
        self._pose_markers: dict = {}
        # Runs still to be sent, one per ticked coil pose.
        self._queue: list[dict] = []
        self._run_number = 0
        # False once the user picks a simulation output folder by hand.
        self._sim_output_is_auto = True
        # Name of the active coil target, used to name the simulation folder.
        self._target_name = ""
        self._mask_index_by_name: dict[str, int] = {}
        self._efield_loaded = False
        # Names of the surfaces the E-field is painted on right now.
        self._efield_targets: list[str] = []
        # Set while waiting for surfaces to finish generating, to paint on one of them.
        self._retarget_on_new_surface = False
        self._painted_distance = simnibs_efield.EFIELD_SAMPLING_MAX_DISTANCE
        self._pulse_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._OnPulse, self._pulse_timer)

        self._subscribe()
        self._build_ui()
        self._restore_paths()

    def _subscribe(self):
        Publisher.subscribe(self._on_efield_loaded, TOPIC_EFIELD_LOADED)
        Publisher.subscribe(self._on_progress, TOPIC_PROGRESS)
        Publisher.subscribe(self._on_error, TOPIC_ERROR)
        Publisher.subscribe(self._on_charm_done, TOPIC_CHARM_DONE)
        Publisher.subscribe(self._on_coil_pose, TOPIC_COIL_POSE)
        Publisher.subscribe(self._on_set_target, TOPIC_SET_TARGET)
        Publisher.subscribe(self._on_unset_target, TOPIC_UNSET_TARGET)
        Publisher.subscribe(self._on_efield_painted, TOPIC_EFIELD_PAINTED)
        Publisher.subscribe(self._on_surface_added, TOPIC_SURFACE_ADDED)

    def _build_ui(self):
        # HEAD MODEL
        box_hm = wx.StaticBox(self, -1, _("Head Model (charm)"))
        sz_hm = wx.StaticBoxSizer(box_hm, wx.VERTICAL)

        self.txt_subject = wx.TextCtrl(self, -1, "")
        self.txt_t1 = wx.TextCtrl(self, -1, "")
        self.txt_t2 = wx.TextCtrl(self, -1, "")
        self.txt_hm_out = wx.TextCtrl(self, -1, "", style=wx.TE_READONLY)

        btn_t1 = wx.Button(self, -1, _("…"), size=wx.Size(28, -1))
        btn_t2 = wx.Button(self, -1, _("…"), size=wx.Size(28, -1))
        btn_hm_out = wx.Button(self, -1, _("…"), size=wx.Size(28, -1))

        btn_t1.Bind(wx.EVT_BUTTON, self.OnBrowseT1)
        btn_t2.Bind(wx.EVT_BUTTON, self.OnBrowseT2)
        btn_hm_out.Bind(wx.EVT_BUTTON, self.OnBrowseHMOutput)

        g1 = wx.FlexGridSizer(4, 3, 2, 2)
        g1.AddGrowableCol(1)
        g1.Add(wx.StaticText(self, -1, _("Subject ID:")), 0, wx.ALIGN_CENTER_VERTICAL)
        g1.Add(self.txt_subject, 1, wx.EXPAND)
        g1.AddSpacer(0)
        g1.Add(wx.StaticText(self, -1, _("T1-weighted:")), 0, wx.ALIGN_CENTER_VERTICAL)
        g1.Add(self.txt_t1, 1, wx.EXPAND)
        g1.Add(btn_t1, 0)
        g1.Add(wx.StaticText(self, -1, _("T2-weighted:")), 0, wx.ALIGN_CENTER_VERTICAL)
        g1.Add(self.txt_t2, 1, wx.EXPAND)
        g1.Add(btn_t2, 0)
        g1.Add(wx.StaticText(self, -1, _("Output dir:")), 0, wx.ALIGN_CENTER_VERTICAL)
        g1.Add(self.txt_hm_out, 1, wx.EXPAND)
        g1.Add(btn_hm_out, 0)
        sz_hm.Add(g1, 0, wx.EXPAND | wx.ALL, 2)

        self.chk_forcerun = wx.CheckBox(self, -1, _("Force re-run (--forcerun)"))
        self.chk_forcerun.SetToolTip(
            _(
                "Overwrite an existing m2m_<subjectID> folder.\n"
                "Required if you want to re-run charm for the same subject."
            )
        )
        sz_hm.Add(self.chk_forcerun, 0, wx.LEFT | wx.BOTTOM, 2)

        self.chk_force_qform = wx.CheckBox(self, -1, _("Force qform (--forceqform)"))
        self.chk_force_qform.SetValue(True)
        self.chk_force_qform.SetToolTip(
            _(
                "Replace sform with qform in the T1 NIfTI header.\n"
                "This is what charm itself recommends when it reports a\n"
                "qform/sform mismatch (the common case).\n\n"
                "Important: this overwrites the original sform. Neuronavigation\n"
                "software must then be set up with the SimNIBS-processed T1.nii.gz\n"
                "from the m2m_<subjectID> folder, not the original input MRI —\n"
                "otherwise coil pose import/export will be misaligned."
            )
        )
        self.chk_force_qform.Bind(wx.EVT_CHECKBOX, self.OnForceQform)
        sz_hm.Add(self.chk_force_qform, 0, wx.LEFT | wx.BOTTOM, 2)

        self.chk_force_sform = wx.CheckBox(self, -1, _("Force sform (--forcesform)"))
        self.chk_force_sform.SetToolTip(
            _(
                "Replace qform with sform in the T1 NIfTI header (strips shears).\n"
                "Only needed if the qform code is unknown/invalid — charm\n"
                "recommends Force qform for the common mismatch case instead."
            )
        )
        self.chk_force_sform.Bind(wx.EVT_CHECKBOX, self.OnForceSform)
        sz_hm.Add(self.chk_force_sform, 0, wx.LEFT | wx.BOTTOM, 2)

        row_hm = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_run_charm = wx.Button(self, -1, _("Run head model"), size=wx.Size(110, -1))
        self.btn_cancel_charm = wx.Button(self, -1, _("Cancel"), size=wx.Size(60, -1))
        self.btn_cancel_charm.Enable(False)
        self.btn_run_charm.Bind(wx.EVT_BUTTON, self.OnRunCharm)
        self.btn_cancel_charm.Bind(wx.EVT_BUTTON, self.OnCancelCharm)
        row_hm.Add(self.btn_run_charm, 1, wx.RIGHT, 2)
        row_hm.Add(self.btn_cancel_charm, 0)
        sz_hm.Add(row_hm, 0, wx.EXPAND | wx.ALL, 2)

        self.gauge_charm = wx.Gauge(self, -1, 100)
        self.lbl_charm = wx.StaticText(self, -1, _("When ready: "))
        sz_hm.Add(self.gauge_charm, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 2)
        sz_hm.Add(self.lbl_charm, 0, wx.LEFT | wx.BOTTOM, 2)

        self.btn_load_tissues = wx.Button(self, -1, _("Load tissue surfaces"))
        self.btn_load_tissues.SetToolTip(
            _(
                "Select a tissue-label NIfTI from the m2m folder,\n"
                "create one InVesalius mask per label and generate VTK surfaces."
            )
        )
        self.btn_load_tissues.Bind(wx.EVT_BUTTON, self.OnLoadTissueSurfaces)
        sz_hm.Add(self.btn_load_tissues, 0, wx.ALL, 2)

        # TMS SIMULATION
        box_sim = wx.StaticBox(self, -1, _("TMS Simulation"))
        sz_sim = wx.StaticBoxSizer(box_sim, wx.VERTICAL)

        self.txt_m2m = wx.TextCtrl(self, -1, "", style=wx.TE_READONLY)
        self.txt_sim_out = wx.TextCtrl(self, -1, "", style=wx.TE_READONLY)
        self.txt_sim_out.SetToolTip(
            _(
                "Filled in automatically next to the m2m folder, as\n"
                "simnibs_simulation_<subjectID>_<coil target>.\n"
                "The target name comes from the navigation target marker, or\n"
                "from the loaded coil pose file when not navigating.\n"
                "Browse to choose a different folder; a folder chosen by hand\n"
                "is kept as is. Created by SimNIBS when the simulation runs."
            )
        )
        self.cmb_coil = wx.ComboBox(self, -1, "", size=wx.Size(120, -1), style=wx.CB_READONLY)
        self._coil_paths: dict[str, str] = {}
        self._populate_coil_models()
        self.txt_didt = wx.TextCtrl(self, -1, "1000000.0")

        btn_m2m = wx.Button(self, -1, _("…"), size=wx.Size(28, -1))
        btn_sim_out = wx.Button(self, -1, _("…"), size=wx.Size(28, -1))
        btn_coil = wx.Button(self, -1, _("Add coil"))

        btn_m2m.Bind(wx.EVT_BUTTON, self.OnBrowseM2M)
        btn_sim_out.Bind(wx.EVT_BUTTON, self.OnBrowseSimOutput)
        btn_coil.Bind(wx.EVT_BUTTON, self.OnAddCoil)
        self.cmb_coil.Bind(wx.EVT_COMBOBOX, self.OnCoilSelected)

        g2 = wx.FlexGridSizer(4, 3, 2, 2)
        g2.AddGrowableCol(1)
        g2.Add(wx.StaticText(self, -1, _("m2m path:")), 0, wx.ALIGN_CENTER_VERTICAL)
        g2.Add(self.txt_m2m, 1, wx.EXPAND)
        g2.Add(btn_m2m, 0)
        g2.Add(wx.StaticText(self, -1, _("Output dir:")), 0, wx.ALIGN_CENTER_VERTICAL)
        g2.Add(self.txt_sim_out, 1, wx.EXPAND)
        g2.Add(btn_sim_out, 0)
        g2.Add(wx.StaticText(self, -1, _("Coil model:")), 0, wx.ALIGN_CENTER_VERTICAL)
        g2.Add(self.cmb_coil, 1, wx.EXPAND)
        g2.Add(btn_coil, 0)
        g2.Add(wx.StaticText(self, -1, _("dI/dt (A/s):")), 0, wx.ALIGN_CENTER_VERTICAL)
        g2.Add(self.txt_didt, 1, wx.EXPAND)
        g2.AddSpacer(0)
        sz_sim.Add(g2, 0, wx.EXPAND | wx.ALL, 2)

        self.chk_overwrite = wx.CheckBox(self, -1, _("Overwrite previous results"))
        self.chk_overwrite.SetValue(True)
        self.chk_overwrite.SetToolTip(
            _(
                "The output folder is named after the coil target and the coil\n"
                "model, so changing either already gives a folder of its own.\n"
                "This only decides what an exact repeat does.\n"
                "On: the folder is emptied first, keeping the latest result only.\n"
                "Off: the repeat runs beside it, in a folder stamped with the\n"
                "time SimNIBS started it — the same stamp it puts on the .mat\n"
                "and .log inside."
            )
        )
        sz_sim.Add(self.chk_overwrite, 0, wx.ALL, 2)

        row_poses = wx.BoxSizer(wx.HORIZONTAL)
        row_poses.Add(
            wx.StaticText(self, -1, _("Coil poses:")), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4
        )
        self.combo_poses = CheckCombo(
            self,
            on_change=self.OnPoseSelect,
            on_refresh=self._refresh_pose_dropdown,
            empty_label=_("(none — pose below)"),
        )
        self.combo_poses.SetToolTip(
            _(
                "The coil targets and coil poses of the marker list, which is filled\n"
                "by loading a marker file — navigation does not have to run.\n"
                "Tick one to simulate it; tick several to run one simulation per pose,\n"
                "each written to its own folder named after the marker.\n"
                "With none ticked the pose below is used, from navigation or a file."
            )
        )
        row_poses.Add(self.combo_poses, 1)
        sz_sim.Add(row_poses, 0, wx.EXPAND | wx.ALL, 2)

        # matsimnibs display
        sz_sim.Add(wx.StaticText(self, -1, _("Coil pose (matsimnibs):")), 0, wx.LEFT | wx.TOP, 2)
        self.txt_mat = wx.TextCtrl(
            self,
            -1,
            "",
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
            size=wx.Size(-1, 72),
        )
        self._show_pose_source()
        sz_sim.Add(self.txt_mat, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 2)

        row_pose = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_lock = wx.Button(self, -1, _("Lock current coil pose"), size=wx.Size(160, -1))
        self.btn_lock.Bind(wx.EVT_BUTTON, self.OnLockPose)
        row_pose.Add(self.btn_lock, 0, wx.RIGHT, 2)

        self.btn_load_pose = wx.Button(self, -1, _("Load coil pose"), size=wx.Size(130, -1))
        self.btn_load_pose.SetToolTip(
            _(
                "Load a 4x4 coil pose (matsimnibs) matrix from a text file,\n"
                "as an alternative to receiving one from neuronavigation.\n"
            )
        )
        self.btn_load_pose.Bind(wx.EVT_BUTTON, self.OnLoadCoilPose)
        row_pose.Add(self.btn_load_pose, 0)
        sz_sim.Add(row_pose, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 2)

        row_sim = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_run_sim = wx.Button(self, -1, _("Run simulation"), size=wx.Size(110, -1))
        self.btn_cancel_sim = wx.Button(self, -1, _("Cancel"), size=wx.Size(60, -1))
        self.btn_run_sim.Enable(False)
        self.btn_cancel_sim.Enable(False)
        self.btn_run_sim.Bind(wx.EVT_BUTTON, self.OnRunSimulation)
        self.btn_cancel_sim.Bind(wx.EVT_BUTTON, self.OnCancelSimulation)
        row_sim.Add(self.btn_run_sim, 1, wx.RIGHT, 2)
        row_sim.Add(self.btn_cancel_sim, 0)
        sz_sim.Add(row_sim, 0, wx.EXPAND | wx.ALL, 2)

        self.gauge_sim = wx.Gauge(self, -1, 100)
        self.lbl_sim = wx.StaticText(self, -1, _("Load head surfaces first."))
        sz_sim.Add(self.gauge_sim, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 2)
        sz_sim.Add(self.lbl_sim, 0, wx.LEFT | wx.BOTTOM, 2)

        # E-FIELD VISUALIZATION
        box_ef = wx.StaticBox(self, -1, _("E-field Visualization"))
        sz_ef = wx.StaticBoxSizer(box_ef, wx.VERTICAL)

        row_surf = wx.BoxSizer(wx.HORIZONTAL)
        row_surf.Add(
            wx.StaticText(self, -1, _("Surface:")), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4
        )
        self.combo_surface = CheckCombo(
            self,
            on_change=self.OnSurfaceSelect,
            on_refresh=self._refresh_surface_dropdown,
            empty_label=_("(none — E-field mesh)"),
        )
        self.combo_surface.SetToolTip(
            _(
                "The surfaces the E-field is painted on, in the volume viewer and\n"
                "as a cross section in the axial, coronal and sagittal views.\n"
                "Tick as many as you like; those are the surfaces kept visible.\n"
                "Clearing every tick puts the E-field on a surface of its own.\n"
                "Loading a result with none ticked picks the best surface for you."
            )
        )
        row_surf.Add(self.combo_surface, 1)
        sz_ef.Add(row_surf, 0, wx.EXPAND | wx.ALL, 2)

        row_dist = wx.BoxSizer(wx.HORIZONTAL)
        row_dist.Add(
            wx.StaticText(self, -1, _("Max distance (mm):")),
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            4,
        )
        self.spin_distance = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(70, -1), inc=1.0)
        self.spin_distance.SetRange(0.1, 100.0)
        self.spin_distance.SetValue(simnibs_efield.EFIELD_SAMPLING_MAX_DISTANCE)
        self.spin_distance.SetToolTip(
            _(
                "How far a surface point may be from the E-field mesh and still take\n"
                "its value. The result is a grey-matter sheet, so a surface further\n"
                "out shows the field of the tissue underneath it, not its own —\n"
                "raise this only if that is what you want to see.\n"
                "Points beyond the distance are left in their plain colour."
            )
        )
        self.spin_distance.Bind(wx.EVT_SPINCTRLDOUBLE, self.OnMaxDistance)
        self.spin_distance.Bind(wx.EVT_KILL_FOCUS, self.OnMaxDistance)
        row_dist.Add(self.spin_distance, 0)
        sz_ef.Add(row_dist, 0, wx.ALL, 2)

        self.btn_load_efield = wx.Button(self, -1, _("Load E-field result…"))
        self.btn_load_efield.SetToolTip(
            _(
                "Load an E-field surface (.vtk/.vtp) produced by the SimNIBS\n"
                "server and overlay it, coloured by field magnitude, on the 3D view."
            )
        )
        self.btn_load_efield.Bind(wx.EVT_BUTTON, self.OnLoadEfieldResult)
        sz_ef.Add(self.btn_load_efield, 0, wx.ALL, 2)

        self.gauge_efield = wx.Gauge(self, -1, 100)
        self.lbl_efield = wx.StaticText(self, -1, _("No E-field loaded."))
        sz_ef.Add(self.gauge_efield, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 2)
        sz_ef.Add(self.lbl_efield, 0, wx.LEFT | wx.BOTTOM, 2)

        row_cmap = wx.BoxSizer(wx.HORIZONTAL)
        row_cmap.Add(
            wx.StaticText(self, -1, _("Colormap:")), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4
        )
        cmap_choices = [_VTK_COLORMAP] + list(const.MEP_COLORMAP_DEFINITIONS.keys())
        self.combo_cmap = wx.ComboBox(
            self,
            -1,
            size=wx.Size(150, -1),
            choices=cmap_choices,
            style=wx.CB_DROPDOWN | wx.CB_READONLY,
        )
        self.combo_cmap.SetStringSelection(_VTK_COLORMAP)
        self.combo_cmap.SetToolTip(
            _(
                "Colours used for the field magnitude. The first entry is the same "
                "colour series the real-time E-field uses."
            )
        )
        self.combo_cmap.Bind(wx.EVT_COMBOBOX, self.OnColormap)
        row_cmap.Add(self.combo_cmap, 1)
        sz_ef.Add(row_cmap, 0, wx.EXPAND | wx.ALL, 2)

        row_op = wx.BoxSizer(wx.HORIZONTAL)
        row_op.Add(
            wx.StaticText(self, -1, _("E-field opacity:")),
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            4,
        )
        self.spin_opacity = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(60, -1), inc=0.05)
        self.spin_opacity.SetRange(0.0, 1.0)
        self.spin_opacity.SetValue(1.0)
        self.spin_opacity.Bind(wx.EVT_TEXT, self.OnOpacity)
        self.spin_opacity.Bind(wx.EVT_SPINCTRL, self.OnOpacity)
        row_op.Add(self.spin_opacity, 0)
        sz_ef.Add(row_op, 0, wx.ALL, 2)

        row_th = wx.BoxSizer(wx.HORIZONTAL)
        row_th.Add(
            wx.StaticText(self, -1, _("Threshold %:")), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4
        )
        self.spin_threshold = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(60, -1), inc=1.0)
        self.spin_threshold.SetRange(0.0, 100.0)
        self.spin_threshold.SetValue(90.0)
        self.spin_threshold.SetToolTip(
            _(
                "Share of the maximum field value above which the area is\n"
                "considered stimulated, as a percentage."
            )
        )
        self.spin_threshold.Bind(wx.EVT_TEXT, self.OnThreshold)
        self.spin_threshold.Bind(wx.EVT_SPINCTRL, self.OnThreshold)
        row_th.Add(self.spin_threshold, 0)
        sz_ef.Add(row_th, 0, wx.ALL, 2)

        self.chk_highlight = wx.CheckBox(self, -1, _("Highlight area above threshold"))
        self.chk_highlight.Bind(wx.EVT_CHECKBOX, self.OnHighlightAboveThreshold)
        sz_ef.Add(self.chk_highlight, 0, wx.ALL, 2)

        self.btn_remove = wx.Button(self, -1, _("Remove E-field"), size=wx.Size(140, -1))
        self.btn_remove.Bind(wx.EVT_BUTTON, self.OnRemove)
        sz_ef.Add(self.btn_remove, 0, wx.ALL, 2)

        # outer sizer
        main = wx.BoxSizer(wx.VERTICAL)
        main.Add(sz_hm, 0, wx.EXPAND | wx.ALL, 5)
        main.Add(sz_sim, 0, wx.EXPAND | wx.ALL, 5)
        main.Add(sz_ef, 0, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(main)
        self.Layout()

    def _restore_paths(self):
        m2m = self.session.GetConfig(_KEY_M2M_DIR, "")
        self.txt_m2m.SetValue(m2m)
        self.txt_hm_out.SetValue(self.session.GetConfig(_KEY_SUBJECTS_DIR, ""))
        saved_output = self.session.GetConfig(_KEY_OUTPUT_DIR, "")
        if saved_output:
            self._set_sim_output_dir(saved_output, auto=False)
        else:
            self._autofill_sim_output_dir(m2m)
        saved_coil = self.session.GetConfig(_KEY_COIL_FILE, "")
        if saved_coil:
            self._select_coil_path(saved_coil)
        self.txt_t1.SetValue(self.session.GetConfig(_KEY_T1_FILE, ""))
        self.txt_t2.SetValue(self.session.GetConfig(_KEY_T2_FILE, ""))
        if self.session.GetConfig(_KEY_M2M_DIR, ""):
            self.btn_run_sim.Enable(True)

    def _save_path(self, key, value):
        self.session.SetConfig(key, value)

    def _set_sim_output_dir(self, path: str, auto: bool) -> None:
        """Show `path` as the simulation output folder."""
        self.txt_sim_out.SetValue(path)
        self._sim_output_is_auto = auto
        if path and not auto:
            self._save_path(_KEY_OUTPUT_DIR, path)

    def _autofill_sim_output_dir(self, m2m_path: str | None = None) -> None:
        """Derive the simulation output folder automatically from the m2m path and the coil target."""
        if not self._sim_output_is_auto:
            return
        m2m_path = m2m_path or self.txt_m2m.GetValue().strip()
        if not m2m_path:
            return
        derived = _derive_sim_output_dir(m2m_path, self._target_name, self._coil_name())
        if derived:
            self._set_sim_output_dir(derived, auto=True)

    def _set_target_name(self, name: str) -> None:
        """Name the simulation folder after the coil target `name`."""
        name = _sanitize_for_folder(name or "")
        if name == self._target_name:
            return
        self._target_name = name
        self._autofill_sim_output_dir()

    def _on_set_target(self, marker):
        """A navigation target became active."""
        self._set_target_name(getattr(marker, "label", ""))

    def _on_unset_target(self, marker):
        self._set_target_name("")

    def _browse_file(self, wildcard, session_key, msg=""):
        last = self.session.GetConfig(session_key, "")
        last_dir = os.path.dirname(last) if last else ""
        dialog = wx.FileDialog(
            self,
            message=msg or _("Select file"),
            defaultDir=last_dir,
            defaultFile="",
            wildcard=wildcard,
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_CHANGE_DIR,
        )
        path = None
        try:
            if dialog.ShowModal() == wx.ID_OK:
                path = (
                    dialog.GetPath()
                    if sys.platform == "win32"
                    else dialog.GetPath().encode("utf-8")
                )
        except wx.PyAssertionError:
            if dialog.GetPath():
                path = dialog.GetPath()
        dialog.Destroy()
        if path:
            path = utils.decode(path, const.FS_ENCODE)
            self._save_path(session_key, path)
        return path

    def _browse_dir(self, session_key, msg=""):
        current_dir = os.path.abspath(".")
        last_dir = self.session.GetConfig(session_key, "")
        dialog = wx.DirDialog(
            self,
            message=msg or _("Choose a folder:"),
            defaultPath=last_dir,
            style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST | wx.DD_CHANGE_DIR,
        )
        path = None
        try:
            if dialog.ShowModal() == wx.ID_OK:
                path = (
                    dialog.GetPath()
                    if sys.platform == "win32"
                    else dialog.GetPath().encode("utf-8")
                )
        except wx.PyAssertionError:
            if dialog.GetPath():
                path = dialog.GetPath()
        dialog.Destroy()
        os.chdir(current_dir)
        if path:
            path = utils.decode(path, const.FS_ENCODE)
            self._save_path(session_key, path)
        return path

    def OnBrowseT1(self, _evt):
        path = self._browse_file(
            _("NIfTI (*.nii;*.nii.gz)|*.nii;*.nii.gz|All files (*.*)|*.*"),
            _KEY_T1_FILE,
            _("Select T1-weighted image"),
        )
        if path:
            self.txt_t1.SetValue(path)

    def OnBrowseT2(self, _evt):
        path = self._browse_file(
            _("NIfTI (*.nii;*.nii.gz)|*.nii;*.nii.gz|All files (*.*)|*.*"),
            _KEY_T2_FILE,
            _("Select T2-weighted image"),
        )
        if path:
            self.txt_t2.SetValue(path)

    def OnBrowseHMOutput(self, _evt):
        path = self._browse_dir(_KEY_SUBJECTS_DIR, _("Choose subjects root folder"))
        if path:
            self.txt_hm_out.SetValue(path)

    def OnBrowseM2M(self, _evt):
        path = self._browse_dir(_KEY_M2M_DIR, _("Choose m2m_subjectID folder"))
        if path:
            self.txt_m2m.SetValue(path)
            self._m2m_path = path
            self._save_path(_KEY_M2M_DIR, path)
            self._autofill_sim_output_dir(path)
            self.btn_run_sim.Enable(True)

    def OnBrowseSimOutput(self, _evt):
        path = self._browse_dir(_KEY_OUTPUT_DIR, _("Choose simulation output folder"))
        if path:
            self._set_sim_output_dir(path, auto=False)

    def _populate_coil_models(self):
        sp = _simnibs_site_packages()
        if not sp:
            return
        root = os.path.join(sp, "simnibs", "resources", "coil_models")
        if not os.path.isdir(root):
            return
        found: dict[str, str] = {}
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                if name.lower().endswith((".ccd", ".tcd")):
                    full = os.path.join(dirpath, name)
                    found[os.path.relpath(full, root)] = full
        for display in sorted(found, key=str.lower):
            self._coil_paths[display] = found[display]
            self.cmb_coil.Append(display)

    def _select_coil_path(self, path):
        target = os.path.normcase(os.path.abspath(path))
        for display, full in self._coil_paths.items():
            if os.path.normcase(os.path.abspath(full)) == target:
                self.cmb_coil.SetValue(display)
                return
        display = _("(added) {}").format(os.path.basename(path))
        self._coil_paths[display] = path
        if self.cmb_coil.FindString(display) == wx.NOT_FOUND:
            self.cmb_coil.Append(display)
        self.cmb_coil.SetValue(display)
        self._autofill_sim_output_dir()

    def _selected_coil_path(self):
        return self._coil_paths.get(self.cmb_coil.GetValue(), "")

    def _coil_name(self) -> str:
        """The coil model the output folder is named after."""
        return _coil_model_name(self._selected_coil_path())

    def OnCoilSelected(self, _evt):
        path = self._selected_coil_path()
        if path:
            self._save_path(_KEY_COIL_FILE, path)
        self._autofill_sim_output_dir()

    def OnAddCoil(self, _evt):
        path = self._browse_file(
            _("SimNIBS coil (*.tcd;*.ccd)|*.tcd;*.ccd|All files (*.*)|*.*"),
            _KEY_COIL_FILE,
            _("Add a SimNIBS coil file"),
        )
        if path:
            self._select_coil_path(path)

    def OnForceQform(self, _evt):
        if self.chk_force_qform.GetValue():
            self.chk_force_sform.SetValue(False)

    def OnForceSform(self, _evt):
        if self.chk_force_sform.GetValue():
            self.chk_force_qform.SetValue(False)

    def OnRunCharm(self, _evt):
        subject = self.txt_subject.GetValue().strip()
        t1 = self.txt_t1.GetValue().strip()
        t2 = self.txt_t2.GetValue().strip() or None
        outdir = self.txt_hm_out.GetValue().strip()

        if not subject or not t1 or not outdir:
            wx.MessageBox(
                _("Please fill in Subject ID, T1-weighted image path, and output folder."),
                _("Missing input"),
                wx.ICON_WARNING,
            )
            return

        subject_dir = os.path.join(outdir, f"m2m_{subject}")
        forcerun = self.chk_forcerun.GetValue()
        force_qform = self.chk_force_qform.GetValue()
        force_sform = self.chk_force_sform.GetValue()

        msg = _(
            "charm will create the following folder on the SimNIBS server:\n\n"
            "  {}\n\n"
            "This may take 30–60 minutes and requires several GB of free disk space."
            "{}"
            "{}"
            "\n\nProceed?"
        ).format(
            subject_dir,
            _("\n\nThe existing folder will be overwritten (--forcerun is checked).")
            if forcerun
            else "",
            _(
                "\n\nNote: --forceqform will be used, which overwrites the sform in the "
                "NIfTI header.\nFor neuronavigation, use the SimNIBS-processed T1.nii.gz "
                "from the m2m folder,\nnot the original input MRI."
            )
            if force_qform
            else "",
        )

        if wx.MessageBox(msg, _("Run SimNIBS charm"), wx.YES_NO | wx.ICON_QUESTION) != wx.YES:
            return

        mri_files = [t1] + ([t2] if t2 else [])
        Publisher.sendMessage(
            "SimNIBS: Run charm",
            subject_dir=subject_dir,
            mri_files=mri_files,
            forcerun=forcerun,
            force_qform=force_qform,
            force_sform=force_sform,
        )

        self._running = "charm"
        self.btn_run_charm.Enable(False)
        self.btn_cancel_charm.Enable(True)
        self.gauge_charm.SetValue(0)
        self.lbl_charm.SetLabel(_("Sent to SimNIBS server…"))

    def OnCancelCharm(self, _evt):
        Publisher.sendMessage("SimNIBS: Cancel charm")
        self._running = None
        self.btn_run_charm.Enable(True)
        self.btn_cancel_charm.Enable(False)
        self.lbl_charm.SetLabel(_("Cancel requested."))

    def _on_charm_done(self, m2m_dir):
        self._running = None
        self.btn_run_charm.Enable(True)
        self.btn_cancel_charm.Enable(False)
        self.gauge_charm.SetValue(100)
        self.lbl_charm.SetLabel(_("Head model complete."))
        if m2m_dir:
            self._m2m_path = m2m_dir
            self.txt_m2m.SetValue(m2m_dir)
            self._save_path(_KEY_M2M_DIR, m2m_dir)
            self._autofill_sim_output_dir(m2m_dir)
            self.btn_run_sim.Enable(True)

    def OnLoadTissueSurfaces(self, _evt):
        """
        Browse for a tissue-label NIfTI, then create one
        InVesalius mask per label and generate a VTK surface for each.
        """
        start_dir = self._m2m_path or self.session.GetConfig(_KEY_M2M_DIR, "")
        dlg = wx.FileDialog(
            self,
            message=_("Select tissue-label NIfTI from the m2m folder"),
            defaultDir=start_dir,
            wildcard=_("NIfTI (*.nii;*.nii.gz)|*.nii;*.nii.gz|All files (*.*)|*.*"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        if dlg.ShowModal() == wx.ID_OK:
            filepath = utils.decode(dlg.GetPath(), const.FS_ENCODE)
            self._load_tissue_surfaces(filepath)
        dlg.Destroy()

    def _load_tissue_surfaces(self, labels_nii: str) -> None:
        import nibabel as nib

        import invesalius.project as prj

        try:
            nii = nib.load(labels_nii)
            data = np.asarray(nii.dataobj)
        except Exception as exc:
            wx.MessageBox(
                _("Could not read NIfTI file:\n{}").format(exc),
                _("SimNIBS"),
                wx.ICON_ERROR,
            )
            return

        present = sorted(int(v) for v in np.unique(data) if v > 0)
        if not present:
            wx.MessageBox(
                _("No tissue labels found in the selected file."), _("SimNIBS"), wx.ICON_WARNING
            )
            return

        info = _label_info(present)
        created: list[tuple[int, str]] = []

        for label in present:
            name, _colour = info[label]
            binary = (data == label).astype(np.uint8) * 255
            mask_img = nib.Nifti1Image(binary, nii.affine, nii.header)

            with tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as fh:
                tmp = fh.name
            try:
                nib.save(mask_img, tmp)
                Publisher.sendMessage("Import Nifti mask", filepath=tmp, mask_name=name)
                proj = prj.Project()
                idx = max(proj.mask_dict.keys())
                created.append((idx, name))
            except Exception as exc:
                wx.MessageBox(
                    _("Could not import mask for label {} ({}):\n{}").format(label, name, exc),
                    _("SimNIBS"),
                    wx.ICON_WARNING,
                )
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

        for mask_idx, mask_name in created:
            surface_params = {
                "method": {
                    "algorithm": "ca_smoothing",
                    "options": {
                        "angle": 0.7,
                        "max distance": 3.0,
                        "min weight": 0.5,
                        "steps": 10,
                    },
                },
                "options": {
                    "index": mask_idx,
                    "name": mask_name,
                    "quality": _("Optimal *"),
                    "fill": False,
                    "fill_border_holes": False,
                    "keep_largest": False,
                    "overwrite": False,
                },
            }
            Publisher.sendMessage("Create surface from index", surface_parameters=surface_params)

        self._mask_index_by_name = {name: mask_idx for mask_idx, name in created}
        self._retarget_on_new_surface = self._efield_loaded
        self._refresh_surface_dropdown()

    def _on_coil_pose(self, coord):
        """Store the latest coil pose broadcast by the navigation module."""
        if coord is None or len(coord) < 6:
            return

        mat = _matsimnibs_from_coord(coord)
        if mat is None:
            return

        self._matsimnibs = mat.tolist()

    def _refresh_pose_dropdown(self, _evt=None) -> None:
        """List the coil poses of the marker list, keeping whichever are ticked."""
        self._pose_markers = _coil_markers()
        self.combo_poses.SetItems(list(self._pose_markers))

    def _checked_poses(self) -> list:
        """The ticked markers, as (display name, marker)."""
        return [
            (name, self._pose_markers[name])
            for name in self.combo_poses.GetChecked()
            if name in self._pose_markers
        ]

    def OnPoseSelect(self) -> None:
        """The ticked coil markers are the poses to simulate."""
        poses = self._checked_poses()

        if len(poses) == 1:
            name, marker = poses[0]
            mat = _matsimnibs_from_coord(marker.coordinate)
            if mat is None:
                self._warn_no_affine()
                return
            self._refresh_mat_display(mat)
            self._set_target_name(marker.label or name)
            self.lbl_sim.SetLabel(_("Coil pose from marker {}.").format(name))
        elif poses:
            self.txt_mat.SetValue(
                _("{} coil poses ticked, simulated one run each:\n{}").format(
                    len(poses), ", ".join(name for name, _marker in poses)
                )
            )
            # Each run names its own folder after its marker.
            self._set_target_name("")
            self.lbl_sim.SetLabel(_("{} coil poses to simulate.").format(len(poses)))
        else:
            self._show_pose_source()

    def _show_pose_source(self) -> None:
        """Show the pose a run with no ticked marker would use."""
        if self._matsimnibs is not None:
            self._refresh_mat_display(np.array(self._matsimnibs))
        else:
            self.txt_mat.SetValue(
                _("No pose — tick a coil marker above, or take one from navigation or a file")
            )

    def _warn_no_affine(self) -> None:
        wx.MessageBox(
            _(
                "The project has no affine matrix, so a coil pose cannot be converted to "
                "SimNIBS coordinates.\n\nOpen the SimNIBS-processed T1.nii.gz from the "
                "m2m folder as the project image."
            ),
            _("SimNIBS"),
            wx.ICON_WARNING,
        )

    def OnLockPose(self, _evt):
        if self._matsimnibs is None:
            wx.MessageBox(
                _("No coil pose received yet.\nThe navigation module must send a coil pose first."),
                _("No pose"),
                wx.ICON_WARNING,
            )
            return
        self.combo_poses.SetChecked([])
        self._refresh_mat_display(np.array(self._matsimnibs))

    def _refresh_mat_display(self, mat=None):
        m = mat if mat is not None else np.eye(4)
        lines = [
            f"[ {m[r, 0]:7.3f}  {m[r, 1]:7.3f}  {m[r, 2]:7.3f}  {m[r, 3]:8.2f} ]" for r in range(4)
        ]
        self.txt_mat.SetValue("\n".join(lines))

    def OnLoadCoilPose(self, _evt):
        path = self._browse_file(
            _("Coil pose matrix (*.txt;*.csv;*.mat)|*.txt;*.csv;*.mat|All files (*.*)|*.*"),
            _KEY_POSE_FILE,
            _("Select a 4x4 coil pose (matsimnibs) matrix"),
        )
        if not path:
            return
        try:
            mat = self._read_matsimnibs(path)
        except Exception as exc:  # noqa: BLE001 - report to the user
            wx.MessageBox(
                _("Could not read a 4x4 coil pose matrix from:\n{}\n\n{}").format(path, exc),
                _("Invalid coil pose"),
                wx.ICON_ERROR,
            )
            return
        self._matsimnibs = mat.tolist()
        self.combo_poses.SetChecked([])
        self._refresh_mat_display(mat)
        stem = os.path.splitext(os.path.basename(path))[0]
        self._set_target_name(re.sub(r"^(coil_)?pose_", "", stem, flags=re.IGNORECASE))
        self.lbl_sim.SetLabel(_("Coil pose loaded from file."))

    @staticmethod
    def _read_matsimnibs(path: str):
        """Read a 4x4 matsimnibs matrix from a whitespace- or comma-delimited text file."""
        try:
            arr = np.loadtxt(path)
        except ValueError:
            arr = np.loadtxt(path, delimiter=",")
        arr = np.asarray(arr, dtype=float)
        if arr.size != 16:
            raise ValueError(_("expected 16 numbers forming a 4x4 matrix, got {}").format(arr.size))
        return arr.reshape(4, 4)

    def OnRunSimulation(self, _evt):
        m2m_path = self.txt_m2m.GetValue().strip()
        out_dir = self.txt_sim_out.GetValue().strip()
        coil = self._selected_coil_path().strip()

        try:
            didt = float(self.txt_didt.GetValue())
        except ValueError:
            wx.MessageBox(_("dI/dt must be a number."), _("Input error"), wx.ICON_WARNING)
            return

        if not m2m_path or not out_dir or not coil:
            wx.MessageBox(
                _("Please fill in m2m path, output folder, and coil file."),
                _("Missing input"),
                wx.ICON_WARNING,
            )
            return

        runs = self._plan_runs(out_dir)
        if not runs:
            return

        overwrite = self.chk_overwrite.GetValue()
        self._queue = [
            {
                "name": run["name"],
                "m2m_dir": m2m_path,
                "output_dir": run["output_dir"],
                "coil": coil,
                "didt": didt,
                "overwrite": overwrite,
                "matsimnibs": run["matsimnibs"],
            }
            for run in runs
        ]
        self._run_number = 0
        self._start_next_run()

    def _plan_runs(self, base_out_dir: str) -> list:
        """One entry per coil pose to simulate, each with an output folder of its own."""
        ticked = len(self.combo_poses.GetChecked())
        self._refresh_pose_dropdown()
        poses = self._checked_poses()
        if len(poses) < ticked:
            wx.MessageBox(
                _("{} of the ticked coil poses are no longer in the marker list.").format(
                    ticked - len(poses)
                ),
                _("SimNIBS"),
                wx.ICON_WARNING,
            )
            if not poses:
                return []

        if poses:
            runs = []
            for name, marker in poses:
                mat = _matsimnibs_from_coord(marker.coordinate)
                if mat is None:
                    self._warn_no_affine()
                    return []
                runs.append(
                    {
                        "name": marker.label or name,
                        "marker_id": marker.marker_id,
                        "matsimnibs": mat.tolist(),
                    }
                )
        elif self._matsimnibs is not None:
            runs = [{"name": self._target_name, "marker_id": None, "matsimnibs": self._matsimnibs}]
        else:
            wx.MessageBox(
                _(
                    "No coil pose to simulate.\n\nTick a coil marker, or take a pose from "
                    "navigation or a coil pose file."
                ),
                _("No pose"),
                wx.ICON_WARNING,
            )
            return []

        batch = len(runs) > 1
        assigned: set = set()
        for run in runs:
            path = self._output_dir_for(base_out_dir, run["name"], batch)
            if path in assigned:
                # Two markers whose labels sanitise the same way; their ids do not.
                path = f"{path}_marker{run['marker_id']}"
            assigned.add(path)
            run["output_dir"] = path
        return runs

    def _output_dir_for(self, base: str, target_name: str, batch: bool) -> str:
        """Where one run writes."""
        if self._sim_output_is_auto:
            m2m = self.txt_m2m.GetValue().strip()
            return _derive_sim_output_dir(m2m, target_name, self._coil_name()) or base
        if batch:
            return os.path.join(base, _sanitize_for_folder(target_name) or _SIM_OUT_PREFIX)
        return base

    def _start_next_run(self) -> None:
        """Send the first queued pose to the server."""
        run = self._queue.pop(0)
        self._run_number += 1
        total = self._run_number + len(self._queue)

        Publisher.sendMessage(
            "SimNIBS: Run simulation",
            m2m_dir=run["m2m_dir"],
            output_dir=run["output_dir"],
            coil=run["coil"],
            didt=run["didt"],
            overwrite=run["overwrite"],
            matsimnibs=run["matsimnibs"],
        )

        self._running = "sim"
        self.btn_run_sim.Enable(False)
        self.btn_cancel_sim.Enable(True)
        self.gauge_sim.SetValue(0)
        if total > 1:
            self.lbl_sim.SetLabel(
                _("Pose {}/{} ({}) sent to SimNIBS server…").format(
                    self._run_number, total, run["name"] or _("no name")
                )
            )
        else:
            self.lbl_sim.SetLabel(_("Sent to SimNIBS server…"))

    def OnCancelSimulation(self, _evt):
        Publisher.sendMessage("SimNIBS: Cancel simulation")
        pending = len(self._queue)
        self._queue = []
        self._running = None
        self.btn_run_sim.Enable(True)
        self.btn_cancel_sim.Enable(False)
        self.lbl_sim.SetLabel(
            _("Cancel requested, {} queued pose(s) dropped.").format(pending)
            if pending
            else _("Cancel requested.")
        )

    def _on_efield_loaded(self, result_msh):
        converting = self._running == "convert"
        self._running = None
        self._StopPulse()
        if not converting:
            label = os.path.basename(result_msh) if result_msh else _("Simulation complete.")
            self.lbl_sim.SetLabel(label)
            self.gauge_sim.SetValue(100)
        self.btn_run_sim.Enable(True)
        self.btn_cancel_sim.Enable(False)

        if result_msh and result_msh.lower().endswith((".vtk", ".vtp")):
            self.gauge_efield.SetValue(100)
            self._load_efield_result(result_msh)
        elif result_msh:
            log.warning(
                "SimNIBS returned %s, which is not a surface the viewer can read", result_msh
            )

        if not converting and self._queue:
            self._start_next_run()

    def _OnPulse(self, _evt):
        self.gauge_efield.Pulse()

    def _StartPulse(self):
        self._pulse_timer.Start(120)

    def _StopPulse(self):
        if self._pulse_timer.IsRunning():
            self._pulse_timer.Stop()

    def _on_progress(self, message, percent):
        if self._running == "charm":
            self.gauge_charm.SetValue(int(percent or 0))
            self.lbl_charm.SetLabel(message)
        elif self._running == "convert":
            if not self._pulse_timer.IsRunning():
                self.gauge_efield.SetValue(int(percent or 0))
            self.lbl_efield.SetLabel(message)
        else:
            self.gauge_sim.SetValue(int(percent or 0))
            self.lbl_sim.SetLabel(message)

    def _on_error(self, message):
        converting = self._running == "convert"
        self._running = None
        self._StopPulse()
        pending = len(self._queue)
        self._queue = []
        if pending:
            message = _("{}\n\n{} queued coil pose(s) were not simulated.").format(message, pending)
        if converting:
            self.gauge_efield.SetValue(0)
            self.lbl_efield.SetLabel(_("Conversion failed."))
        else:
            self.gauge_charm.SetValue(0)
            self.gauge_sim.SetValue(0)
            self.lbl_charm.SetLabel(_("Error."))
            self.lbl_sim.SetLabel(f"Error: {message}")
        self.btn_run_charm.Enable(True)
        self.btn_cancel_charm.Enable(False)
        self.btn_run_sim.Enable(True)
        self.btn_cancel_sim.Enable(False)
        wx.MessageBox(message, _("SimNIBS error"), wx.ICON_ERROR | wx.OK)

    def OnSurfaceSelect(self) -> None:
        """Show the surfaces just ticked, and paint the E-field on them once there is one."""
        selected = self.combo_surface.GetChecked()
        self._show_masks_for(selected)

        if not self._efield_loaded:
            if selected:
                Publisher.sendMessage(
                    TOPIC_SHOW_SURFACES,
                    index_list=self._surface_indexes(selected),
                    visibility=True,
                )
            return

        try:
            Publisher.sendMessage(
                TOPIC_SET_SURFACES,
                target_surfaces=self._surface_indexes(selected),
                max_distance=self.spin_distance.GetValue(),
            )
        except Exception as exc:  # noqa: BLE001 - report to the user
            log.exception("SimNIBS E-field could not be painted on the chosen surfaces")
            wx.MessageBox(str(exc), _("SimNIBS"), wx.ICON_WARNING)
            # Nothing on screen changed, so put the dropdown back in step with it.
            self.combo_surface.SetChecked(self._efield_targets)

    def OnMaxDistance(self, evt) -> None:
        evt.Skip()
        distance = self.spin_distance.GetValue()
        if not self._efield_loaded or distance == self._painted_distance:
            return
        self._painted_distance = distance
        self.OnSurfaceSelect()

    def _show_masks_for(self, names) -> None:
        """Show the masks of the ticked tissue surfaces, and hide the rest."""
        for name, mask_index in self._mask_index_by_name.items():
            Publisher.sendMessage("Show mask", index=mask_index, value=name in names)
        if len(names) == 1 and names[0] in self._mask_index_by_name:
            Publisher.sendMessage("Change mask selected", index=self._mask_index_by_name[names[0]])

    def _refresh_surface_dropdown(self, _evt=None) -> None:
        """List every surface in the project, keeping whichever are ticked."""
        import invesalius.project as prj

        self.combo_surface.SetItems([str(s.name) for s in prj.Project().surface_dict.values()])

    def _surface_indexes(self, names) -> list:
        import invesalius.project as prj

        wanted = set(names)
        return [
            index
            for index, surface in prj.Project().surface_dict.items()
            if str(surface.name) in wanted
        ]

    def _on_efield_painted(self, painted, refused) -> None:
        self._efield_loaded = True
        self._efield_targets = [name for _index, name, _coverage in painted]

        self._refresh_surface_dropdown()
        if not self.combo_surface.GetChecked():
            self.combo_surface.SetChecked(self._efield_targets)

        visible = set(self.combo_surface.GetChecked()) | set(self._efield_targets)
        Publisher.sendMessage(
            TOPIC_SHOW_SURFACES, index_list=self._surface_indexes(visible), visibility=True
        )

        summary = ", ".join(f"{name} ({coverage:.0%})" for _index, name, coverage in painted)
        if refused:
            skipped = ", ".join(
                name if closest is None else f"{name} {closest:.0f} mm away"
                for name, closest in refused
            )
            summary += _(" — out of reach: {}").format(skipped)
        self.lbl_efield.SetLabel(_("E-field on {}").format(summary))

    def _on_surface_added(self, surface) -> None:
        """A surface finished generating, which happens well after the import is asked for."""
        self._refresh_surface_dropdown()
        if not self._efield_loaded:
            return

        name = str(surface.name)
        if self._retarget_on_new_surface and simnibs_efield.IsDefaultTarget(name):
            self._retarget_on_new_surface = False
            self.combo_surface.SetChecked([name])
            self.OnSurfaceSelect()
        else:
            Publisher.sendMessage(
                TOPIC_SHOW_SURFACES,
                index_list=self._surface_indexes(self._efield_targets),
                visibility=True,
            )

    def OnColormap(self, _evt):
        Publisher.sendMessage(TOPIC_SET_COLORMAP, colormap=self.combo_cmap.GetValue())

    def OnOpacity(self, _evt):
        Publisher.sendMessage(TOPIC_SET_OPACITY, opacity=self.spin_opacity.GetValue())

    def OnThreshold(self, _evt):
        Publisher.sendMessage(TOPIC_SET_THRESHOLD, threshold=self._threshold())

    def OnHighlightAboveThreshold(self, _evt):
        Publisher.sendMessage(TOPIC_HIGHLIGHT_ABOVE_THRESHOLD, enable=self.chk_highlight.GetValue())
        Publisher.sendMessage(TOPIC_SET_THRESHOLD, threshold=self._threshold())

    def _threshold(self):
        return self.spin_threshold.GetValue() / 100.0

    def OnLoadEfieldResult(self, _evt):
        path = self._browse_file(
            _("E-field result (*.vtk;*.vtp;*.msh)|*.vtk;*.vtp;*.msh|All files (*.*)|*.*"),
            _KEY_EFIELD_FILE,
            _("Select an E-field result (.vtk/.vtp or SimNIBS .msh)"),
        )
        if not path:
            return

        if path.lower().endswith(".msh"):
            self._convert_efield_result(path)
        else:
            self._load_efield_result(path)

    def _convert_efield_result(self, filepath: str) -> None:
        if Publisher.sendMessage_hook is None:
            wx.MessageBox(
                _(
                    "A .msh has to be converted by the SimNIBS server, but InVesalius "
                    "is not connected to one.\n\n"
                    "Start it with --remote-host, or select a .vtk/.vtp surface that "
                    "has already been converted."
                ),
                _("SimNIBS"),
                wx.ICON_WARNING,
            )
            return

        self._running = "convert"
        Publisher.sendMessage("SimNIBS: Convert msh", result_msh=filepath)
        self._StartPulse()
        self.gauge_efield.SetValue(0)
        self.lbl_efield.SetLabel(
            _("Converting {} on the SimNIBS server…").format(os.path.basename(filepath))
        )

    def _load_efield_result(self, filepath: str) -> None:
        self._refresh_surface_dropdown()
        try:
            Publisher.sendMessage(
                TOPIC_LOAD_RESULT,
                filepath=filepath,
                target_surfaces=self._surface_indexes(self.combo_surface.GetChecked()),
                colormap=self.combo_cmap.GetValue(),
                threshold=self._threshold(),
                opacity=self.spin_opacity.GetValue(),
                max_distance=self.spin_distance.GetValue(),
            )
        except Exception as exc:  # noqa: BLE001 - report to the user
            log.exception("SimNIBS E-field surface could not be loaded")
            wx.MessageBox(
                _("Could not load the E-field surface:\n{}\n\n{}").format(filepath, exc),
                _("SimNIBS"),
                wx.ICON_ERROR,
            )

    def OnRemove(self, _evt):
        try:
            Publisher.sendMessage(TOPIC_REMOVE_EFIELD)
        finally:
            self._efield_loaded = False
            self._efield_targets = []
            self._retarget_on_new_surface = False
            self.combo_surface.SetChecked([])
            self.lbl_efield.SetLabel(_("No E-field loaded."))
