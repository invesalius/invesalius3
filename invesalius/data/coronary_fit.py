import numpy as np
from invesalius.data.tag import DensityTag
import invesalius.constants as const

class CoronaryFit:
    def __init__(self, point1, point2, start_slice, end_slice, label):
        self.point1 = point1
        self.point2 = point2
        self.start_slice = start_slice
        self.end_slice = end_slice
        self.label = label

    def add_density_tags(self):
        #invert the points
        #if slice is decreasing, don't invert the points
        if self.point1[2] > self.point2[2]:
            x1, y1, z1 = self.point1
            x2, y2, z2 = self.point2
        else:
            x1, y1, z1 = self.point2
            x2, y2, z2 = self.point1

        num_slices = abs(self.end_slice - self.start_slice) + 1

        if self.start_slice < self.end_slice:
            slice_range = range(self.start_slice, self.end_slice + 1)
        else:
            slice_range = range(self.end_slice, self.start_slice + 1)

        xs = np.linspace(x2, x1, num_slices)
        ys = np.linspace(y2, y1, num_slices)

        if num_slices > 1:
            zs = np.arange(z2, z2 + 0.5 * num_slices, 0.5)
            zs = zs[:num_slices]
        else:
            zs = np.array([z2])
        all_means = []
        all_mins = []
        all_maxs = []

        for idx, slice_num in enumerate(slice_range):
            print(f"Adding density tag at slice {slice_num}")
            tag = DensityTag(
                xs[idx], ys[idx], zs[idx], self.label, location=const.AXIAL, slice_number=slice_num
            )
            min, max = tag.GetMinMax()
            center = tag.GetCenter()

            best_center = center

            cx, cy, cz = tag.GetCenter()
            best_center = center
            
            improved = True
            while improved:
                improved = False
                cx, cy, cz = tag.GetCenter()
                best_mean = tag.GetMean()
                for r in np.linspace(0, const.LINE_SPACE, const.LINE_SPACE+1):  # radii from 0 to 50
                    for theta in np.linspace(0, 2 * np.pi, 24, endpoint=False):  # 24 directions
                        dx = r * np.cos(theta)
                        dy = r * np.sin(theta)
                        if r == 0:
                            continue
                        p1 = tag.GetPoint1()
                        p2 = tag.GetPoint2()
                        new_p1 = (p1[0] + dx, p1[1] + dy, p1[2])
                        new_p2 = (p2[0] + dx, p2[1] + dy, p2[2])
                        tag.SetPoint1(new_p1)
                        tag.SetPoint2(new_p2)
                        tag.UpdateCenter((cx + dx, cy + dy, cz))
                        min_tmp, max_tmp = tag.GetMinMax()
                        mean_tmp = tag.GetMean()
                        delta_tmp = max_tmp - min_tmp
                        if delta_tmp < const.MIN_DELTA and max_tmp > const.MAX_TH and min_tmp > const.MIN_TH:
                            if mean_tmp > best_mean:
                                best_mean = mean_tmp
                                best_center = (cx + dx, cy + dy, cz)
                                improved = True

                tag.UpdateCenter(best_center)
                min, max = tag.GetMinMax()
                delta = max - min

            shrink_step = 0.1
            mean = tag.GetMean()
            while mean < const.MIN_MEAN:
                tag.Update(-shrink_step)
                mean = tag.GetMean()

            center = tag.GetCenter()


            all_means.append(mean)
            all_mins.append(min)
            all_maxs.append(max)

        overall_mean = np.mean(all_means)
        overall_min = np.min(all_mins)
        overall_max = np.max(all_maxs)

        from invesalius.i18n import tr as _
        stats_str = _(
            f"mean_density={overall_mean:.2f}\n"
            f"min_density={overall_min:.2f}\n"
            f"max_density={overall_max:.2f}"

        )
        print(stats_str)
        return stats_str
        
