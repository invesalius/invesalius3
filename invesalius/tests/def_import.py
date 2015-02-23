__author__ = 'Victor'

import bases

a = [1, 2, 3]
b = [2, 5, 7]
c = [6, 2, 8]

# M, q, Minv = bases.Bases(a, b, c).Basecreation()
M, q, inv = base_creation(a, b, c)
