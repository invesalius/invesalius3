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

"""Share sample timing and playback between source readers, maps and the timeline.

Times are in seconds. Playback advances from elapsed time rather than GUI timer
frequency, keeping sample selection independent of rendering speed and file format.
"""

from dataclasses import dataclass
from math import floor, isfinite
from operator import index
from time import monotonic


@dataclass(frozen=True)
class TimeAxis:
    """Define a validated, uniformly sampled recording and its time/index conversions.

    Readers supply the first sample time, positive sampling interval and frame count.
    The same conversions drive map frames and timeline seeking, including recordings
    that start before time zero.
    """

    t0: float
    dt: float
    n_frames: int

    def __post_init__(self):
        if index(self.n_frames) < 1:
            raise ValueError("A time series must contain at least one frame.")
        if not isfinite(self.t0) or not isfinite(self.dt) or self.dt <= 0:
            raise ValueError(
                "Time origin must be finite and time step must be positive and finite."
            )
        if not isfinite(self.end) or (self.n_frames > 1 and self.end <= self.t0):
            raise ValueError("Time axis cannot be represented with finite, distinct endpoints.")

    @property
    def end(self):
        return self.t0 + (self.n_frames - 1) * self.dt

    def check_index(self, frame_index):
        frame_index = index(frame_index)
        if not 0 <= frame_index < self.n_frames:
            raise IndexError("Frame index is outside the time series.")
        return frame_index

    def time_at(self, frame_index):
        return self.t0 + self.check_index(frame_index) * self.dt

    def index_at(self, time):
        """Select the nearest sample, clipping to the recorded interval."""
        if not isfinite(time):
            raise ValueError("Selected time must be finite.")
        if time <= self.t0:
            return 0
        if time >= self.end:
            return self.n_frames - 1
        return min(self.n_frames - 1, floor((time - self.t0) / self.dt + 0.5))


class Playback:
    """Track playback position and speed without owning a timer or rendering objects.

    The GUI calls tick with its own refresh schedule. Elapsed monotonic time decides
    the current sample, while seeking and stepping stay within the recording.
    """

    def __init__(self, axis: TimeAxis):
        self.axis = axis
        self.index = 0
        self.playing = False
        self.speed = 1.0
        self._position = axis.t0
        self._last_tick = monotonic()

    @property
    def time(self):
        return self.axis.time_at(self.index)

    def seek(self, frame_index):
        self.index = self.axis.check_index(frame_index)
        self._position = self.time
        self._last_tick = monotonic()
        return self.index

    def seek_time(self, time):
        return self.seek(self.axis.index_at(time))

    def play(self):
        if self.playing:
            return
        if self._position >= self.axis.end:
            self.seek(0)
        self._last_tick = monotonic()
        self.playing = self.axis.n_frames > 1

    def pause(self):
        self.tick()
        self.playing = False

    def stop(self):
        self.playing = False
        self.seek(0)

    def step(self, offset):
        offset = index(offset)
        self.pause()
        return self.seek(max(0, min(self.axis.n_frames - 1, self.index + offset)))

    def set_speed(self, speed):
        if not isfinite(speed) or speed <= 0:
            raise ValueError("Playback speed must be positive and finite.")
        self.tick()
        self.speed = speed

    def tick(self):
        if self.playing:
            now = monotonic()
            self._position = min(
                self.axis.end, self._position + (now - self._last_tick) * self.speed
            )
            self._last_tick = now
            self.index = self.axis.index_at(self._position)
            if self._position >= self.axis.end:
                self.playing = False
        return self.index
