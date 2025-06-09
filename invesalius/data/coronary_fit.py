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
        x1, y1, z1 = self.point2
        x2, y2, z2 = self.point1

        num_slices = abs(self.end_slice - self.start_slice) + 1

        # Interpolate x and y normally, but z by 0.5 per step
        if self.start_slice < self.end_slice:
            slice_range = range(self.start_slice, self.end_slice + 1)
        else:
            slice_range = range(self.end_slice, self.start_slice + 1)

        xs = np.linspace(x2, x1, num_slices)
        ys = np.linspace(y2, y1, num_slices)
        # z progresses by 0.5 per slice, starting from z2 towards z1
        if num_slices > 1:
            # if z1 > z2:
            zs = np.arange(z2, z2 + 0.5 * num_slices, 0.5)
            # else:
            #     zs = np.arange(z2, z2 - 0.5 * num_slices, -0.5)
            zs = zs[:num_slices]
        else:
            zs = np.array([z2])

        for idx, slice_num in enumerate(slice_range):
            print(f"Adding density tag at slice {slice_num}")
            tag = DensityTag(
                xs[idx], ys[idx], zs[idx], self.label, location=const.AXIAL, slice_number=slice_num
            )
            min, max = tag.GetMinMax()
            center = tag.GetCenter()
            delta = max - min

            # Store original perimeter
            min_perimeter = 5

            # Try to maximize delta by moving center in x, y (within 10 units)
            best_center = center
            best_delta = delta

            # Integrate shrinkage and center movement together
            cx, cy, cz = tag.GetCenter()
            best_center = center
            best_delta = delta
            best_max = max
            
            

            improved = True
            while improved:
                improved = False

                # Try moving center radially in x, y
                cx, cy, cz = tag.GetCenter()
                best_mean = tag.GetMean()
                for r in np.linspace(0, 50, 51):  # radii from 0 to 50
                    for theta in np.linspace(0, 2 * np.pi, 24, endpoint=False):  # 24 directions
                        dx = r * np.cos(theta)
                        dy = r * np.sin(theta)
                        if r == 0:
                            continue  # skip the original center, already checked
                        # Shift p1 and p2 by the same dx, dy as the center
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
                        # Only consider if delta is below 200, max density above 400, and min above 226
                        if delta_tmp < 200 and max_tmp > 400 and min_tmp > 226:
                            if mean_tmp > best_mean:
                                best_mean = mean_tmp
                                best_center = (cx + dx, cy + dy, cz)
                                improved = True

                tag.UpdateCenter(best_center)
                min, max = tag.GetMinMax()
                delta = max - min

            # Separate loop: shrink the tag while mean is less than 200
            shrink_step = 0.1
            mean = tag.GetMean()
            while mean < 200:
                tag.Update(-shrink_step)
                mean = tag.GetMean()

            center = tag.GetCenter()
