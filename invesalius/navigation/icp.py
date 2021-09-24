#--------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
#--------------------------------------------------------------------------
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
#--------------------------------------------------------------------------

import wx

import invesalius.data.bases as db
import invesalius.gui.dialogs as dlg
from invesalius.pubsub import pub as Publisher


class ICP():
    def __init__(self):
        self.use_icp = False
        self.m_icp = None
        self.icp_fre = None

    def StartICP(self, navigation, tracker):
        ref_mode_id = navigation.GetReferenceMode()

        if not self.use_icp:
            if dlg.ICPcorregistration(navigation.fre):
                Publisher.sendMessage('Stop navigation')
                use_icp, self.m_icp = self.OnICP(navigation, tracker, navigation.m_change)
                if use_icp:
                    self.icp_fre = db.calculate_fre(tracker.tracker_fiducials_raw, navigation.all_fiducials,
                                                    ref_mode_id, navigation.m_change, self.m_icp)
                    self.SetICP(navigation, use_icp)
                else:
                    print("ICP canceled")
                Publisher.sendMessage('Start navigation')

    def OnICP(self, navigation, tracker, m_change):
        ref_mode_id = navigation.GetReferenceMode()

        dialog = dlg.ICPCorregistrationDialog(nav_prop=(m_change, tracker.tracker_id, tracker.trk_init, ref_mode_id))

        if dialog.ShowModal() == wx.ID_OK:
            m_icp, point_coord, transformed_points, prev_error, final_error = dialog.GetValue()
            # TODO: checkbox in the dialog to transfer the icp points to 3D viewer
            #create markers
            # for i in range(len(point_coord)):
            #     img_coord = point_coord[i][0],-point_coord[i][1],point_coord[i][2], 0, 0, 0
            #     transf_coord = transformed_points[i][0],-transformed_points[i][1],transformed_points[i][2], 0, 0, 0
            #     Publisher.sendMessage('Create marker', coord=img_coord, marker_id=None, colour=(1,0,0))
            #     Publisher.sendMessage('Create marker', coord=transf_coord, marker_id=None, colour=(0,0,1))
            if m_icp is not None:
                dlg.ReportICPerror(prev_error, final_error)
                use_icp = True
            else:
                use_icp = False

            return use_icp, m_icp

        else:
            return self.use_icp, self.m_icp

    def SetICP(self, navigation, use_icp):
        self.use_icp = use_icp
        navigation.icp_queue.put_nowait([self.use_icp, self.m_icp])

    def ResetICP(self):
        self.use_icp = False
        self.m_icp = None
        self.icp_fre = None
