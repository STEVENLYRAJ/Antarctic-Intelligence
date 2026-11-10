"""Shared plotting style (validated reference palette, fixed categorical order)."""
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
OTHER, INK, INK2, MUTED, SURFACE, GRID = "#898781", "#0b0b0b", "#52514e", "#898781", "#fcfcfb", "#e4e3df"
BLUE_CMAP = LinearSegmentedColormap.from_list("sic", ["#f0efec", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"])
DIVERGING = LinearSegmentedColormap.from_list("div", ["#c2410c", "#eb6834", "#f6c6ad", "#f0efec", "#b7d3f6", "#3987e5", "#184f95"])


def apply_style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": MUTED, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "axes.titlecolor": INK, "axes.titlesize": 11.5, "axes.titleweight": "bold", "axes.labelsize": 10,
        "font.size": 9.5, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False, "lines.linewidth": 1.8,
    })
