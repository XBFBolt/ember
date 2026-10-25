"""Shaded views of the STLs, so the geometry can be checked by eye."""
import struct, sys, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

HERE = os.path.dirname(os.path.abspath(__file__))


def load_stl(path):
    with open(path, "rb") as f:
        head = f.read(5)
        f.seek(0)
        if head == b"solid":
            txt = f.read().decode("utf8", "ignore")
            v = [list(map(float, l.split()[1:4]))
                 for l in txt.splitlines() if l.strip().startswith("vertex")]
            return np.array(v).reshape(-1, 3, 3)
        f.seek(80)
        n = struct.unpack("<I", f.read(4))[0]
        tris = np.zeros((n, 3, 3))
        for i in range(n):
            d = struct.unpack("<12fH", f.read(50))
            tris[i] = np.array(d[3:12]).reshape(3, 3)
        return tris


def draw(ax, tris, elev, azim, title, face="#7b8794"):
    nrm = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(nrm, axis=1, keepdims=True)
    nrm = nrm / np.where(ln == 0, 1, ln)
    light = np.array([0.4, -0.7, 0.6]); light /= np.linalg.norm(light)
    # Two-sided lighting: STL winding from a boolean cut is not reliable,
    # and signed shading turns that into stripes that look like slots.
    sh = np.abs(nrm @ light) * 0.62 + 0.38
    base = np.array(matplotlib.colors.to_rgb(face))
    cols = np.clip(base[None, :] * sh[:, None], 0, 1)

    pc = Poly3DCollection(tris, facecolors=cols, edgecolors="none")
    ax.add_collection3d(pc)

    p = tris.reshape(-1, 3)
    c = (p.max(axis=0) + p.min(axis=0)) / 2
    r = (p.max(axis=0) - p.min(axis=0)).max() / 2 * 0.62
    ax.set_xlim(c[0]-r, c[0]+r); ax.set_ylim(c[1]-r, c[1]+r)
    ax.set_zlim(c[2]-r, c[2]+r)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    ax.set_title(title, fontsize=11, color="#2b2b2b", pad=2)


if __name__ == "__main__":
    body = load_stl(os.path.join(HERE, "ember_body.stl"))
    lid = load_stl(os.path.join(HERE, "ember_lid.stl"))
    asm = load_stl(os.path.join(HERE, "ember_assembly.stl"))

    pod = load_stl(os.path.join(HERE, "ember_pod.stl"))
    views = [
        (body, 30, -58, "Body, from above\nshort posts = board, wall bosses = lid"),
        (body, -30, -58, "Body, from underneath\nconcave chest scoop, strap loops, drains"),
        (body, 6, 0, "-X end\nUSB notch (open top), strap loop"),
        (lid, -28, -58, "Lid, underside\nlocating ring, relieved at the bosses"),
        (asm, 20, -58, "Exploded\nlid lifts straight off, 4 x M3"),
        (pod, 34, -58, "Power bank pod\nopen top, 3 mm air all round"),
    ]
    fig = plt.figure(figsize=(15, 8.4), dpi=120)
    for i, (m, e, a, t) in enumerate(views):
        ax = fig.add_subplot(2, 3, i + 1, projection="3d")
        draw(ax, m, e, a, t)
    fig.patch.set_facecolor("white")
    fig.subplots_adjust(left=0, right=1, top=0.95, bottom=0, wspace=0, hspace=0.05)
    fig.savefig(os.path.join(HERE, "ember_views.png"), facecolor="white")
    print("wrote ember_views.png")

    # One big view of the underside - the face that touches a person.
    fig2 = plt.figure(figsize=(8, 7), dpi=140)
    ax = fig2.add_subplot(111, projection="3d")
    draw(ax, body, -30, -52,
         "Body-side face\nconcave R150 scoop, strap loops at both ends, drains")
    fig2.patch.set_facecolor("white")
    fig2.subplots_adjust(left=0, right=1, top=0.93, bottom=0)
    fig2.savefig(os.path.join(HERE, "ember_underside.png"), facecolor="white")
    print("wrote ember_underside.png")
