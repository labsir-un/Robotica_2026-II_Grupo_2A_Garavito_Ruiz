from robodk.robolink import *
from robodk.robomath import *
import numpy as np
from matplotlib.textpath import TextPath
from matplotlib.font_manager import FontProperties

# ================= PARAMETROS =================
FRAME_NAME = "Frame_from_Target1"
Z_SURFACE = 0.0             # altura de contacto en el Frame (ajustar si el Frame esta pegado a la superficie)
Z_SAFE = 50                 # distancia positiva; al llamar se resta: Z_SURFACE - Z_SAFE
SPEED = 300                 # mm/s
ROUNDING = 0.1             # mm (menor = mas preciso, pero mas lento)

A = 150                     # tamano de la mariposa (mm)
N_SAMPLES = 50            # muestreo fino de la curva; luego RDP descarta lo redundante
TOLERANCE = 0.3             # mm de error maximo permitido al simplificar (balance puntos vs suavidad)
TEXT_W, TEXT_H = 240, 38    # caja de cada nombre (mm)
Y_NAMES = {"Felipe": -130, "Alexandra": -190}

# Orientacion de toda la composicion
MIRROR_Y = True             # corrige el efecto espejo
ROT_DEG = 90                # si sale de cabeza prueba 270; de lado prueba 0 o 180
OFFSET = np.array([300, 0])

# ================= CONEXION =================
RDK = Robolink()
robot = RDK.ItemUserPick("Selecciona un robot", ITEM_TYPE_ROBOT)
frame = RDK.Item(FRAME_NAME, ITEM_TYPE_FRAME)
home = RDK.Item("TargetHome", ITEM_TYPE_TARGET)

if not robot.Valid() or not frame.Valid() or not home.Valid():
    raise Exception(f'Falta el robot, el Frame "{FRAME_NAME}" o "TargetHome".')

'''
# Conectar al robot físico
if not robot.Connect():
    raise Exception("No se pudo conectar al robot. Verifica que esté en modo remoto y que la configuración sea correcta.")

# Confirmar conexión
state, msg = robot.ConnectedState()
if state != ROBOTCOM_READY:
    raise Exception(f"El robot no esta listo (codigo {state}): {msg}")
    
print("Robot conectado correctamente.")
'''

robot.setPoseFrame(frame)
robot.setPoseTool(robot.PoseTool())
robot.setSpeed(SPEED)
robot.setRounding(ROUNDING)

# ================= GEOMETRIA =================
def rdp(P, tol):
    """Ramer-Douglas-Peucker iterativo: quita puntos que desvian menos de tol mm."""
    P = np.asarray(P, dtype=float)
    keep = np.zeros(len(P), dtype=bool)
    keep[[0, -1]] = True
    stack = [(0, len(P) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, d = P[i], P[j] - P[i]
        seg = P[i + 1:j] - a
        n = np.hypot(*d)
        dist = np.hypot(*seg.T) if n == 0 else np.abs(d[0] * seg[:, 1] - d[1] * seg[:, 0]) / n
        k = np.argmax(dist)
        if dist[k] > tol:
            m = i + 1 + k
            keep[m] = True
            stack += [(i, m), (m, j)]
    return P[keep]


def transform(points):
    """Espejo en Y -> rotacion global -> traslacion."""
    a = np.radians(ROT_DEG)
    R = np.array([[np.cos(a), -np.sin(a)],
                  [np.sin(a),  np.cos(a)]])
    pts = np.asarray(points, dtype=float)
    if MIRROR_Y:
        pts = pts * [1, -1]
    return pts @ R.T + OFFSET


def butterfly():
    t = np.linspace(0, 12 * np.pi, N_SAMPLES + 1)
    r = np.exp(np.sin(t)) - 2 * np.cos(4 * t) + np.sin((2 * t - np.pi) / 24) ** 5
    r = A * r / np.max(np.abs(r))
    return rdp(np.column_stack((r * np.cos(t), r * np.sin(t))), TOLERANCE)


def text_paths(text, y_base):
    tp = TextPath((0, 0), text, size=100,
                  prop=FontProperties(family="DejaVu Sans", weight="bold"))
    polys = tp.to_polygons(closed_only=False)
    allp = np.vstack(polys)
    mn, mx = allp.min(axis=0), allp.max(axis=0)
    scale = min(TEXT_W / (mx[0] - mn[0]), TEXT_H / (mx[1] - mn[1]))
    origin = np.array([(mn[0] + mx[0]) / 2, mn[1]])   # centrado en X, base en Y
    paths = []
    for p in polys:
        p = (p - origin) * scale + [0, y_base]
        if not np.allclose(p[0], p[-1]):              # cerrar contorno
            p = np.vstack([p, p[:1]])
        paths.append(rdp(p, TOLERANCE))
    return paths


# ================= DIBUJO =================
def draw(path):
    pts = transform(path)
    x0, y0 = pts[0]
    robot.MoveJ(transl(float(x0), float(y0), Z_SURFACE - Z_SAFE))   # aproximacion
    for x, y in pts:
        robot.MoveL(transl(float(x), float(y), Z_SURFACE))          # trazo
    xf, yf = pts[-1]
    robot.MoveL(transl(float(xf), float(yf), Z_SURFACE - Z_SAFE))   # retirada


# ================= RUTINA =================
paths = [butterfly()]
for name, y in Y_NAMES.items():
    paths += text_paths(name, y)
print("Trayectorias:", len(paths), "| Puntos totales:", sum(len(p) for p in paths))

robot.MoveJ(home)          # inicio en Home
for p in paths:
    draw(p)
robot.MoveJ(home)          # final en Home
print("DIBUJO COMPLETADO")
