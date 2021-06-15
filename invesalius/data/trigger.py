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

import threading
from time import sleep

import wx
from invesalius_pubsub import pub as Publisher


class Trigger(threading.Thread):
    """
    Thread created to use external trigger to interact with software during neuronavigation
    """

    def __init__(self, nav_id):
        threading.Thread.__init__(self)
        self.trigger_init = None
        self.stylusplh = False
        self.COM = False
        self.nav_id = nav_id
        self.__bind_events()
        try:
            import serial

            self.trigger_init = serial.Serial('COM5', baudrate=115200, timeout=0)
            self.COM = True

        except:
            #wx.MessageBox(_('Connection with port COM1 failed'), _('Communication error'), wx.OK | wx.ICON_ERROR)
            print("Trigger init error: Connection with port COM1 failed")
            self.COM = False

        self._pause_ = False
        self.start()

    def __bind_events(self):
        Publisher.subscribe(self.OnStylusPLH, 'PLH Stylus Button On')

    def OnStylusPLH(self):
        self.stylusplh = True

    def stop(self):
        self._pause_ = True

    def run(self):
        while self.nav_id:
            if self.COM:
                self.trigger_init.write(b'0')
                sleep(0.3)
                lines = self.trigger_init.readlines()
                # Following lines can simulate a trigger in 3 sec repetitions
                # sleep(3)
                # lines = True
                if lines:
                    wx.CallAfter(Publisher.sendMessage, 'Create marker')
                    sleep(0.5)

            if self.stylusplh:
                wx.CallAfter(Publisher.sendMessage, 'Create marker')
                sleep(0.5)
                self.stylusplh = False

            sleep(0.175)
            if self._pause_:
                if self.trigger_init:
                    self.trigger_init.close()
                return


class TriggerNew(threading.Thread):

    def __init__(self, trigger_queue, event, sle):
        """Class (threading) to compute real time tractography data for visualization in a single loop.

        Different than ComputeTractsThread because it does not keep adding tracts to the bundle until maximum,
        is reached. It actually compute all requested tracts at once. (Might be deleted in the future)!
        Tracts are computed using the Trekker library by Baran Aydogan (https://dmritrekker.github.io/)
        For VTK visualization, each tract (fiber) is a constructed as a tube and many tubes combined in one
        vtkMultiBlockDataSet named as a branch. Several branches are combined in another vtkMultiBlockDataSet named as
        bundle, to obtain fast computation and visualization. The bundle dataset is mapped to a single vtkActor.
        Mapper and Actor are computer in the data/viewer_volume.py module for easier handling in the invesalius 3D scene.

        Sleep function in run method is used to avoid blocking GUI and more fluent, real-time navigation

        :param inp: List of inputs: trekker instance, affine numpy array, seed_offset, seed_radius, n_threads
        :type inp: list
        :param affine_vtk: Affine matrix in vtkMatrix4x4 instance to update objects position in 3D scene
        :type affine_vtk: vtkMatrix4x4
        :param coord_queue: Queue instance that manage coordinates read from tracking device and coregistered
        :type coord_queue: queue.Queue
        :param visualization_queue: Queue instance that manage coordinates to be visualized
        :type visualization_queue: queue.Queue
        :param event: Threading event to coordinate when tasks as done and allow UI release
        :type event: threading.Event
        :param sle: Sleep pause in seconds
        :type sle: float
        """

        threading.Thread.__init__(self, name='Trigger')

        self.trigger_init = None
        self.stylusplh = False
        # self.COM = False
        # self.__bind_events()
        try:
            import serial

            self.trigger_init = serial.Serial('COM5', baudrate=115200, timeout=0)
            # self.COM = True

        except:
            #wx.MessageBox(_('Connection with port COM1 failed'), _('Communication error'), wx.OK | wx.ICON_ERROR)
            print("Trigger init error: Connection with port COM failed")
            # self.COM = False
            pass

        # self.coord_queue = coord_queue
        self.trigger_queue = trigger_queue
        self.event = event
        self.sle = sle

    def run(self):

        while not self.event.is_set():
            trigger_on = False
            try:
                self.trigger_init.write(b'0')
                sleep(0.3)
                lines = self.trigger_init.readlines()
                # Following lines can simulate a trigger in 3 sec repetitions
                # sleep(3)
                # lines = True
                if lines:
                    trigger_on = True
                    # wx.CallAfter(Publisher.sendMessage, 'Create marker')

                if self.stylusplh:
                    trigger_on = True
                    # wx.CallAfter(Publisher.sendMessage, 'Create marker')
                    self.stylusplh = False

                self.trigger_queue.put_nowait(trigger_on)
                sleep(self.sle)

            except:
                print("Trigger not read, error")
                pass

            # except queue.Empty:
            #     pass
            # except queue.Full:
            #     self.coord_queue.task_done()
        else:
            if self.trigger_init:
                self.trigger_init.close()
