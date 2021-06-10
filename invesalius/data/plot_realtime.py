import random
from itertools import count
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

#plt.style.use('fivethirtyeight')
matplotlib.use('TkAgg')

x_vals = []
y_vals = []

index = count()
fig, (ax1, ax2) = plt.subplots(2)

def animate(i):
    data = pd.read_csv('D:\\Repository\\invesalius3\\data.csv')
    x = data['time']
    y1 = data['x']
    y2 = data['xf']
    status_x = data['statusx']

    ax1.cla()
    ax2.cla()

    ax1.plot(x, y1, label='Coord x')
    ax1.plot(x, y2, label='Coord x after Kalman')

    ax2.plot(x, status_x, label='STD', color='red')

    ax1.legend(loc='upper left')
    ax2.legend(loc='upper left')


ani = FuncAnimation(fig, animate, interval=0.1)

plt.tight_layout()
plt.show()