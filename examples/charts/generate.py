"""Regenerate both example attachments: uv run --with matplotlib generate.py."""

from pathlib import Path

from matplotlib.figure import Figure
from matplotlib.ticker import MultipleLocator

days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
counts = [18, 27, 21, 34, 30]
ink, muted, accent = '#192b39', '#455966', '#126559'

for style in ('bars', 'line'):
    fig = Figure(figsize=(7, 3.75), dpi=144, facecolor='white')
    fig.text(.09, .90, 'SUPPORT QUEUE   /   SAMPLE WEEK', fontsize=10, weight='bold', color=accent)
    fig.text(.09, .775, 'Tickets resolved per day', fontsize=23, weight='bold', color=ink)
    ax = fig.add_axes([.09, .12, .865, .57])
    ax.set(xlim=(-.5, 4.5), ylim=(0, 40), xticks=range(len(days)), xticklabels=days)
    ax.yaxis.set_major_locator(MultipleLocator(10))
    ax.tick_params(length=0, pad=7, labelsize=11, colors=muted)
    ax.spines[:].set_visible(False)
    ax.grid(axis='y', color='#dce4e6')
    ax.set_axisbelow(True)
    if style == 'bars':
        ax.bar(range(len(days)), counts, width=.54, color=accent)
    else:
        ax.plot(range(len(days)), counts, color=accent, lw=2.5, marker='o', markersize=7)
    for x, count in enumerate(counts):
        ax.annotate(str(count), (x, count), xytext=(0, 7), textcoords='offset points',
                    ha='center', fontsize=12, weight='bold', color=ink)
    fig.savefig(Path(__file__).with_name(f'{style}.png'))
