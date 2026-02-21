import copy
import base64
import hashlib
import io
import json
import os
import time
import wave
from pathlib import Path

from PIL import Image, ImageDraw

from PySide6.QtCore import Qt, QRect, QPoint, Signal, QTimer, QEasingCurve, QPropertyAnimation, QEvent
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QBrush, QPainterPath, QAction, QShortcut, QKeySequence, QPixmap, QCursor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QGridLayout,
    QSizePolicy,
    QVBoxLayout,
    QColorDialog,
    QWidget,
    QScrollArea,
    QGraphicsOpacityEffect,
)

from core_utils import pil_to_qpixmap


class NodeGraphCanvas(QWidget):
    linksChanged = Signal(list)
    nodeSelected = Signal(int)
    requestRemoveNode = Signal(int)
    connectionRejected = Signal(str)
    portSelected = Signal(int, str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.nodes = []
        self.links = []
        self.node_io = []
        self._node_pos = {}
        self._selected = -1
        self._connect_src = (-1, 0)
        self._drag_idx = -1
        self._drag_off = QPoint(0, 0)
        self._node_size = (176, 74)
        self._drag_link = None
        self._drag_link_pos = QPoint(0, 0)
        self._drag_link_hover_in = None
        self._selected_port = None
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._panning = False
        self._pan_anchor = QPoint(0, 0)
        self._pan_start = (0.0, 0.0)
        self.setMinimumHeight(180)
        self.setMouseTracking(True)

    def _normalize_stream_type(self, t):
        v = str(t or "").strip().lower()
        if v in ("video", "audio", "data", "any"):
            return v
        return "video"

    def _ensure_type_list(self, value, count, default_type):
        cnt = max(1, int(count))
        base = []
        if isinstance(value, list):
            base = [self._normalize_stream_type(x) for x in value]
        elif isinstance(value, str) and value.strip():
            base = [self._normalize_stream_type(value.strip())]
        if not base:
            base = [self._normalize_stream_type(default_type)]
        while len(base) < cnt:
            base.append(base[-1])
        return base[:cnt]

    def _clean_links(self, links):
        out = []
        seen = set()
        n = len(self.nodes)
        for link in (links or []):
            try:
                if isinstance(link, dict):
                    a = int(link.get("src", -1))
                    b = int(link.get("dst", -1))
                    op = int(link.get("src_port", 0))
                    ip = int(link.get("dst_port", 0))
                elif isinstance(link, (list, tuple)) and len(link) >= 4:
                    a, b, op, ip = int(link[0]), int(link[1]), int(link[2]), int(link[3])
                else:
                    a, b = int(link[0]), int(link[1])
                    op, ip = 0, 0
            except Exception:
                continue
            if a == b or a < 0 or b < 0 or a >= n or b >= n:
                continue
            op = max(0, op)
            ip = max(0, ip)
            try:
                op_max = max(1, int(self._port_count(a, "out")))
                ip_max = max(1, int(self._port_count(b, "in")))
                if op >= op_max or ip >= ip_max:
                    continue
                out_t = self._port_type(a, "out", op)
                in_t = self._port_type(b, "in", ip)
                if not self._port_compatible(out_t, in_t):
                    continue
            except Exception:
                pass
            key = (a, b, op, ip)
            if key in seen:
                continue
            seen.add(key)
            out.append([a, b, op, ip])
        return out

    def _norm_io(self, node_io, count):
        out = []
        src = node_io if isinstance(node_io, list) else []
        for i in range(int(count)):
            d = {"inputs": 1, "outputs": 1, "in_types": ["video"], "out_types": ["video"]}
            if i < len(src) and isinstance(src[i], dict):
                try:
                    d["inputs"] = max(1, min(8, int(src[i].get("inputs", 1) or 1)))
                    d["outputs"] = max(1, min(8, int(src[i].get("outputs", 1) or 1)))
                except Exception:
                    pass
                d["in_types"] = self._ensure_type_list(
                    src[i].get("in_types", src[i].get("input_type", "video")),
                    d["inputs"],
                    src[i].get("input_type", "video"),
                )
                d["out_types"] = self._ensure_type_list(
                    src[i].get("out_types", src[i].get("output_type", "video")),
                    d["outputs"],
                    src[i].get("output_type", "video"),
                )
            else:
                d["in_types"] = self._ensure_type_list(["video"], d["inputs"], "video")
                d["out_types"] = self._ensure_type_list(["video"], d["outputs"], "video")
            out.append(d)
        return out

    def _default_pos(self, idx):
        col = int(idx) % 4
        row = int(idx) // 4
        return QPoint(24 + col * 188, 26 + row * 112)

    def set_graph(self, nodes, links=None, node_io=None):
        self.nodes = [str(n) for n in (nodes or []) if str(n).strip()]
        self.node_io = self._norm_io(node_io, len(self.nodes))
        self.links = self._clean_links(links)
        alive = {}
        for i in range(len(self.nodes)):
            alive[i] = QPoint(self._node_pos.get(i, self._default_pos(i)))
        self._node_pos = alive
        if self._selected >= len(self.nodes):
            self._selected = len(self.nodes) - 1
        if int(self._connect_src[0]) >= len(self.nodes):
            self._connect_src = (-1, 0)
        if isinstance(self._selected_port, dict):
            try:
                sp_idx = int(self._selected_port.get("idx", -1))
            except Exception:
                sp_idx = -1
            if sp_idx < 0 or sp_idx >= len(self.nodes):
                self._selected_port = None
        self.update()

    def _to_world(self, x, y):
        z = max(0.4, min(3.0, float(self.zoom)))
        wx = (float(x) - float(self.pan_x)) / z
        wy = (float(y) - float(self.pan_y)) / z
        return wx, wy

    def _to_view(self, x, y):
        z = max(0.4, min(3.0, float(self.zoom)))
        vx = float(x) * z + float(self.pan_x)
        vy = float(y) * z + float(self.pan_y)
        return int(round(vx)), int(round(vy))

    def _node_rect(self, idx):
        pos = self._node_pos.get(idx, self._default_pos(idx))
        w, h = self._node_size
        x, y = self._to_view(pos.x(), pos.y())
        ww = max(56, int(round(w * self.zoom)))
        hh = max(28, int(round(h * self.zoom)))
        return QRect(int(x), int(y), int(ww), int(hh))

    def _hit_node(self, x, y):
        for i in range(len(self.nodes) - 1, -1, -1):
            if self._node_rect(i).contains(int(x), int(y)):
                return i
        return -1

    def _port_count(self, idx, side):
        if idx < 0 or idx >= len(self.node_io):
            return 1
        io = self.node_io[idx] if isinstance(self.node_io[idx], dict) else {}
        if side == "in":
            return max(1, int(io.get("inputs", 1) or 1))
        return max(1, int(io.get("outputs", 1) or 1))

    def _port_type(self, idx, side="out", port=0):
        if idx < 0 or idx >= len(self.node_io):
            return "video"
        io = self.node_io[idx] if isinstance(self.node_io[idx], dict) else {}
        if side == "in":
            cnt = max(1, int(io.get("inputs", 1) or 1))
            arr = self._ensure_type_list(io.get("in_types", io.get("input_type", "video")), cnt, io.get("input_type", "video"))
        else:
            cnt = max(1, int(io.get("outputs", 1) or 1))
            arr = self._ensure_type_list(io.get("out_types", io.get("output_type", "video")), cnt, io.get("output_type", "video"))
        p = max(0, min(len(arr) - 1, int(port)))
        return self._normalize_stream_type(arr[p] if p < len(arr) else "video")

    def _port_compatible(self, out_t, in_t):
        a = self._normalize_stream_type(out_t)
        b = self._normalize_stream_type(in_t)
        if a == "any" or b == "any":
            return True
        return a == b

    def _port_color(self, t):
        tt = self._normalize_stream_type(t)
        if tt == "audio":
            return QColor(136, 236, 152, 230)
        if tt == "data":
            return QColor(246, 196, 118, 230)
        if tt == "any":
            return QColor(218, 180, 252, 230)
        return QColor(124, 220, 255, 230)

    def _port_badge(self, t):
        tt = self._normalize_stream_type(t)
        if tt == "audio":
            return "A"
        if tt == "data":
            return "D"
        if tt == "any":
            return "*"
        return "V"

    def _select_port(self, idx, side, port):
        try:
            i = int(idx)
            p = int(max(0, port))
            s = str(side or "").strip().lower()
        except Exception:
            i = -1
            p = 0
            s = ""
        if s not in ("in", "out") or i < 0:
            self._selected_port = None
            self.update()
            return
        self._selected_port = {"idx": i, "side": s, "port": p}
        try:
            self.portSelected.emit(i, s, p)
        except Exception:
            pass
        self.update()

    def selected_port(self):
        if isinstance(self._selected_port, dict):
            return dict(self._selected_port)
        return None

    def links_for_port(self, port_info=None):
        info = port_info if isinstance(port_info, dict) else (self._selected_port if isinstance(self._selected_port, dict) else None)
        if not isinstance(info, dict):
            return []
        try:
            idx = int(info.get("idx", -1))
            side = str(info.get("side", "")).strip().lower()
            port = int(info.get("port", 0))
        except Exception:
            return []
        out = []
        for lk in (self.links or []):
            try:
                a, b = int(lk[0]), int(lk[1])
                op = int(lk[2]) if len(lk) >= 3 else 0
                ip = int(lk[3]) if len(lk) >= 4 else 0
            except Exception:
                continue
            if side == "out" and a == idx and op == port:
                out.append([a, b, op, ip])
            elif side == "in" and b == idx and ip == port:
                out.append([a, b, op, ip])
        return out

    def remove_link(self, link):
        if not isinstance(link, (list, tuple)) or len(link) < 2:
            return
        try:
            a = int(link[0])
            b = int(link[1])
            op = int(link[2]) if len(link) >= 3 else 0
            ip = int(link[3]) if len(link) >= 4 else 0
        except Exception:
            return
        keep = []
        for lk in (self.links or []):
            try:
                x, y = int(lk[0]), int(lk[1])
                xo = int(lk[2]) if len(lk) >= 3 else 0
                yi = int(lk[3]) if len(lk) >= 4 else 0
            except Exception:
                continue
            if x == a and y == b and xo == op and yi == ip:
                continue
            keep.append([x, y, xo, yi])
        self.links = keep
        self._emit_links()

    def remove_links_for_port(self, port_info=None):
        info = port_info if isinstance(port_info, dict) else (self._selected_port if isinstance(self._selected_port, dict) else None)
        if not isinstance(info, dict):
            return
        try:
            idx = int(info.get("idx", -1))
            side = str(info.get("side", "")).strip().lower()
            port = int(info.get("port", 0))
        except Exception:
            return
        if idx < 0 or side not in ("in", "out"):
            return
        keep = []
        for lk in (self.links or []):
            try:
                a, b = int(lk[0]), int(lk[1])
                op = int(lk[2]) if len(lk) >= 3 else 0
                ip = int(lk[3]) if len(lk) >= 4 else 0
            except Exception:
                continue
            if side == "out" and a == idx and op == port:
                continue
            if side == "in" and b == idx and ip == port:
                continue
            keep.append([a, b, op, ip])
        self.links = keep
        self._emit_links()

    def _port_pos(self, idx, side="out", port=0):
        r = self._node_rect(idx)
        cnt = max(1, self._port_count(idx, "in" if side == "in" else "out"))
        port = max(0, min(cnt - 1, int(port)))
        slot = float(port + 1) / float(cnt + 1)
        y = int(round(r.top() + slot * r.height()))
        if side == "in":
            return QPoint(int(r.left()), y)
        return QPoint(int(r.right()), y)

    def _hit_port(self, x, y, side=None):
        px = int(x)
        py = int(y)
        tol = max(7, int(round(8 * max(0.7, self.zoom))))
        sides = []
        if side in ("in", "out"):
            sides = [side]
        else:
            sides = ["out", "in"]
        for idx in range(len(self.nodes) - 1, -1, -1):
            for s in sides:
                cnt = self._port_count(idx, s)
                for port in range(cnt):
                    p = self._port_pos(idx, s, port)
                    if abs(px - p.x()) <= tol and abs(py - p.y()) <= tol:
                        return {"idx": int(idx), "side": s, "port": int(port), "pos": p}
        return None

    def _would_cycle(self, a, b):
        graph = {}
        for i in range(len(self.nodes)):
            graph[i] = []
        for lk in self.links:
            x, y = int(lk[0]), int(lk[1])
            if x in graph:
                graph[x].append(y)
        graph.setdefault(a, []).append(b)
        target = int(a)
        seen = set()
        stack = [int(b)]
        while stack:
            cur = stack.pop()
            if cur == target:
                return True
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(graph.get(cur, []))
        return False

    def _emit_links(self):
        self.links = self._clean_links(self.links)
        self.linksChanged.emit([list(x) for x in self.links])
        self.update()

    def _remove_node_and_links(self, idx):
        idx = int(idx)
        if idx < 0 or idx >= len(self.nodes):
            return
        remap = {}
        j = 0
        for i in range(len(self.nodes)):
            if i == idx:
                continue
            remap[i] = j
            j += 1
        new_links = []
        for lk in self.links:
            a, b, op, ip = int(lk[0]), int(lk[1]), int(lk[2]), int(lk[3])
            if a == idx or b == idx:
                continue
            na = remap.get(a, -1)
            nb = remap.get(b, -1)
            if na >= 0 and nb >= 0 and na != nb:
                new_links.append([na, nb, op, ip])
        self.links = self._clean_links(new_links)
        new_pos = {}
        for old, new in remap.items():
            new_pos[new] = QPoint(self._node_pos.get(old, self._default_pos(new)))
        self._node_pos = new_pos
        self._selected = -1
        self._connect_src = (-1, 0)
        self._selected_port = None
        self.linksChanged.emit([list(x) for x in self.links])
        self.requestRemoveNode.emit(int(idx))

    def contextMenuEvent(self, ev):
        px = int(ev.pos().x())
        py = int(ev.pos().y())
        port_hit = self._hit_port(px, py, side=None)
        idx = self._hit_node(px, py)
        menu = QMenu(self)
        if isinstance(port_hit, dict):
            pidx = int(port_hit.get("idx", -1))
            pside = str(port_hit.get("side", "")).strip().lower()
            pnum = int(port_hit.get("port", 0))
            self._select_port(pidx, pside, pnum)
            ptype = self._port_type(pidx, pside, pnum)
            pbadge = self._port_badge(ptype)
            pside_lbl = "Input" if pside == "in" else "Output"
            head = QAction(f"{self.nodes[pidx]}  {pside_lbl} {pnum + 1}  [{ptype}/{pbadge}]", self)
            head.setEnabled(False)
            menu.addAction(head)
            if pside == "out":
                set_src = QAction("Set as connect source", self)
                set_src.triggered.connect(lambda: self._set_connect_source(pidx, pnum))
                menu.addAction(set_src)
            links = self.links_for_port(port_hit)
            if links:
                menu.addSeparator()
                det_all = QAction("Detach all links from this port", self)
                det_all.triggered.connect(lambda: self.remove_links_for_port(port_hit))
                menu.addAction(det_all)
                det_menu = menu.addMenu("Detach selected link")
                for lk in links:
                    try:
                        a, b, op, ip = int(lk[0]), int(lk[1]), int(lk[2]), int(lk[3])
                    except Exception:
                        continue
                    title = f"{self.nodes[a]}:O{op + 1}  ->  {self.nodes[b]}:I{ip + 1}"
                    act = QAction(title, self)
                    act.triggered.connect(lambda _=False, link=list(lk): self.remove_link(link))
                    det_menu.addAction(act)
            menu.exec(ev.globalPos())
            return
        if idx >= 0:
            self._selected = int(idx)
            self.nodeSelected.emit(int(idx))
            node_name = self.nodes[idx]
            src_menu = menu.addMenu(f"Set source: {node_name}")
            outc = self._port_count(idx, "out")
            for op in range(outc):
                t = self._port_type(idx, "out", op)
                act = QAction(f"Output {op + 1} [{t}]", self)
                act.triggered.connect(lambda _=False, i=idx, p=op: self._set_connect_source(i, p))
                src_menu.addAction(act)
            if int(self._connect_src[0]) >= 0 and int(self._connect_src[0]) != idx:
                src_idx = int(self._connect_src[0])
                src_port = int(self._connect_src[1])
                in_menu = menu.addMenu(f"Connect {self.nodes[src_idx]}:O{src_port + 1} -> {node_name}")
                inc = self._port_count(idx, "in")
                out_t = self._port_type(src_idx, "out", src_port)
                for ip in range(inc):
                    in_t = self._port_type(idx, "in", ip)
                    ok = self._port_compatible(out_t, in_t)
                    title = f"Input {ip + 1} [{in_t}]"
                    if not ok:
                        title += "  (incompatible)"
                    conn = QAction(title, self)
                    conn.setEnabled(ok)
                    conn.triggered.connect(lambda _=False, a=src_idx, b=idx, op=src_port, ipt=ip: self._connect_nodes(a, b, op, ipt))
                    in_menu.addAction(conn)
            menu.addSeparator()
            drop_in = QAction("Disconnect inputs", self)
            drop_out = QAction("Disconnect outputs", self)
            drop_in.triggered.connect(lambda: self._remove_links_to(idx))
            drop_out.triggered.connect(lambda: self._remove_links_from(idx))
            menu.addAction(drop_in)
            menu.addAction(drop_out)
            menu.addSeparator()
            rm = QAction("Remove node", self)
            rm.triggered.connect(lambda: self._remove_node_and_links(idx))
            menu.addAction(rm)
        else:
            clear = QAction("Clear links", self)
            clear.triggered.connect(self._clear_links)
            menu.addAction(clear)
            reset_view = QAction("Reset view", self)
            reset_view.triggered.connect(self._reset_view)
            menu.addAction(reset_view)
        menu.exec(ev.globalPos())

    def _set_connect_source(self, idx, out_port=0):
        self._connect_src = (int(idx), int(max(0, out_port)))
        self._select_port(int(idx), "out", int(max(0, out_port)))
        self.update()

    def _connect_nodes(self, a, b, out_port=0, in_port=0):
        a = int(a)
        b = int(b)
        out_port = int(max(0, out_port))
        in_port = int(max(0, in_port))
        if a < 0 or b < 0 or a == b:
            return
        if self._would_cycle(a, b):
            return
        out_t = self._port_type(a, "out", out_port)
        in_t = self._port_type(b, "in", in_port)
        if not self._port_compatible(out_t, in_t):
            try:
                self.connectionRejected.emit(f"Incompatible ports: {out_t} -> {in_t}")
            except Exception:
                pass
            return
        link = [a, b, out_port, in_port]
        if link not in self.links:
            self.links.append(link)
        self._emit_links()

    def _remove_links_to(self, idx):
        idx = int(idx)
        self.links = [list(x) for x in self.links if int(x[1]) != idx]
        self._emit_links()

    def _remove_links_from(self, idx):
        idx = int(idx)
        self.links = [list(x) for x in self.links if int(x[0]) != idx]
        self._emit_links()

    def _clear_links(self):
        self.links = []
        self._emit_links()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_anchor = ev.pos()
            self._pan_start = (float(self.pan_x), float(self.pan_y))
            ev.accept()
            return
        if ev.button() == Qt.LeftButton:
            port_hit = self._hit_port(ev.pos().x(), ev.pos().y(), side="out")
            if port_hit is not None:
                self._selected = int(port_hit["idx"])
                self.nodeSelected.emit(int(port_hit["idx"]))
                self._select_port(int(port_hit["idx"]), "out", int(port_hit["port"]))
                self._drag_link = {
                    "src_idx": int(port_hit["idx"]),
                    "src_port": int(port_hit["port"]),
                }
                self._drag_link_pos = QPoint(int(ev.pos().x()), int(ev.pos().y()))
                self.update()
                ev.accept()
                return
            in_hit = self._hit_port(ev.pos().x(), ev.pos().y(), side="in")
            if in_hit is not None:
                self._selected = int(in_hit["idx"])
                self.nodeSelected.emit(int(in_hit["idx"]))
                self._select_port(int(in_hit["idx"]), "in", int(in_hit["port"]))
                self._drag_idx = -1
                self.update()
                ev.accept()
                return
            idx = self._hit_node(ev.pos().x(), ev.pos().y())
            self._selected = int(idx)
            if idx >= 0:
                self._drag_idx = int(idx)
                wx, wy = self._to_world(ev.pos().x(), ev.pos().y())
                p = self._node_pos.get(idx, self._default_pos(idx))
                self._drag_off = QPoint(int(round(wx - p.x())), int(round(wy - p.y())))
                self.nodeSelected.emit(int(idx))
                self._select_port(-1, "", 0)
            else:
                self._drag_idx = -1
                self._select_port(-1, "", 0)
            self.update()
            ev.accept()
            return
        return super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._panning and (ev.buttons() & Qt.MiddleButton):
            dx = int(ev.pos().x() - self._pan_anchor.x())
            dy = int(ev.pos().y() - self._pan_anchor.y())
            self.pan_x = float(self._pan_start[0] + dx)
            self.pan_y = float(self._pan_start[1] + dy)
            self.update()
            ev.accept()
            return
        if self._drag_link is not None and (ev.buttons() & Qt.LeftButton):
            self._drag_link_pos = QPoint(int(ev.pos().x()), int(ev.pos().y()))
            self._drag_link_hover_in = self._hit_port(ev.pos().x(), ev.pos().y(), side="in")
            self.update()
            ev.accept()
            return
        if self._drag_idx >= 0 and (ev.buttons() & Qt.LeftButton):
            idx = int(self._drag_idx)
            wx, wy = self._to_world(ev.pos().x(), ev.pos().y())
            x = int(round(wx - self._drag_off.x()))
            y = int(round(wy - self._drag_off.y()))
            self._node_pos[idx] = QPoint(x, y)
            self.update()
            ev.accept()
            return
        return super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._drag_link is not None and ev.button() == Qt.LeftButton:
            src_idx = int(self._drag_link.get("src_idx", -1))
            src_port = int(self._drag_link.get("src_port", 0))
            dst_hit = self._hit_port(ev.pos().x(), ev.pos().y(), side="in")
            self._drag_link = None
            self._drag_link_pos = QPoint(0, 0)
            self._drag_link_hover_in = None
            if dst_hit is not None:
                self._connect_nodes(src_idx, int(dst_hit["idx"]), src_port, int(dst_hit["port"]))
                self._select_port(int(dst_hit["idx"]), "in", int(dst_hit["port"]))
            self.update()
            ev.accept()
            return
        self._drag_idx = -1
        self._panning = False
        return super().mouseReleaseEvent(ev)

    def wheelEvent(self, ev):
        mods = ev.modifiers()
        if mods & Qt.ControlModifier:
            old = float(self.zoom)
            delta = ev.angleDelta().y()
            factor = 1.12 if delta > 0 else (1.0 / 1.12)
            nz = max(0.4, min(3.0, old * factor))
            if abs(nz - old) < 1e-4:
                return
            px = float(ev.position().x())
            py = float(ev.position().y())
            wx, wy = self._to_world(px, py)
            self.zoom = nz
            self.pan_x = px - wx * self.zoom
            self.pan_y = py - wy * self.zoom
            self.update()
            ev.accept()
            return
        return super().wheelEvent(ev)

    def _reset_view(self):
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            p.fillRect(self.rect(), QColor(10, 16, 26, 228))
            p.setPen(QPen(QColor(64, 88, 118, 82), 1))
            step = max(12, int(round(32 * self.zoom)))
            ox = int(self.pan_x) % step
            oy = int(self.pan_y) % step
            for x in range(ox, self.width(), step):
                p.drawLine(x, 0, x, self.height())
            for y in range(oy, self.height(), step):
                p.drawLine(0, y, self.width(), y)
            major = max(step * 4, 48)
            p.setPen(QPen(QColor(96, 128, 168, 92), 1))
            ox2 = int(self.pan_x) % major
            oy2 = int(self.pan_y) % major
            for x in range(ox2, self.width(), major):
                p.drawLine(x, 0, x, self.height())
            for y in range(oy2, self.height(), major):
                p.drawLine(0, y, self.width(), y)
            if not self.nodes:
                p.setPen(QColor(144, 162, 184))
                p.drawText(self.rect(), Qt.AlignCenter, "Node graph")
                return
            for lk in self.links:
                a, b = int(lk[0]), int(lk[1])
                op = int(lk[2]) if len(lk) >= 3 else 0
                ipt = int(lk[3]) if len(lk) >= 4 else 0
                if a < 0 or b < 0 or a >= len(self.nodes) or b >= len(self.nodes):
                    continue
                p1 = self._port_pos(a, "out", op)
                p2 = self._port_pos(b, "in", ipt)
                out_t = self._port_type(a, "out", op)
                col = self._port_color(out_t)
                path = QPainterPath()
                path.moveTo(p1)
                dx = max(46, abs(p2.x() - p1.x()) // 2)
                c1 = QPoint(p1.x() + dx, p1.y())
                c2 = QPoint(p2.x() - dx, p2.y())
                path.cubicTo(c1, c2, p2)
                p.setPen(QPen(col, 2))
                p.setBrush(Qt.NoBrush)
                p.drawPath(path)
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawEllipse(QPoint(p2.x(), p2.y()), 3, 3)
            if self._drag_link is not None:
                try:
                    src_idx = int(self._drag_link.get("src_idx", -1))
                    src_port = int(self._drag_link.get("src_port", 0))
                    if 0 <= src_idx < len(self.nodes):
                        p1 = self._port_pos(src_idx, "out", src_port)
                        p2 = QPoint(int(self._drag_link_pos.x()), int(self._drag_link_pos.y()))
                        out_t = self._port_type(src_idx, "out", src_port)
                        col = self._port_color(out_t)
                        path = QPainterPath()
                        path.moveTo(p1)
                        dx = max(46, abs(p2.x() - p1.x()) // 2)
                        c1 = QPoint(p1.x() + dx, p1.y())
                        c2 = QPoint(p2.x() - dx, p2.y())
                        path.cubicTo(c1, c2, p2)
                        p.setPen(QPen(col, 2, Qt.DashLine))
                        p.setBrush(Qt.NoBrush)
                        p.drawPath(path)
                except Exception:
                    pass
            drag_src_idx = -1
            drag_src_port = 0
            drag_out_t = "video"
            drag_hover = self._drag_link_hover_in if isinstance(self._drag_link_hover_in, dict) else None
            if self._drag_link is not None:
                try:
                    drag_src_idx = int(self._drag_link.get("src_idx", -1))
                    drag_src_port = int(self._drag_link.get("src_port", 0))
                    drag_out_t = self._port_type(drag_src_idx, "out", drag_src_port)
                except Exception:
                    drag_src_idx = -1
            for i, node in enumerate(self.nodes):
                r = self._node_rect(i)
                sel = (i == self._selected)
                src = (i == int(self._connect_src[0]))
                if src:
                    border = QColor(255, 210, 94, 232)
                    fill = QColor(66, 48, 18, 176)
                elif sel:
                    border = QColor(118, 198, 255, 240)
                    fill = QColor(30, 58, 94, 188)
                else:
                    border = QColor(86, 148, 214, 184)
                    fill = QColor(24, 36, 54, 176)
                p.setPen(QPen(border, 1.6))
                p.setBrush(QBrush(fill))
                p.drawRoundedRect(r, 9, 9)
                p.setPen(QColor(228, 238, 252))
                p.drawText(r.adjusted(8, 8, -8, -8), Qt.AlignLeft | Qt.AlignTop, f"[{i}]")
                p.drawText(r.adjusted(8, 0, -8, 0), Qt.AlignVCenter | Qt.AlignHCenter, node)
                p.setPen(Qt.NoPen)
                for ipt in range(self._port_count(i, "in")):
                    in_t = self._port_type(i, "in", ipt)
                    pp = self._port_pos(i, "in", ipt)
                    base_col = self._port_color(in_t)
                    p.setBrush(base_col)
                    p.drawEllipse(pp, 3, 3)
                    sel_port = (
                        isinstance(self._selected_port, dict)
                        and int(self._selected_port.get("idx", -1)) == int(i)
                        and str(self._selected_port.get("side", "")).strip().lower() == "in"
                        and int(self._selected_port.get("port", -1)) == int(ipt)
                    )
                    if sel_port:
                        p.setBrush(Qt.NoBrush)
                        p.setPen(QPen(QColor(236, 246, 255, 246), 1.6))
                        p.drawEllipse(pp, 6, 6)
                        p.setPen(Qt.NoPen)
                    if drag_src_idx >= 0:
                        comp = self._port_compatible(drag_out_t, in_t)
                        if i == drag_src_idx or self._would_cycle(drag_src_idx, i):
                            comp = False
                        hover = bool(
                            isinstance(drag_hover, dict)
                            and int(drag_hover.get("idx", -1)) == int(i)
                            and int(drag_hover.get("port", -1)) == int(ipt)
                        )
                        ring_col = QColor(100, 235, 148, 220) if comp else QColor(255, 118, 118, 220)
                        if hover:
                            ring_col = QColor(130, 255, 176, 245) if comp else QColor(255, 140, 140, 245)
                        p.setBrush(Qt.NoBrush)
                        p.setPen(QPen(ring_col, 1.6 if hover else 1.15))
                        p.drawEllipse(pp, 5 if hover else 4, 5 if hover else 4)
                        p.setPen(Qt.NoPen)
                    # Type badge near input port.
                    bb = QRect(pp.x() - 22, pp.y() - 7, 14, 12)
                    p.setPen(QPen(QColor(76, 102, 136, 220), 1))
                    p.setBrush(QColor(8, 12, 18, 214))
                    p.drawRoundedRect(bb, 3, 3)
                    p.setPen(base_col.lighter(130))
                    p.drawText(bb, Qt.AlignCenter, self._port_badge(in_t))
                    p.setPen(Qt.NoPen)
                for opt in range(self._port_count(i, "out")):
                    out_t = self._port_type(i, "out", opt)
                    pp = self._port_pos(i, "out", opt)
                    base_col = self._port_color(out_t)
                    p.setBrush(base_col)
                    p.drawEllipse(pp, 3, 3)
                    sel_port = (
                        isinstance(self._selected_port, dict)
                        and int(self._selected_port.get("idx", -1)) == int(i)
                        and str(self._selected_port.get("side", "")).strip().lower() == "out"
                        and int(self._selected_port.get("port", -1)) == int(opt)
                    )
                    if sel_port:
                        p.setBrush(Qt.NoBrush)
                        p.setPen(QPen(QColor(236, 246, 255, 246), 1.6))
                        p.drawEllipse(pp, 6, 6)
                        p.setPen(Qt.NoPen)
                    # Type badge near output port.
                    bb = QRect(pp.x() + 8, pp.y() - 7, 14, 12)
                    p.setPen(QPen(QColor(76, 102, 136, 220), 1))
                    p.setBrush(QColor(8, 12, 18, 214))
                    p.drawRoundedRect(bb, 3, 3)
                    p.setPen(base_col.lighter(130))
                    p.drawText(bb, Qt.AlignCenter, self._port_badge(out_t))
                    p.setPen(Qt.NoPen)
            p.setPen(QColor(170, 198, 226, 170))
            p.drawText(QRect(8, self.height() - 20, 320, 16), Qt.AlignLeft | Qt.AlignVCenter, f"Zoom: {self.zoom:.2f}x  (Ctrl+Wheel, MMB Pan)")
        finally:
            p.end()


class TimelineMiniView(QWidget):
    seekRequested = Signal(int)
    clipSelected = Signal(str, int)
    clipRangeChanged = Signal(str, int, int, int)
    clipSplitRequested = Signal(str, int, int)
    clipRippleDeleteRequested = Signal(str, int)
    clipKeyframeChanged = Signal(str, int, str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.duration_ms = 1000
        self.current_ms = 0
        self.text_layers = []
        self.media_layers = []
        self.selected_text = -1
        self.selected_media = -1
        self.audio_path = ""
        self.audio_bars = []
        self._audio_bars_key = ""
        self._drag_seek = False
        self._drag_clip = None
        self._drag_keyframe = None
        self._drag_pan = False
        self._pan_anchor_x = 0
        self._pan_anchor_ms = 0
        self.tool_mode = "select"
        self._hover_hit = None
        self.zoom_x = 1.0
        self.pan_ms = 0
        self._rows_meta = []
        self.setMinimumHeight(140)
        self.setMouseTracking(True)
        self._apply_timeline_cursor()

    def _build_audio_bars(self, path):
        path = str(path or "").strip()
        key = path.lower()
        if key == self._audio_bars_key and self.audio_bars:
            return
        self._audio_bars_key = key
        bars = []
        if path and os.path.exists(path) and path.lower().endswith(".wav"):
            try:
                with wave.open(path, "rb") as wf:
                    nframes = int(wf.getnframes())
                    nch = max(1, int(wf.getnchannels()))
                    sw = max(1, int(wf.getsampwidth()))
                    if nframes > 0:
                        chunk = max(1, nframes // 96)
                        pos = 0
                        while pos < nframes and len(bars) < 96:
                            wf.setpos(pos)
                            raw = wf.readframes(chunk)
                            if not raw:
                                break
                            if sw == 1:
                                vals = [abs(b - 128) / 128.0 for b in raw[: min(len(raw), 4096)]]
                            else:
                                step = sw
                                vals = []
                                lim = min(len(raw), 8192)
                                for i in range(0, lim - step + 1, step * nch):
                                    try:
                                        sample = int.from_bytes(raw[i:i + step], byteorder="little", signed=True)
                                        vals.append(abs(float(sample)) / float(2 ** (8 * sw - 1)))
                                    except Exception:
                                        continue
                            bars.append(max(vals) if vals else 0.0)
                            pos += chunk
            except Exception:
                bars = []
        if not bars:
            seed = hashlib.sha1(key.encode("utf-8", errors="ignore")).digest() if key else b"seed"
            vals = []
            for i in range(96):
                b = seed[i % len(seed)]
                vals.append(0.12 + (b / 255.0) * 0.86)
            bars = vals
        self.audio_bars = bars[:96]

    def set_data(self, duration_ms, current_ms, text_layers, media_layers, selected_text=-1, selected_media=-1, audio_path=""):
        self.duration_ms = max(1000, int(duration_ms or 1000))
        self.current_ms = max(0, min(self.duration_ms, int(current_ms or 0)))
        self.text_layers = [dict(x or {}) for x in (text_layers or [])]
        self.media_layers = [dict(x or {}) for x in (media_layers or [])]
        self.selected_text = int(selected_text) if selected_text is not None else -1
        self.selected_media = int(selected_media) if selected_media is not None else -1
        self.audio_path = str(audio_path or "")
        self._build_audio_bars(self.audio_path)
        self._clamp_view_pan()
        self.update()

    def _track_rect(self):
        return QRect(118, 18, max(10, self.width() - 130), max(10, self.height() - 26))

    def _view_bounds(self):
        z = max(1.0, min(12.0, float(self.zoom_x)))
        visible = max(300, int(round(float(self.duration_ms) / z)))
        visible = min(int(self.duration_ms), visible)
        max_pan = max(0, int(self.duration_ms) - int(visible))
        start = max(0, min(max_pan, int(self.pan_ms)))
        end = min(int(self.duration_ms), int(start + visible))
        return int(start), int(end)

    def _clamp_view_pan(self):
        v0, v1 = self._view_bounds()
        self.pan_ms = int(v0)
        if self.current_ms < v0:
            self.current_ms = int(v0)
        elif self.current_ms > v1:
            self.current_ms = int(v1)

    def set_current_ms(self, value):
        try:
            self.current_ms = max(0, min(int(self.duration_ms), int(value)))
            self._clamp_view_pan()
            self.update()
        except Exception:
            pass

    def seek_relative(self, delta_ms):
        try:
            self.set_current_ms(int(self.current_ms) + int(delta_ms))
        except Exception:
            pass

    def zoom_by(self, factor, anchor_ms=None):
        try:
            z = max(1.0, min(12.0, float(self.zoom_x)))
            f = float(factor)
            if f <= 0.0:
                return
            nz = max(1.0, min(12.0, z * f))
            if abs(nz - z) < 1e-4:
                return
            a_ms = int(self.current_ms if anchor_ms is None else anchor_ms)
            v0, v1 = self._view_bounds()
            span_old = max(1, int(v1 - v0))
            k = max(0.0, min(1.0, (float(a_ms) - float(v0)) / float(span_old)))
            self.zoom_x = nz
            span_new = max(300, int(round(float(self.duration_ms) / float(self.zoom_x))))
            span_new = min(int(self.duration_ms), span_new)
            self.pan_ms = int(round(float(a_ms) - k * float(span_new)))
            self._clamp_view_pan()
            self.update()
        except Exception:
            pass

    def _ms_to_x(self, ms):
        tr = self._track_rect()
        v0, v1 = self._view_bounds()
        span = max(1, int(v1 - v0))
        k = max(0.0, min(1.0, (float(ms) - float(v0)) / float(span)))
        return int(tr.left() + k * tr.width())

    def _x_to_ms(self, x):
        tr = self._track_rect()
        if tr.width() <= 1:
            return 0
        v0, v1 = self._view_bounds()
        span = max(1, int(v1 - v0))
        k = (float(x) - float(tr.left())) / float(tr.width())
        k = max(0.0, min(1.0, k))
        return int(round(float(v0) + k * float(span)))

    def _emit_seek(self, x):
        self.seekRequested.emit(int(self._x_to_ms(x)))

    def set_tool_mode(self, mode):
        m = str(mode or "select").strip().lower()
        if m not in ("select", "razor", "trim", "ripple"):
            m = "select"
        self.tool_mode = m
        self._apply_timeline_cursor()
        self.update()

    def _tool_cursor(self, mode):
        m = str(mode or "").strip().lower()
        if m == "select":
            return QCursor(Qt.ArrowCursor)
        if not hasattr(self, "_tool_cursor_cache"):
            self._tool_cursor_cache = {}
        if m in self._tool_cursor_cache:
            return self._tool_cursor_cache[m]
        pm = QPixmap(28, 28)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            # Crosshair base.
            p.setPen(QPen(QColor(232, 242, 255, 238), 1.4))
            p.drawLine(2, 14, 26, 14)
            p.drawLine(14, 2, 14, 26)
            if m == "razor":
                p.setPen(QPen(QColor(255, 118, 118, 238), 2.0))
                p.drawLine(8, 8, 20, 20)
                p.drawLine(20, 8, 8, 20)
            elif m == "trim":
                p.setPen(QPen(QColor(132, 214, 255, 238), 2.0))
                p.drawLine(8, 7, 8, 21)
                p.drawLine(20, 7, 20, 21)
                p.drawLine(8, 7, 11, 7)
                p.drawLine(17, 21, 20, 21)
            elif m == "ripple":
                p.setPen(QPen(QColor(120, 238, 160, 238), 2.0))
                p.drawArc(6, 9, 8, 10, 0 * 16, 180 * 16)
                p.drawArc(12, 9, 8, 10, 0 * 16, 180 * 16)
                p.drawArc(18, 9, 8, 10, 0 * 16, 180 * 16)
        finally:
            p.end()
        cur = QCursor(pm, 14, 14)
        self._tool_cursor_cache[m] = cur
        return cur

    def _apply_timeline_cursor(self):
        self.setCursor(self._tool_cursor(self.tool_mode))

    def _layer_keyframe_ms(self, layer):
        d = dict(layer or {})
        t0 = int(d.get("start_ms", 0) or 0)
        t1 = int(d.get("end_ms", self.duration_ms) or self.duration_ms)
        ki = int(d.get("anim_in_ms", t0) or t0)
        ko = int(d.get("anim_out_ms", t1) or t1)
        ki = max(t0, min(t1, ki))
        ko = max(ki, min(t1, ko))
        return ki, ko

    def _cubic_bezier_progress(self, t, x1, y1, x2, y2):
        tt = max(0.0, min(1.0, float(t)))
        ax = 3.0 * x1 - 3.0 * x2 + 1.0
        bx = -6.0 * x1 + 3.0 * x2
        cx = 3.0 * x1
        ay = 3.0 * y1 - 3.0 * y2 + 1.0
        by = -6.0 * y1 + 3.0 * y2
        cy = 3.0 * y1
        s = tt
        for _ in range(7):
            xs = ((ax * s + bx) * s + cx) * s
            dx = (3.0 * ax * s + 2.0 * bx) * s + cx
            if abs(dx) < 1e-6:
                break
            s2 = s - (xs - tt) / dx
            if s2 < 0.0 or s2 > 1.0:
                break
            s = s2
        lo = 0.0
        hi = 1.0
        for _ in range(10):
            xs = ((ax * s + bx) * s + cx) * s
            if xs < tt:
                lo = s
            else:
                hi = s
            s = (lo + hi) * 0.5
        ys = ((ay * s + by) * s + cy) * s
        return max(0.0, min(1.0, float(ys)))

    def _ease_curve_value(self, layer, k):
        kk = max(0.0, min(1.0, float(k)))
        ease = str((layer or {}).get("anim_ease", "linear") or "linear").strip().lower()
        if ease == "ease_in":
            return kk * kk
        if ease == "ease_out":
            return 1.0 - (1.0 - kk) * (1.0 - kk)
        if ease == "ease_in_out":
            if kk < 0.5:
                return 2.0 * kk * kk
            return 1.0 - ((-2.0 * kk + 2.0) ** 2) * 0.5
        if ease == "bezier":
            bz = (layer or {}).get("anim_bezier", [0.25, 0.1, 0.25, 1.0])
            if not isinstance(bz, (list, tuple)) or len(bz) < 4:
                bz = [0.25, 0.1, 0.25, 1.0]
            try:
                x1 = max(0.0, min(1.0, float(bz[0])))
                y1 = max(0.0, min(1.0, float(bz[1])))
                x2 = max(0.0, min(1.0, float(bz[2])))
                y2 = max(0.0, min(1.0, float(bz[3])))
            except Exception:
                x1, y1, x2, y2 = 0.25, 0.1, 0.25, 1.0
            return self._cubic_bezier_progress(kk, x1, y1, x2, y2)
        return kk

    def _hit_keyframe(self, pos):
        px = int(pos.x())
        py = int(pos.y())
        tol = 8
        for row in reversed(self._rows_meta):
            rc = row.get("rect")
            if rc is None:
                continue
            if py < rc.top() - 6 or py > rc.bottom() + 6:
                continue
            for key, xname in (("in", "kfi_x"), ("out", "kfo_x")):
                x = int(row.get(xname, -999999))
                if abs(px - x) <= tol:
                    return {
                        "kind": str(row.get("kind", "")),
                        "idx": int(row.get("idx", -1)),
                        "key": key,
                    }
        return None

    def _hit_clip(self, pos):
        px = int(pos.x())
        py = int(pos.y())
        for row in reversed(self._rows_meta):
            rc = row.get("rect")
            if rc is None or not rc.contains(px, py):
                continue
            x0 = int(row.get("x0", rc.left()))
            x1 = int(row.get("x1", rc.right()))
            tol = 6
            if abs(px - x0) <= tol:
                row["side"] = "start"
            elif abs(px - x1) <= tol:
                row["side"] = "end"
            else:
                row["side"] = "body"
            return row
        return None

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MiddleButton:
            self._drag_pan = True
            self._pan_anchor_x = int(ev.pos().x())
            self._pan_anchor_ms = int(self.pan_ms)
            ev.accept()
            return
        if ev.button() == Qt.LeftButton:
            kf = self._hit_keyframe(ev.pos())
            if kf is not None:
                self._drag_keyframe = dict(kf)
                kind = str(kf.get("kind", ""))
                idx = int(kf.get("idx", -1))
                if kind and idx >= 0:
                    self.clipSelected.emit(kind, idx)
                ev.accept()
                return
            hit = self._hit_clip(ev.pos())
            if hit is not None:
                kind = str(hit.get("kind", ""))
                idx = int(hit.get("idx", -1))
                if kind and idx >= 0:
                    self.clipSelected.emit(kind, idx)
                if self.tool_mode == "ripple":
                    if kind and idx >= 0:
                        self.clipRippleDeleteRequested.emit(kind, idx)
                        ev.accept()
                        return
                if self.tool_mode == "razor":
                    if kind and idx >= 0:
                        ms = int(self._x_to_ms(ev.pos().x()))
                        self.clipSplitRequested.emit(kind, idx, ms)
                        ev.accept()
                        return
                side = str(hit.get("side", "body"))
                if side in ("start", "end", "body"):
                    self._drag_clip = {
                        "kind": kind,
                        "idx": idx,
                        "side": side,
                        "start": int(hit.get("start", 0)),
                        "end": int(hit.get("end", self.duration_ms)),
                        "anchor_ms": int(self._x_to_ms(ev.pos().x())),
                    }
                    ev.accept()
                    return
                if self.tool_mode == "trim":
                    ev.accept()
                    return
            self._drag_seek = True
            self._emit_seek(ev.pos().x())
            ev.accept()
            return
        if ev.button() == Qt.RightButton:
            hit = self._hit_clip(ev.pos())
            if hit is not None:
                kind = str(hit.get("kind", ""))
                idx = int(hit.get("idx", -1))
                ms = int(self._x_to_ms(ev.pos().x()))
                if kind and idx >= 0:
                    self.clipSelected.emit(kind, idx)
                    self.clipSplitRequested.emit(kind, idx, ms)
                    ev.accept()
                    return
        return super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._drag_pan and (ev.buttons() & Qt.MiddleButton):
            tr = self._track_rect()
            if tr.width() > 1:
                dx = int(ev.pos().x() - self._pan_anchor_x)
                v0, v1 = self._view_bounds()
                visible = max(1, int(v1 - v0))
                delta_ms = int(round(float(dx) / float(tr.width()) * float(visible)))
                self.pan_ms = int(self._pan_anchor_ms - delta_ms)
                self._clamp_view_pan()
                self.update()
            ev.accept()
            return
        if self._drag_keyframe is not None and (ev.buttons() & Qt.LeftButton):
            ms = int(self._x_to_ms(ev.pos().x()))
            kind = str(self._drag_keyframe.get("kind", ""))
            idx = int(self._drag_keyframe.get("idx", -1))
            key = str(self._drag_keyframe.get("key", "in"))
            self.clipKeyframeChanged.emit(kind, idx, key, int(ms))
            ev.accept()
            return
        if self._drag_clip is not None and (ev.buttons() & Qt.LeftButton):
            ms = int(self._x_to_ms(ev.pos().x()))
            side = str(self._drag_clip.get("side", ""))
            kind = str(self._drag_clip.get("kind", ""))
            idx = int(self._drag_clip.get("idx", -1))
            t0 = int(self._drag_clip.get("start", 0))
            t1 = int(self._drag_clip.get("end", self.duration_ms))
            if side == "start":
                t0 = max(0, min(t1, ms))
            elif side == "end":
                t1 = max(t0, min(self.duration_ms, ms))
            elif side == "body":
                anchor = int(self._drag_clip.get("anchor_ms", t0))
                dt = int(ms - anchor)
                ln = max(1, int(t1 - t0))
                nt0 = int(t0 + dt)
                nt1 = int(t1 + dt)
                if nt0 < 0:
                    nt0 = 0
                    nt1 = ln
                if nt1 > int(self.duration_ms):
                    nt1 = int(self.duration_ms)
                    nt0 = max(0, nt1 - ln)
                t0, t1 = int(nt0), int(nt1)
            self.clipRangeChanged.emit(kind, idx, int(t0), int(t1))
            ev.accept()
            return
        if self._drag_seek and (ev.buttons() & Qt.LeftButton):
            self._emit_seek(ev.pos().x())
            ev.accept()
            return
        self._hover_hit = self._hit_clip(ev.pos())
        if self._hover_hit is not None and self.tool_mode in ("select", "trim"):
            side = str(self._hover_hit.get("side", "body"))
            if side in ("start", "end"):
                self.setCursor(Qt.SizeHorCursor)
            elif side == "body" and self.tool_mode == "select":
                self.setCursor(Qt.OpenHandCursor)
            elif self.tool_mode == "trim":
                self.setCursor(Qt.PointingHandCursor)
            else:
                self._apply_timeline_cursor()
        else:
            self._apply_timeline_cursor()
        return super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._drag_seek = False
        self._drag_clip = None
        self._drag_keyframe = None
        self._drag_pan = False
        self._apply_timeline_cursor()
        return super().mouseReleaseEvent(ev)

    def wheelEvent(self, ev):
        try:
            if bool(ev.modifiers() & Qt.ControlModifier):
                delta = int(ev.angleDelta().y())
                if delta == 0:
                    ev.accept()
                    return
                tr = self._track_rect()
                px = int(ev.position().x())
                anchor_ms = int(self._x_to_ms(px))
                old_zoom = max(1.0, min(12.0, float(self.zoom_x)))
                self.zoom_x = old_zoom * (1.12 if delta > 0 else (1.0 / 1.12))
                self.zoom_x = max(1.0, min(12.0, float(self.zoom_x)))
                k = 0.0
                if tr.width() > 1:
                    k = max(0.0, min(1.0, (float(px) - float(tr.left())) / float(tr.width())))
                visible = max(300, int(round(float(self.duration_ms) / float(self.zoom_x))))
                visible = min(int(self.duration_ms), visible)
                self.pan_ms = int(round(float(anchor_ms) - k * float(visible)))
                self._clamp_view_pan()
                self.update()
                ev.accept()
                return
        except Exception:
            pass
        return super().wheelEvent(ev)

    def paintEvent(self, _ev):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            p.fillRect(self.rect(), QColor(8, 12, 18, 220))
            tr = self._track_rect()
            p.setPen(QPen(QColor(84, 108, 138, 130), 1))
            p.setBrush(QColor(12, 20, 30, 190))
            p.drawRoundedRect(tr, 8, 8)

            v0, v1 = self._view_bounds()
            sec = max(1, int(round((v1 - v0) / 1000.0)))
            major_step = 1
            if sec > 30:
                major_step = 5
            if sec > 90:
                major_step = 10
            p.setPen(QPen(QColor(110, 144, 182, 120), 1))
            start_s = max(0, int(v0 // 1000))
            end_s = max(start_s, int((v1 + 999) // 1000))
            tick_start = start_s - (start_s % major_step)
            for s in range(tick_start, end_s + major_step + 1, major_step):
                if s < 0:
                    continue
                ms = int(s * 1000)
                x = self._ms_to_x(ms)
                if x < tr.left() - 2 or x > tr.right() + 2:
                    continue
                p.drawLine(x, tr.top(), x, tr.top() + 10)
                p.drawText(QRect(x - 18, 1, 44, 16), Qt.AlignLeft | Qt.AlignVCenter, f"{s}s")

            self._rows_meta = []
            row_h = 22
            y = tr.top() + 16
            rows = []
            for i, lyr in enumerate(self.text_layers):
                rows.append(("T", i, lyr))
            for i, lyr in enumerate(self.media_layers):
                rows.append(("M", i, lyr))
            max_rows = max(0, (tr.height() - 34) // row_h)
            for ridx, (kind, idx, lyr) in enumerate(rows[:max_rows]):
                ry = y + ridx * row_h
                t0 = int(lyr.get("start_ms", 0) or 0)
                t1 = int(lyr.get("end_ms", self.duration_ms) or self.duration_ms)
                t0 = max(0, min(self.duration_ms, t0))
                t1 = max(t0, min(self.duration_ms, t1))
                x0 = self._ms_to_x(t0)
                x1 = self._ms_to_x(t1)
                if x1 < tr.left() or x0 > tr.right():
                    continue
                x0 = max(tr.left(), min(tr.right(), x0))
                x1 = max(tr.left(), min(tr.right(), x1))
                selected = (kind == "T" and idx == self.selected_text) or (kind == "M" and idx == self.selected_media)
                kfi_ms, kfo_ms = self._layer_keyframe_ms(lyr)
                kfi_x = self._ms_to_x(kfi_ms)
                kfo_x = self._ms_to_x(kfo_ms)
                if kind == "T":
                    fill = QColor(70, 182, 240, 180 if selected else 124)
                    label = f"T{idx + 1}"
                else:
                    fill = QColor(246, 188, 88, 180 if selected else 124)
                    label = f"M{idx + 1}"
                rc = QRect(x0, ry, max(4, x1 - x0), row_h - 4)
                p.setPen(QPen(QColor(220, 234, 250, 150 if selected else 90), 1))
                p.setBrush(fill)
                p.drawRoundedRect(rc, 4, 4)
                p.setPen(QColor(226, 236, 248, 220))
                p.drawText(QRect(8, ry, 102, row_h - 4), Qt.AlignRight | Qt.AlignVCenter, label)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(234, 246, 255, 235))
                p.drawEllipse(QPoint(x0, ry + (row_h - 4) // 2), 3, 3)
                p.drawEllipse(QPoint(x1, ry + (row_h - 4) // 2), 3, 3)
                # In/Out keyframe markers (diamond style).
                for kmx, kcol in ((kfi_x, QColor(132, 230, 255, 236)), (kfo_x, QColor(255, 214, 128, 236))):
                    if kmx < tr.left() - 2 or kmx > tr.right() + 2:
                        continue
                    cy = ry + (row_h - 4) // 2
                    d = 5 if selected else 4
                    path = QPainterPath()
                    path.moveTo(kmx, cy - d)
                    path.lineTo(kmx + d, cy)
                    path.lineTo(kmx, cy + d)
                    path.lineTo(kmx - d, cy)
                    path.closeSubpath()
                    p.setPen(QPen(QColor(8, 12, 16, 210), 1))
                    p.setBrush(kcol)
                    p.drawPath(path)
                # Draw easing curve between in/out keyframes.
                if kfo_x - kfi_x >= 8:
                    py0 = int(ry + 4)
                    py1 = int(ry + row_h - 8)
                    curve = QPainterPath()
                    curve.moveTo(kfi_x, py1)
                    steps = max(8, min(36, (kfo_x - kfi_x) // 10))
                    for s in range(1, steps + 1):
                        kk = float(s) / float(steps)
                        ee = self._ease_curve_value(lyr, kk)
                        xx = int(round(kfi_x + (kfo_x - kfi_x) * kk))
                        yy = int(round(py1 - (py1 - py0) * ee))
                        curve.lineTo(xx, yy)
                    p.setPen(QPen(QColor(168, 198, 232, 170), 1))
                    p.setBrush(Qt.NoBrush)
                    p.drawPath(curve)
                self._rows_meta.append({
                    "kind": kind,
                    "idx": int(idx),
                    "start": int(t0),
                    "end": int(t1),
                    "x0": int(x0),
                    "x1": int(x1),
                    "kfi_x": int(kfi_x),
                    "kfo_x": int(kfo_x),
                    "rect": rc,
                })

            # Audio bars row.
            ay = tr.bottom() - 24
            p.setPen(QPen(QColor(108, 154, 202, 120), 1))
            p.drawLine(tr.left(), ay, tr.right(), ay)
            p.setBrush(QColor(90, 170, 255, 145))
            p.setPen(Qt.NoPen)
            bars = self.audio_bars or [0.3] * 64
            for i, v in enumerate(bars):
                ms0 = int(round(float(i) * float(self.duration_ms) / float(max(1, len(bars)))))
                ms1 = int(round(float(i + 1) * float(self.duration_ms) / float(max(1, len(bars)))))
                if ms1 < v0 or ms0 > v1:
                    continue
                x0 = self._ms_to_x(ms0)
                x1 = self._ms_to_x(ms1)
                bw = max(1, x1 - x0)
                x = x0
                h = max(1, int(16 * max(0.05, min(1.0, float(v)))))
                p.drawRect(x, ay - h, max(1, bw - 1), h)

            px = self._ms_to_x(self.current_ms)
            p.setPen(QPen(QColor(120, 232, 255, 220), 2))
            p.drawLine(px, tr.top(), px, tr.bottom())
            p.setBrush(QColor(120, 232, 255, 230))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPoint(px, tr.top() + 1), 4, 4)
            p.setPen(QColor(160, 188, 220, 170))
            p.drawText(
                QRect(10, self.height() - 18, self.width() - 20, 14),
                Qt.AlignRight | Qt.AlignVCenter,
                f"Mode {self.tool_mode} | Zoom {self.zoom_x:.2f}x | Ctrl+Wheel zoom | MMB pan",
            )
        finally:
            p.end()


class AdvancedEditorDialog(QDialog):
    def __init__(self, host, src_pil, state, duration_ms=6000, tr=None, embedded=False, photo_mode=False):
        super().__init__(host)
        self.host = host
        self.src = src_pil.convert("RGB")
        self.state = copy.deepcopy(state or {})
        self.tr = tr or {}
        self.embedded = bool(embedded)
        self.photo_mode = bool(photo_mode)
        self.duration_ms = max(1000, int(duration_ms or 6000))
        self.preview_meta = {"ox": 0, "oy": 0, "scale": 1.0, "dw": 1, "dh": 1}
        self.drag = {"mode": None, "kind": None, "handle": None, "start_ix": 0, "start_iy": 0, "rect": (0, 0, 1, 1), "layer": -1}
        self._guide_rects = {}
        self._preview_zoom = 1.0
        self._preview_pan_x = 0.0
        self._preview_pan_y = 0.0
        self._preview_pan_drag = False
        self._preview_pan_anchor = QPoint(0, 0)
        self._preview_pan_start = (0.0, 0.0)
        self._ui_lock = False
        self._full = False
        self._normal_geometry = None
        self._timeline_playing = False
        self._always_interactive = True
        self._photo_active_tool = "move"
        self._photo_paint_layer = None
        self._photo_paint_serialized = ""
        self._photo_paint_dirty = False
        self._photo_paint_stroking = False
        self._photo_last_paint_xy = None
        self._photo_brush_rgba = (236, 244, 255, 220)
        self._last_fast_render_ts = 0.0
        self._timeline_timer = QTimer(self)
        self._timeline_timer.setInterval(33 if not bool(photo_mode) else 41)
        self._timeline_timer.timeout.connect(self._timeline_tick)
        self._preview_render_timer = QTimer(self)
        self._preview_render_timer.setSingleShot(True)
        self._preview_render_timer.timeout.connect(self._render_preview_now)
        self._preview_rendering = False
        self._preview_render_pending = False
        self._preview_fast_hint = False
        self._node_preview_timer = QTimer(self)
        self._node_preview_timer.setSingleShot(True)
        self._node_preview_timer.timeout.connect(self._render_node_preview_now)
        self._node_preview_rendering = False
        self._last_preview_render_ts = 0.0
        self._preview_cache_key = ""
        self._preview_cache_img = None
        self._preview_zoom_target = float(self._preview_zoom)
        self._timeline_tool_mode = "select"
        self._ui_anims = []
        self._node_preview_last_sig = None
        self._node_preview_last_ts = 0.0
        self._explicit_close = False
        self._explicit_accept = False
        self._source_path = ""
        self._source_kind = "image"
        self._base_frame_cache = {}
        self._base_frame_cache_order = []
        self.layers_tab_ref = None
        self.crop_mask_tab_ref = None
        self.trim_tab_ref = None
        try:
            self._source_path = str(self.host._effective_source_path() or "")
        except Exception:
            self._source_path = ""
        self._source_kind = self._detect_media_type_from_path(self._source_path)

        self._normalize_state()
        self._build_ui()
        self._sync_from_state()
        self.installEventFilter(self)
        self._schedule_render_preview(0, fast=False)

    def _t(self, key, fallback):
        try:
            return str(self.tr.get(key, fallback))
        except Exception:
            return fallback

    def _normalize_state(self):
        s = self.state
        s.setdefault("enabled", False)
        s.setdefault("brightness", 100)
        s.setdefault("contrast", 100)
        s.setdefault("saturation", 100)
        s.setdefault("sharpness", 100)
        s.setdefault("hue", 0)
        s.setdefault("exposure", 0)
        s.setdefault("temperature", 0)
        s.setdefault("crop_enabled", False)
        s.setdefault("crop_x", 0)
        s.setdefault("crop_y", 0)
        s.setdefault("crop_w", self.src.width)
        s.setdefault("crop_h", self.src.height)
        s.setdefault("mask_enabled", False)
        s.setdefault("mask_x", 0)
        s.setdefault("mask_y", 0)
        s.setdefault("mask_w", self.src.width)
        s.setdefault("mask_h", self.src.height)
        s.setdefault("mask_use_image", False)
        s.setdefault("mask_image_path", "")
        s.setdefault("trim_enabled", False)
        s.setdefault("trim_start_ms", 0)
        s.setdefault("trim_end_ms", self.duration_ms)
        s.setdefault("audio_path", "")
        s.setdefault("audio_gain_db", 0.0)
        s.setdefault("audio_lowpass_hz", 0)
        s.setdefault("nodes_enabled", False)
        s.setdefault("nodes_preview", False)
        s.setdefault("nodes_code", "")
        s.setdefault("node_chain", [])
        s.setdefault("node_links", [])
        s.setdefault("node_params", [])
        s.setdefault("node_io", [])
        s.setdefault("ascii_bridge_enabled", False)
        s.setdefault("ascii_bridge_apply", False)
        s.setdefault("ascii_style", str(getattr(self.host, "style", "bw") or "bw"))
        s.setdefault("ascii_width", int(getattr(self.host, "width_chars", 120) or 120))
        s.setdefault("ascii_font_size", int(getattr(self.host, "font_size", 10) or 10))
        s.setdefault("ascii_charset", str(getattr(self.host, "ascii_chars", "") or ""))
        s.setdefault("ascii_fg_hex", str(getattr(self.host, "fg_hex", "#ffffff") or "#ffffff"))
        s.setdefault("ascii_bg_hex", str(getattr(self.host, "bg_hex", "#000000") or "#000000"))
        s.setdefault("ascii_pro_tools", bool(getattr(self.host, "pro_tools", False)))
        s.setdefault("ascii_pro_bloom", int(getattr(self.host, "pro_bloom", 0) or 0))
        s.setdefault("ascii_pro_vignette", int(getattr(self.host, "pro_vignette", 0) or 0))
        s.setdefault("ascii_pro_grain", int(getattr(self.host, "pro_grain", 0) or 0))
        s.setdefault("ascii_pro_chroma", int(getattr(self.host, "pro_chroma", 0) or 0))
        s.setdefault("ascii_pro_glitch", int(getattr(self.host, "pro_glitch", 0) or 0))
        s.setdefault("photo_paint_enabled", False)
        s.setdefault("photo_paint_opacity", 100)
        s.setdefault("photo_paint_png_b64", "")
        s.setdefault("photo_paint_hash", "")
        s.setdefault("photo_brush_size", 26)
        s.setdefault("photo_brush_opacity", 92)
        s.setdefault("photo_brush_color_rgba", [236, 244, 255, 220])
        s.setdefault("media_layers", [])
        s.setdefault("text_layers", [])

        s["trim_start_ms"] = max(0, min(self.duration_ms, int(s.get("trim_start_ms", 0) or 0)))
        te = int(s.get("trim_end_ms", self.duration_ms) or self.duration_ms)
        s["trim_end_ms"] = max(s["trim_start_ms"], min(self.duration_ms, te))
        s["ascii_style"] = str(s.get("ascii_style", "bw") or "bw")
        s["ascii_width"] = max(40, min(520, int(s.get("ascii_width", 120) or 120)))
        s["ascii_font_size"] = max(6, min(72, int(s.get("ascii_font_size", 10) or 10)))
        s["ascii_charset"] = str(s.get("ascii_charset", "") or "")
        s["ascii_fg_hex"] = str(s.get("ascii_fg_hex", "#ffffff") or "#ffffff")
        s["ascii_bg_hex"] = str(s.get("ascii_bg_hex", "#000000") or "#000000")
        s["ascii_pro_tools"] = bool(s.get("ascii_pro_tools", False))
        s["ascii_pro_bloom"] = max(0, min(100, int(s.get("ascii_pro_bloom", 0) or 0)))
        s["ascii_pro_vignette"] = max(0, min(100, int(s.get("ascii_pro_vignette", 0) or 0)))
        s["ascii_pro_grain"] = max(0, min(100, int(s.get("ascii_pro_grain", 0) or 0)))
        s["ascii_pro_chroma"] = max(0, min(24, int(s.get("ascii_pro_chroma", 0) or 0)))
        s["ascii_pro_glitch"] = max(0, min(100, int(s.get("ascii_pro_glitch", 0) or 0)))
        s["photo_paint_enabled"] = bool(s.get("photo_paint_enabled", False))
        s["photo_paint_opacity"] = max(0, min(100, int(s.get("photo_paint_opacity", 100) or 100)))
        s["photo_paint_hash"] = str(s.get("photo_paint_hash", "") or "")
        s["photo_brush_size"] = max(1, min(220, int(s.get("photo_brush_size", 26) or 26)))
        s["photo_brush_opacity"] = max(1, min(100, int(s.get("photo_brush_opacity", 92) or 92)))
        col = s.get("photo_brush_color_rgba", [236, 244, 255, 220])
        if not isinstance(col, (list, tuple)) or len(col) < 4:
            col = [236, 244, 255, 220]
        try:
            s["photo_brush_color_rgba"] = [
                max(0, min(255, int(col[0]))),
                max(0, min(255, int(col[1]))),
                max(0, min(255, int(col[2]))),
                max(0, min(255, int(col[3]))),
            ]
        except Exception:
            s["photo_brush_color_rgba"] = [236, 244, 255, 220]

        fixed_layers = []
        for i, layer in enumerate(s.get("text_layers", []) or []):
            d = self._default_layer(i)
            try:
                d.update(dict(layer))
            except Exception:
                pass
            d["start_ms"] = max(0, min(self.duration_ms, int(d.get("start_ms", 0) or 0)))
            d["end_ms"] = max(d["start_ms"], min(self.duration_ms, int(d.get("end_ms", self.duration_ms) or self.duration_ms)))
            ai = int(d.get("anim_in_ms", d["start_ms"]) or d["start_ms"])
            ao = int(d.get("anim_out_ms", d["end_ms"]) or d["end_ms"])
            d["anim_in_ms"] = max(d["start_ms"], min(d["end_ms"], ai))
            d["anim_out_ms"] = max(d["anim_in_ms"], min(d["end_ms"], ao))
            ease = str(d.get("anim_ease", "linear") or "linear").strip().lower()
            if ease not in ("linear", "ease_in", "ease_out", "ease_in_out", "bezier"):
                ease = "linear"
            d["anim_ease"] = ease
            bz = d.get("anim_bezier", [0.25, 0.1, 0.25, 1.0])
            if not isinstance(bz, (list, tuple)) or len(bz) < 4:
                bz = [0.25, 0.1, 0.25, 1.0]
            try:
                bx1 = max(0.0, min(1.0, float(bz[0])))
                by1 = max(0.0, min(1.0, float(bz[1])))
                bx2 = max(0.0, min(1.0, float(bz[2])))
                by2 = max(0.0, min(1.0, float(bz[3])))
            except Exception:
                bx1, by1, bx2, by2 = 0.25, 0.1, 0.25, 1.0
            d["anim_bezier"] = [bx1, by1, bx2, by2]
            d["scale_x"] = max(0.1, min(8.0, float(d.get("scale_x", 1.0) or 1.0)))
            d["scale_y"] = max(0.1, min(8.0, float(d.get("scale_y", 1.0) or 1.0)))
            fixed_layers.append(d)
        s["text_layers"] = fixed_layers
        fixed_media = []
        for i, layer in enumerate(s.get("media_layers", []) or []):
            d = self._default_media_layer(i)
            try:
                d.update(dict(layer))
            except Exception:
                pass
            d["start_ms"] = max(0, min(self.duration_ms, int(d.get("start_ms", 0) or 0)))
            d["end_ms"] = max(d["start_ms"], min(self.duration_ms, int(d.get("end_ms", self.duration_ms) or self.duration_ms)))
            ai = int(d.get("anim_in_ms", d["start_ms"]) or d["start_ms"])
            ao = int(d.get("anim_out_ms", d["end_ms"]) or d["end_ms"])
            d["anim_in_ms"] = max(d["start_ms"], min(d["end_ms"], ai))
            d["anim_out_ms"] = max(d["anim_in_ms"], min(d["end_ms"], ao))
            ease = str(d.get("anim_ease", "linear") or "linear").strip().lower()
            if ease not in ("linear", "ease_in", "ease_out", "ease_in_out", "bezier"):
                ease = "linear"
            d["anim_ease"] = ease
            bz = d.get("anim_bezier", [0.25, 0.1, 0.25, 1.0])
            if not isinstance(bz, (list, tuple)) or len(bz) < 4:
                bz = [0.25, 0.1, 0.25, 1.0]
            try:
                bx1 = max(0.0, min(1.0, float(bz[0])))
                by1 = max(0.0, min(1.0, float(bz[1])))
                bx2 = max(0.0, min(1.0, float(bz[2])))
                by2 = max(0.0, min(1.0, float(bz[3])))
            except Exception:
                bx1, by1, bx2, by2 = 0.25, 0.1, 0.25, 1.0
            d["anim_bezier"] = [bx1, by1, bx2, by2]
            d["scale_x"] = max(0.05, min(8.0, float(d.get("scale_x", 1.0) or 1.0)))
            d["scale_y"] = max(0.05, min(8.0, float(d.get("scale_y", 1.0) or 1.0)))
            d["speed"] = max(0.05, min(16.0, float(d.get("speed", 1.0) or 1.0)))
            d["alpha"] = max(0, min(255, int(d.get("alpha", 255) or 255)))
            d["blend"] = str(d.get("blend", "normal") or "normal")
            fixed_media.append(d)
        s["media_layers"] = fixed_media
        fixed_links = []
        n = len(s.get("node_chain", []) or [])
        for link in (s.get("node_links", []) or []):
            try:
                if isinstance(link, dict):
                    a = int(link.get("src", -1))
                    b = int(link.get("dst", -1))
                    op = int(link.get("src_port", 0))
                    ip = int(link.get("dst_port", 0))
                elif isinstance(link, (list, tuple)) and len(link) >= 4:
                    a, b, op, ip = int(link[0]), int(link[1]), int(link[2]), int(link[3])
                else:
                    a, b = int(link[0]), int(link[1])
                    op, ip = 0, 0
            except Exception:
                continue
            if a == b or a < 0 or b < 0 or a >= n or b >= n:
                continue
            item = [a, b, max(0, int(op)), max(0, int(ip))]
            if item not in fixed_links:
                fixed_links.append(item)
        s["node_links"] = fixed_links
        params = []
        raw_params = s.get("node_params", []) or []
        node_io = []
        raw_io = s.get("node_io", []) or []
        for i, nid in enumerate(s.get("node_chain", []) or []):
            d = self._default_node_params(nid)
            try:
                if i < len(raw_params) and isinstance(raw_params[i], dict):
                    d.update(raw_params[i])
            except Exception:
                pass
            d["enabled"] = bool(d.get("enabled", True))
            d["intensity"] = max(0, min(100, int(d.get("intensity", 55) or 55)))
            d["radius"] = max(0, min(32, int(d.get("radius", 2) or 2)))
            d["mix"] = max(0, min(100, int(d.get("mix", 100) or 100)))
            d["value"] = max(-200, min(200, int(d.get("value", 0) or 0)))
            d["seed"] = max(0, min(9999, int(d.get("seed", 0) or 0)))
            params.append(d)
            io = dict(self._default_node_io(nid))
            if i < len(raw_io) and isinstance(raw_io[i], dict):
                try:
                    io["inputs"] = max(1, min(8, int(raw_io[i].get("inputs", 1) or 1)))
                    io["outputs"] = max(1, min(8, int(raw_io[i].get("outputs", 1) or 1)))
                except Exception:
                    pass
                in_types = raw_io[i].get("in_types", raw_io[i].get("input_type", io.get("in_types", ["video"])))
                out_types = raw_io[i].get("out_types", raw_io[i].get("output_type", io.get("out_types", ["video"])))
                if not isinstance(in_types, list):
                    in_types = [in_types]
                if not isinstance(out_types, list):
                    out_types = [out_types]
                in_norm = []
                out_norm = []
                for t in in_types:
                    tv = str(t or "").strip().lower()
                    if tv not in ("video", "audio", "data", "any"):
                        tv = "video"
                    in_norm.append(tv)
                for t in out_types:
                    tv = str(t or "").strip().lower()
                    if tv not in ("video", "audio", "data", "any"):
                        tv = "video"
                    out_norm.append(tv)
                if not in_norm:
                    in_norm = [str(io.get("in_types", ["video"])[0])]
                if not out_norm:
                    out_norm = [str(io.get("out_types", ["video"])[0])]
                while len(in_norm) < int(io["inputs"]):
                    in_norm.append(in_norm[-1])
                while len(out_norm) < int(io["outputs"]):
                    out_norm.append(out_norm[-1])
                io["in_types"] = in_norm[: int(io["inputs"])]
                io["out_types"] = out_norm[: int(io["outputs"])]
            else:
                in_norm = [str(x).strip().lower() for x in (io.get("in_types", ["video"]) or ["video"])]
                out_norm = [str(x).strip().lower() for x in (io.get("out_types", ["video"]) or ["video"])]
                while len(in_norm) < int(io["inputs"]):
                    in_norm.append(in_norm[-1])
                while len(out_norm) < int(io["outputs"]):
                    out_norm.append(out_norm[-1])
                io["in_types"] = in_norm[: int(io["inputs"])]
                io["out_types"] = out_norm[: int(io["outputs"])]
            io["input_type"] = str(io.get("in_types", ["video"])[0])
            io["output_type"] = str(io.get("out_types", ["video"])[0])
            node_io.append(io)
        s["node_params"] = params
        s["node_io"] = node_io

    def _default_layer(self, idx):
        px = max(0, int(self.src.width * 0.08))
        py = max(0, int(self.src.height * 0.08))
        return {
            "enabled": True,
            "text": f"Layer {idx + 1}",
            "font": "Arial",
            "size": 36,
            "x": px,
            "y": py,
            "x1": px,
            "y1": py,
            "start_ms": 0,
            "end_ms": self.duration_ms,
            "anim_in_ms": 0,
            "anim_out_ms": self.duration_ms,
            "anim_ease": "linear",
            "anim_bezier": [0.25, 0.1, 0.25, 1.0],
            "scale_x": 1.0,
            "scale_y": 1.0,
            "color_rgba": (255, 255, 255, 220),
        }

    def _default_media_layer(self, idx):
        px = max(0, int(self.src.width * 0.08))
        py = max(0, int(self.src.height * 0.08))
        return {
            "enabled": True,
            "path": "",
            "type": "image",
            "x": px,
            "y": py,
            "x1": px,
            "y1": py,
            "scale_x": 1.0,
            "scale_y": 1.0,
            "alpha": 255,
            "start_ms": 0,
            "end_ms": self.duration_ms,
            "anim_in_ms": 0,
            "anim_out_ms": self.duration_ms,
            "anim_ease": "linear",
            "anim_bezier": [0.25, 0.1, 0.25, 1.0],
            "speed": 1.0,
            "blend": "normal",
        }

    def _default_node_params(self, node_id):
        nid = str(node_id or "").strip().lower()
        base = {"enabled": True, "intensity": 55, "radius": 2, "mix": 100, "value": 0, "seed": 0}
        if nid == "blur":
            base["intensity"] = 62
            base["radius"] = 3
        elif nid == "brightness-node":
            base["intensity"] = 52
            base["value"] = 8
        elif nid == "contrast-node":
            base["intensity"] = 56
            base["value"] = 12
        elif nid == "saturation-node":
            base["intensity"] = 60
            base["value"] = 10
        elif nid == "hue-shift":
            base["intensity"] = 50
            base["value"] = 18
        elif nid == "gamma-node":
            base["intensity"] = 50
            base["value"] = 0
        elif nid == "autocontrast":
            base["intensity"] = 68
        elif nid == "equalize":
            base["intensity"] = 66
        elif nid == "grayscale":
            base["intensity"] = 100
        elif nid == "solarize":
            base["intensity"] = 46
            base["value"] = 0
        elif nid == "pixelate":
            base["intensity"] = 38
            base["radius"] = 3
        elif nid == "median-denoise":
            base["intensity"] = 54
            base["radius"] = 2
        elif nid == "motion-blur":
            base["intensity"] = 42
            base["radius"] = 4
        elif nid == "sharpen":
            base["intensity"] = 48
            base["radius"] = 2
        elif nid == "edge":
            base["intensity"] = 56
            base["radius"] = 1
        elif nid == "posterize":
            base["intensity"] = 44
            base["radius"] = 1
        elif nid == "invert":
            base["intensity"] = 100
            base["radius"] = 1
        elif nid == "emboss":
            base["intensity"] = 55
            base["radius"] = 2
        elif nid == "glitch-lite":
            base["intensity"] = 40
            base["radius"] = 2
        elif nid == "vignette":
            base["intensity"] = 46
            base["radius"] = 2
        elif nid == "bloom-lite":
            base["intensity"] = 52
            base["radius"] = 3
        elif nid == "threshold":
            base["intensity"] = 48
            base["radius"] = 1
        elif nid == "noise":
            base["intensity"] = 34
            base["radius"] = 1
        elif nid == "channel-shift":
            base["intensity"] = 50
            base["radius"] = 2
        base["mix"] = max(0, min(100, int(base.get("mix", 100))))
        base["value"] = max(-200, min(200, int(base.get("value", 0))))
        base["seed"] = max(0, min(9999, int(base.get("seed", 0))))
        return base

    def _default_node_io(self, node_id):
        nid = str(node_id or "").strip().lower()
        video_nodes = {
            "video-in", "video-out", "brightness-node", "contrast-node", "saturation-node", "hue-shift",
            "gamma-node", "autocontrast", "equalize", "blur", "sharpen", "median-denoise", "motion-blur",
            "edge", "emboss", "posterize", "invert", "grayscale", "solarize", "pixelate", "glitch-lite",
            "vignette", "bloom-lite", "threshold", "noise", "channel-shift", "bypass",
        }
        if nid in ("audio-in", "audio-gain", "audio-lowpass"):
            return {"inputs": 1, "outputs": 1, "in_types": ["audio"], "out_types": ["audio"]}
        if nid == "audio-analyzer":
            return {"inputs": 1, "outputs": 1, "in_types": ["audio"], "out_types": ["data"]}
        if nid in ("value-node", "math-add", "switch-node", "if-node"):
            return {"inputs": 1, "outputs": 1, "in_types": ["data"], "out_types": ["data"]}
        if nid == "python-script":
            return {"inputs": 1, "outputs": 1, "in_types": ["any"], "out_types": ["any"]}
        if nid in video_nodes:
            return {"inputs": 1, "outputs": 1, "in_types": ["video"], "out_types": ["video"]}
        return {"inputs": 1, "outputs": 1, "in_types": ["video"], "out_types": ["video"]}

    def _slider_with_value(self, min_v, max_v, val):
        sl = QSlider(Qt.Horizontal)
        sl.setRange(int(min_v), int(max_v))
        sl.setValue(int(max(min_v, min(max_v, int(val)))))
        lbl = QLabel(str(sl.value()))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(sl, 1)
        row.addWidget(lbl)
        sl.valueChanged.connect(lambda v, x=lbl: x.setText(str(int(v))))
        return sl, row

    def _clamp_rect(self, x, y, w, h):
        w = max(1, int(w))
        h = max(1, int(h))
        x = max(0, min(self.src.width - 1, int(x)))
        y = max(0, min(self.src.height - 1, int(y)))
        if x + w > self.src.width:
            w = self.src.width - x
        if y + h > self.src.height:
            h = self.src.height - y
        return int(x), int(y), max(1, int(w)), max(1, int(h))

    def _detect_media_type_from_path(self, path):
        low = str(path or "").strip().lower()
        if low.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm")):
            return "video"
        if low.endswith(".gif"):
            return "gif"
        return "image"

    def _source_frame_for_time(self, t_ms, fast=False):
        try:
            if bool(self.photo_mode):
                return self.src.copy()
            p = str(getattr(self, "_source_path", "") or "").strip()
            if (not p or (not os.path.exists(p))) and hasattr(self.host, "_effective_source_path"):
                p = str(self.host._effective_source_path() or "").strip()
                self._source_path = p
            if not p or (not os.path.exists(p)):
                return self.src.copy()
            kind = self._detect_media_type_from_path(p)
            self._source_kind = kind
            if kind == "image":
                return self.src.copy()
            bucket = 90 if bool(fast) else 48
            key = (p, kind, int(max(0, int(t_ms)) // max(1, bucket)))
            cache = self._base_frame_cache if isinstance(getattr(self, "_base_frame_cache", None), dict) else None
            if cache is not None and key in cache and isinstance(cache[key], Image.Image):
                try:
                    return cache[key].copy()
                except Exception:
                    return cache[key]
            frame = None
            if kind == "video" and hasattr(self.host, "_get_video_frame_at_ms"):
                try:
                    frame = self.host._get_video_frame_at_ms(p, int(max(0, int(t_ms))))
                except Exception:
                    frame = None
            if frame is None and hasattr(self.host, "_load_media_layer_frame"):
                try:
                    frame = self.host._load_media_layer_frame({"path": p, "type": kind}, int(max(0, int(t_ms))))
                except Exception:
                    frame = None
            if frame is None and hasattr(self.host, "_get_first_frame"):
                try:
                    frame = self.host._get_first_frame(p)
                except Exception:
                    frame = None
            if frame is None:
                frame = self.src.copy()
            frame = frame.convert("RGB")
            if cache is not None:
                cache[key] = frame.copy()
                self._base_frame_cache_order.append(key)
                if len(self._base_frame_cache_order) > 24:
                    old = self._base_frame_cache_order.pop(0)
                    cache.pop(old, None)
            return frame.copy()
        except Exception:
            try:
                return self.src.copy()
            except Exception:
                return self.src

    def _active_interaction_mode(self):
        if bool(getattr(self, "photo_mode", False)):
            try:
                tool = str(getattr(self, "_photo_active_tool", "move") or "move").strip().lower()
                if tool in ("marquee", "crop"):
                    return "crop"
                if tool in ("lasso", "mask"):
                    return "mask"
                if tool in ("brush", "eraser"):
                    return "off"
                if tool == "text":
                    return "text"
                if tool == "move":
                    med, _ = self._selected_media_layer()
                    if med is not None:
                        return "media"
                    lyr, _ = self._selected_layer()
                    if lyr is not None:
                        return "text"
            except Exception:
                pass
        if not bool(getattr(self, "_always_interactive", False)):
            return str(self.mode_combo.currentData() or "off")
        try:
            cw = self.tabs.currentWidget() if hasattr(self, "tabs") else None
            if cw is getattr(self, "crop_mask_tab_ref", None):
                if bool(self.mask_enable.isChecked()) or bool(self.mask_use_image_chk.isChecked()):
                    return "mask"
                return "crop"
            if cw is getattr(self, "layers_tab_ref", None):
                med, _ = self._selected_media_layer()
                if med is not None:
                    return "media"
                lyr, _ = self._selected_layer()
                if lyr is not None:
                    return "text"
        except Exception:
            pass
        try:
            k, _, _ = self._selected_clip_ref()
            if k == "M":
                return "media"
            if k == "T":
                return "text"
            if bool(self.crop_enable.isChecked()):
                return "crop"
            if bool(self.mask_enable.isChecked()) or bool(self.mask_use_image_chk.isChecked()):
                return "mask"
        except Exception:
            pass
        return "off"

    def _set_color_btn(self, btn, rgba):
        try:
            r, g, b, a = int(rgba[0]), int(rgba[1]), int(rgba[2]), int(rgba[3])
        except Exception:
            r, g, b, a = 255, 255, 255, 220
        css = self.host._glass_btn_css() + f"QPushButton{{background: rgba({r},{g},{b},{max(60, min(255, a))}); color:#111;}}"
        btn.setStyleSheet(css)

    def _ensure_photo_paint_layer(self):
        if not bool(self.photo_mode):
            return None
        try:
            sw = int(self.src.width)
            sh = int(self.src.height)
        except Exception:
            sw, sh = 1, 1
        layer = getattr(self, "_photo_paint_layer", None)
        if layer is None:
            self._photo_paint_layer = Image.new("RGBA", (max(1, sw), max(1, sh)), (0, 0, 0, 0))
        else:
            try:
                if layer.size != (max(1, sw), max(1, sh)):
                    self._photo_paint_layer = layer.resize((max(1, sw), max(1, sh)), Image.Resampling.LANCZOS)
            except Exception:
                self._photo_paint_layer = Image.new("RGBA", (max(1, sw), max(1, sh)), (0, 0, 0, 0))
        return self._photo_paint_layer

    def _decode_photo_paint_layer(self, payload_b64):
        data = str(payload_b64 or "").strip()
        if not data:
            return None
        try:
            raw = base64.b64decode(data.encode("ascii"), validate=False)
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            if img.size != self.src.size:
                img = img.resize(self.src.size, Image.Resampling.LANCZOS)
            return img
        except Exception:
            return None

    def _load_photo_paint_state(self):
        if not bool(self.photo_mode):
            return
        st = self.state if isinstance(self.state, dict) else {}
        payload = str(st.get("photo_paint_png_b64", "") or "")
        if payload != str(getattr(self, "_photo_paint_serialized", "")):
            self._photo_paint_layer = self._decode_photo_paint_layer(payload)
            self._photo_paint_serialized = payload
            self._photo_paint_dirty = False
        try:
            bcol = st.get("photo_brush_color_rgba", [236, 244, 255, 220])
            if isinstance(bcol, (list, tuple)) and len(bcol) >= 4:
                self._photo_brush_rgba = (
                    max(0, min(255, int(bcol[0]))),
                    max(0, min(255, int(bcol[1]))),
                    max(0, min(255, int(bcol[2]))),
                    max(0, min(255, int(bcol[3]))),
                )
        except Exception:
            self._photo_brush_rgba = (236, 244, 255, 220)
        try:
            if hasattr(self, "photo_paint_enable_chk"):
                self.photo_paint_enable_chk.setChecked(bool(st.get("photo_paint_enabled", False)))
            if hasattr(self, "photo_brush_size_slider"):
                self.photo_brush_size_slider.setValue(int(st.get("photo_brush_size", self.photo_brush_size_slider.value())))
            if hasattr(self, "photo_brush_opacity_slider"):
                self.photo_brush_opacity_slider.setValue(int(st.get("photo_brush_opacity", self.photo_brush_opacity_slider.value())))
            if hasattr(self, "photo_paint_opacity_slider"):
                self.photo_paint_opacity_slider.setValue(int(st.get("photo_paint_opacity", self.photo_paint_opacity_slider.value())))
            if hasattr(self, "photo_brush_color_btn"):
                self._set_color_btn(self.photo_brush_color_btn, self._photo_brush_rgba)
        except Exception:
            pass

    def _commit_photo_paint_state(self):
        if not bool(self.photo_mode):
            return
        st = self.state if isinstance(self.state, dict) else {}
        if not isinstance(st, dict):
            return
        try:
            st["photo_paint_enabled"] = bool(self.photo_paint_enable_chk.isChecked()) if hasattr(self, "photo_paint_enable_chk") else bool(st.get("photo_paint_enabled", False))
            st["photo_paint_opacity"] = int(self.photo_paint_opacity_slider.value()) if hasattr(self, "photo_paint_opacity_slider") else int(st.get("photo_paint_opacity", 100))
            st["photo_brush_size"] = int(self.photo_brush_size_slider.value()) if hasattr(self, "photo_brush_size_slider") else int(st.get("photo_brush_size", 26))
            st["photo_brush_opacity"] = int(self.photo_brush_opacity_slider.value()) if hasattr(self, "photo_brush_opacity_slider") else int(st.get("photo_brush_opacity", 92))
            st["photo_brush_color_rgba"] = [
                int(self._photo_brush_rgba[0]),
                int(self._photo_brush_rgba[1]),
                int(self._photo_brush_rgba[2]),
                int(self._photo_brush_rgba[3]),
            ]
        except Exception:
            pass
        layer = getattr(self, "_photo_paint_layer", None)
        if layer is None:
            st["photo_paint_png_b64"] = ""
            st["photo_paint_hash"] = ""
            self._photo_paint_serialized = ""
            self._photo_paint_dirty = False
            return
        try:
            if layer.getbbox() is None:
                st["photo_paint_png_b64"] = ""
                st["photo_paint_hash"] = ""
                self._photo_paint_serialized = ""
                self._photo_paint_dirty = False
                return
        except Exception:
            pass
        try:
            buf = io.BytesIO()
            layer.save(buf, format="PNG", optimize=True)
            raw = buf.getvalue()
            payload = base64.b64encode(raw).decode("ascii")
            st["photo_paint_png_b64"] = payload
            st["photo_paint_hash"] = hashlib.sha1(raw).hexdigest()
            self._photo_paint_serialized = payload
        except Exception:
            st["photo_paint_png_b64"] = ""
            st["photo_paint_hash"] = ""
            self._photo_paint_serialized = ""
        self._photo_paint_dirty = False

    def _apply_photo_paint_overlay(self, pil_img, state_hint=None):
        if not bool(self.photo_mode):
            return pil_img
        st = state_hint if isinstance(state_hint, dict) else self.state
        if not isinstance(st, dict):
            return pil_img
        enabled = bool(st.get("photo_paint_enabled", False))
        opacity = max(0, min(100, int(st.get("photo_paint_opacity", 100) or 100)))
        if not enabled or opacity <= 0:
            return pil_img
        layer = getattr(self, "_photo_paint_layer", None)
        if layer is None:
            layer = self._decode_photo_paint_layer(st.get("photo_paint_png_b64", ""))
            self._photo_paint_layer = layer
        if layer is None:
            return pil_img
        try:
            if layer.size != pil_img.size:
                layer = layer.resize(pil_img.size, Image.Resampling.LANCZOS)
        except Exception:
            return pil_img
        ov = layer.copy()
        if opacity < 100:
            try:
                a = np.array(ov.split()[-1], dtype=np.float32)
                a *= float(opacity) / 100.0
                ov.putalpha(np.clip(a, 0, 255).astype(np.uint8))
            except Exception:
                pass
        base = pil_img.convert("RGBA")
        try:
            base.alpha_composite(ov)
        except Exception:
            return pil_img
        return base.convert("RGB")

    def _paint_photo_stroke(self, x0, y0, x1, y1):
        if not bool(self.photo_mode):
            return
        layer = self._ensure_photo_paint_layer()
        if layer is None:
            return
        tool = str(getattr(self, "_photo_active_tool", "move") or "move").strip().lower()
        if tool not in ("brush", "eraser"):
            return
        size = int(self.photo_brush_size_slider.value()) if hasattr(self, "photo_brush_size_slider") else int(self.state.get("photo_brush_size", 26))
        size = max(1, min(220, int(size)))
        op = int(self.photo_brush_opacity_slider.value()) if hasattr(self, "photo_brush_opacity_slider") else int(self.state.get("photo_brush_opacity", 92))
        op = max(1, min(100, int(op)))
        color = tuple(int(v) for v in getattr(self, "_photo_brush_rgba", (236, 244, 255, 220)))
        if tool == "eraser":
            draw_rgba = (0, 0, 0, 0)
        else:
            draw_rgba = (color[0], color[1], color[2], max(0, min(255, int(color[3] * (op / 100.0)))))
        x0 = max(0, min(int(layer.width - 1), int(x0)))
        y0 = max(0, min(int(layer.height - 1), int(y0)))
        x1 = max(0, min(int(layer.width - 1), int(x1)))
        y1 = max(0, min(int(layer.height - 1), int(y1)))
        d = ImageDraw.Draw(layer, "RGBA")
        if x0 == x1 and y0 == y1:
            rr = max(1, int(size // 2))
            d.ellipse((x0 - rr, y0 - rr, x0 + rr, y0 + rr), fill=draw_rgba)
        else:
            d.line((x0, y0, x1, y1), fill=draw_rgba, width=int(size), joint="curve")
            rr = max(1, int(size // 2))
            d.ellipse((x0 - rr, y0 - rr, x0 + rr, y0 + rr), fill=draw_rgba)
            d.ellipse((x1 - rr, y1 - rr, x1 + rr, y1 + rr), fill=draw_rgba)
        self._photo_paint_dirty = True
        self.state["photo_paint_enabled"] = True

    def _pick_photo_brush_color(self):
        if not bool(self.photo_mode):
            return
        col = QColorDialog.getColor(QColor(*self._photo_brush_rgba), self, self._t("text_color", "Brush color"))
        if not col.isValid():
            return
        self._photo_brush_rgba = (col.red(), col.green(), col.blue(), col.alpha())
        self.state["photo_brush_color_rgba"] = list(self._photo_brush_rgba)
        if hasattr(self, "photo_brush_color_btn"):
            self._set_color_btn(self.photo_brush_color_btn, self._photo_brush_rgba)
        self._schedule_render_preview(0, fast=True)

    def _clear_photo_paint_layer(self):
        if not bool(self.photo_mode):
            return
        self._photo_paint_layer = Image.new("RGBA", self.src.size, (0, 0, 0, 0))
        self._photo_paint_dirty = True
        self._commit_photo_paint_state()
        self._schedule_render_preview(0, fast=True)

    def result_state(self, include_photo_blob=True):
        if bool(self.photo_mode):
            try:
                if bool(include_photo_blob) and bool(getattr(self, "_photo_paint_dirty", False)) and not bool(getattr(self, "_photo_paint_stroking", False)):
                    self._commit_photo_paint_state()
            except Exception:
                pass
        out = copy.deepcopy(self.state)
        if bool(self.photo_mode) and (not bool(include_photo_blob)):
            out["photo_paint_png_b64"] = ""
            out["photo_paint_hash"] = ""
        has_layers = any(bool(str((ly or {}).get("text", "")).strip()) for ly in (out.get("text_layers", []) or []))
        has_media = any(bool(str((ly or {}).get("path", "")).strip()) and bool((ly or {}).get("enabled", True)) for ly in (out.get("media_layers", []) or []))
        has_photo_paint = bool(out.get("photo_paint_enabled", False)) and bool(str(out.get("photo_paint_png_b64", "") or "").strip())
        defaults_changed = (
            int(out.get("brightness", 100)) != 100
            or int(out.get("contrast", 100)) != 100
            or int(out.get("saturation", 100)) != 100
            or int(out.get("sharpness", 100)) != 100
            or int(out.get("hue", 0)) != 0
            or int(out.get("exposure", 0)) != 0
            or int(out.get("temperature", 0)) != 0
        )
        out["enabled"] = bool(
            defaults_changed
            or bool(out.get("crop_enabled", False))
            or bool(out.get("mask_enabled", False))
            or (bool(out.get("mask_use_image", False)) and bool(str(out.get("mask_image_path", "") or "").strip()))
            or bool(out.get("trim_enabled", False))
            or bool(out.get("nodes_enabled", False))
            or bool(out.get("audio_path", ""))
            or bool(out.get("ascii_bridge_apply", False))
            or has_media
            or has_layers
            or has_photo_paint
        )
        return out

    def _build_ui(self):
        self.setWindowTitle(self._t("editor", "Editor"))
        try:
            icon = self.host.windowIcon()
            if isinstance(icon, QIcon):
                self.setWindowIcon(icon)
        except Exception:
            pass
        if self.embedded:
            try:
                self.setWindowFlags(Qt.Widget)
            except Exception:
                pass
            self.setModal(False)
        else:
            self.setModal(True)
        self.resize(1360, 860)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        top_wrap = QFrame()
        top_wrap.setStyleSheet(
            "QFrame{"
            "background: rgba(16,24,36,0.78);"
            "border:1px solid rgba(126,176,236,0.24);"
            "border-radius:10px;"
            "}"
        )
        top = QHBoxLayout(top_wrap)
        top.setContentsMargins(8, 6, 8, 6)
        top.setSpacing(8)
        self.play_btn = QPushButton(self._t("play", "Play"))
        self.stop_btn = QPushButton(self._t("stop", "Stop"))
        for b in (self.play_btn, self.stop_btn):
            b.setStyleSheet(self.host._glass_btn_css())
            b.setCursor(Qt.PointingHandCursor)
        top.addWidget(self.play_btn)
        top.addWidget(self.stop_btn)
        self.interactive_badge = QLabel("Interactive: always ON")
        self.interactive_badge.setStyleSheet(
            "padding:4px 10px; border-radius:9px; "
            "background: rgba(92,160,236,0.20); border:1px solid rgba(140,196,255,0.42);"
        )
        top.addWidget(self.interactive_badge)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(self._t("editor_none_mode", "Off"), "off")
        self.mode_combo.addItem(self._t("editor_crop_mode", "Crop area"), "crop")
        self.mode_combo.addItem(self._t("editor_mask_mode", "Mask area"), "mask")
        self.mode_combo.addItem(self._t("editor_text_mode", "Layer move"), "text")
        self.mode_combo.addItem(self._t("editor_media_mode", "Media layer move"), "media")
        self.mode_combo.hide()
        self.timeline_title_lbl = QLabel(self._t("editor_timeline", "Timeline"))
        top.addWidget(self.timeline_title_lbl)
        self.time_slider = QSlider(Qt.Horizontal)
        self.time_slider.setRange(0, self.duration_ms)
        self.time_spin = QSpinBox()
        self.time_spin.setRange(0, self.duration_ms)
        top.addWidget(self.time_slider, 1)
        top.addWidget(self.time_spin)
        self.full_btn = QPushButton(self._t("editor_fullscreen", "Fullscreen editor"))
        self.full_btn.setStyleSheet(self.host._glass_btn_css())
        self.full_btn.setCursor(Qt.PointingHandCursor)
        top.addWidget(self.full_btn)
        root.addWidget(top_wrap, 0)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)

        # Left panel (media/layers), closer to NLE layouts.
        left_wrap = QFrame()
        left_wrap.setMinimumWidth(300)
        left_wrap.setStyleSheet(
            "QFrame{"
            "background: rgba(10,16,24,0.74);"
            "border:1px solid rgba(126,176,236,0.20);"
            "border-radius:12px;"
            "}"
        )
        ll = QVBoxLayout(left_wrap)
        ll.setContentsMargins(8, 8, 8, 8)
        ll.setSpacing(6)
        left_title_text = self._t("editor_media_layers", "Media layers") + " / " + self._t("editor_layers", "Layers")
        if self.photo_mode:
            left_title_text = "Tools / Layers / Adjustments"
        left_title = QLabel(left_title_text)
        left_title.setStyleSheet("font-weight:700; letter-spacing:0.5px;")
        ll.addWidget(left_title)
        quick = QHBoxLayout()
        self.quick_add_text_btn = QPushButton("+ Text")
        self.quick_add_media_btn = QPushButton("+ Media")
        self.quick_import_audio_btn = QPushButton("+ Audio")
        for b in (self.quick_add_text_btn, self.quick_add_media_btn, self.quick_import_audio_btn):
            b.setStyleSheet(self.host._glass_btn_css())
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(30)
            quick.addWidget(b)
        self.quick_add_text_btn.setToolTip(self._t("editor_add_layer", "Add text layer"))
        self.quick_add_media_btn.setToolTip(self._t("editor_add_media_layer", "Add media layer"))
        self.quick_import_audio_btn.setToolTip(self._t("editor_import_audio", "Import audio"))
        ll.addLayout(quick)
        if self.photo_mode:
            photo_wrap = QFrame()
            photo_wrap.setStyleSheet(
                "QFrame{background: rgba(255,255,255,0.04); border:1px solid rgba(126,176,236,0.18); border-radius:10px;}"
            )
            photo_row = QVBoxLayout(photo_wrap)
            photo_row.setContentsMargins(6, 6, 6, 6)
            photo_row.setSpacing(4)
            self.photo_tool_buttons = []
            icon_map = {
                "Move": "arrow-right-circle",
                "Marquee": "layers",
                "Lasso": "node",
                "Brush": "spark",
                "Eraser": "close",
                "Text": "info",
                "Crop": "crop",
                "Mask": "layers",
            }
            for nm in ("Move", "Marquee", "Lasso", "Brush", "Eraser", "Text", "Crop", "Mask"):
                b = QPushButton(nm)
                b.setStyleSheet(self.host._glass_btn_css())
                b.setCursor(Qt.PointingHandCursor)
                b.setCheckable(True)
                b.setMinimumHeight(30)
                try:
                    ico = self.host._load_svg_icon(icon_map.get(nm, "spark"), "#dfe8f6")
                    if ico is not None:
                        b.setIcon(ico)
                except Exception:
                    pass
                self.photo_tool_buttons.append(b)
                photo_row.addWidget(b, 0)
            if self.photo_tool_buttons:
                self.photo_tool_buttons[0].setChecked(True)
            self.photo_paint_enable_chk = QCheckBox("Paint layer")
            self.photo_paint_enable_chk.setChecked(bool(self.state.get("photo_paint_enabled", False)))
            self.photo_paint_enable_chk.setStyleSheet("QCheckBox{padding-top:2px;}")
            photo_row.addWidget(self.photo_paint_enable_chk, 0)

            self.photo_brush_size_slider = QSlider(Qt.Horizontal)
            self.photo_brush_size_slider.setRange(1, 220)
            self.photo_brush_size_slider.setValue(int(self.state.get("photo_brush_size", 26)))
            self.photo_brush_size_val = QLabel(str(int(self.photo_brush_size_slider.value())))
            bs_row = QHBoxLayout()
            bs_row.setContentsMargins(0, 0, 0, 0)
            bs_row.setSpacing(6)
            bs_row.addWidget(QLabel("Brush"), 0)
            bs_row.addWidget(self.photo_brush_size_slider, 1)
            bs_row.addWidget(self.photo_brush_size_val, 0)
            photo_row.addLayout(bs_row, 0)

            self.photo_brush_opacity_slider = QSlider(Qt.Horizontal)
            self.photo_brush_opacity_slider.setRange(1, 100)
            self.photo_brush_opacity_slider.setValue(int(self.state.get("photo_brush_opacity", 92)))
            self.photo_brush_opacity_val = QLabel(str(int(self.photo_brush_opacity_slider.value())))
            bo_row = QHBoxLayout()
            bo_row.setContentsMargins(0, 0, 0, 0)
            bo_row.setSpacing(6)
            bo_row.addWidget(QLabel("Brush opacity"), 0)
            bo_row.addWidget(self.photo_brush_opacity_slider, 1)
            bo_row.addWidget(self.photo_brush_opacity_val, 0)
            photo_row.addLayout(bo_row, 0)

            self.photo_paint_opacity_slider = QSlider(Qt.Horizontal)
            self.photo_paint_opacity_slider.setRange(0, 100)
            self.photo_paint_opacity_slider.setValue(int(self.state.get("photo_paint_opacity", 100)))
            self.photo_paint_opacity_val = QLabel(str(int(self.photo_paint_opacity_slider.value())))
            po_row = QHBoxLayout()
            po_row.setContentsMargins(0, 0, 0, 0)
            po_row.setSpacing(6)
            po_row.addWidget(QLabel("Layer opacity"), 0)
            po_row.addWidget(self.photo_paint_opacity_slider, 1)
            po_row.addWidget(self.photo_paint_opacity_val, 0)
            photo_row.addLayout(po_row, 0)

            self.photo_brush_color_btn = QPushButton("Color")
            self.photo_brush_color_btn.setCursor(Qt.PointingHandCursor)
            self.photo_brush_color_btn.setStyleSheet(self.host._glass_btn_css())
            self.photo_paint_clear_btn = QPushButton("Clear paint")
            self.photo_paint_clear_btn.setCursor(Qt.PointingHandCursor)
            self.photo_paint_clear_btn.setStyleSheet(self.host._glass_btn_css())
            c_row = QHBoxLayout()
            c_row.setContentsMargins(0, 0, 0, 0)
            c_row.setSpacing(6)
            c_row.addWidget(self.photo_brush_color_btn, 1)
            c_row.addWidget(self.photo_paint_clear_btn, 1)
            photo_row.addLayout(c_row, 0)
            ll.addWidget(photo_wrap, 0)
        self.left_tabs = QTabWidget()
        self.left_tabs.setStyleSheet("QTabWidget::pane{border:0;} QTabBar::tab{padding:6px 10px;}")
        try:
            self.left_tabs.tabBar().setExpanding(False)
        except Exception:
            pass
        ll.addWidget(self.left_tabs, 1)
        split.addWidget(left_wrap)

        self.preview_wrap = QFrame()
        self.preview_wrap.setMinimumWidth(660)
        self.preview_wrap.setStyleSheet(
            "QFrame{"
            "background: rgba(0,0,0,0.10);"
            "border:1px solid rgba(126,176,236,0.20);"
            "border-radius:12px;"
            "}"
        )
        pv_l = QVBoxLayout(self.preview_wrap)
        pv_l.setContentsMargins(8, 8, 8, 8)
        pv_l.setSpacing(6)
        self.preview = QLabel()
        self.preview.setMinimumSize(560, 340)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("background: rgba(8,12,16,0.78); border-radius:10px;")
        self.preview.setMouseTracking(True)
        self.preview.setContextMenuPolicy(Qt.CustomContextMenu)
        self.preview.setAcceptDrops(True)
        pv_l.addWidget(self.preview, 1)
        self.preview_hint = QLabel("Drag crop/mask handles directly. Right click for tools. Text/media are draggable.")
        self.preview_hint.setStyleSheet("font-size:11px; color:#9fb3cc;")
        pv_l.addWidget(self.preview_hint)
        split.addWidget(self.preview_wrap)

        right_wrap = QFrame()
        right_wrap.setMinimumWidth(430)
        right_wrap.setStyleSheet(
            "QFrame{"
            "background: rgba(10,16,24,0.74);"
            "border:1px solid rgba(126,176,236,0.20);"
            "border-radius:12px;"
            "}"
        )
        rl = QVBoxLayout(right_wrap)
        rl.setContentsMargins(8, 8, 8, 8)
        rl.setSpacing(6)
        right_title = QLabel(self._t("editor", "Editor") + " - Inspector")
        right_title.setStyleSheet("font-weight:700; letter-spacing:0.5px;")
        rl.addWidget(right_title)
        self.tabs = QTabWidget()
        self.tabs.setMinimumWidth(390)
        self.tabs.setStyleSheet("QTabWidget::pane{border:0;} QTabBar::tab{padding:6px 10px;}")
        rl.addWidget(self.tabs, 1)
        split.addWidget(right_wrap)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 8)
        split.setStretchFactor(2, 5)
        try:
            split.setSizes([330, 940, 500])
        except Exception:
            pass
        root.addWidget(split, 1)

        # Left tabs.
        self._build_left_media_bin_tab()
        self._build_tab_layers()
        # Right inspector tabs.
        self._build_tab_fx()
        self._build_tab_ascii_bridge()
        self._build_tab_crop_mask()
        self._build_tab_trim()
        self._build_tab_audio()
        self._build_tab_nodes()
        try:
            if self.left_tabs.count() <= 0:
                self.left_tabs.hide()
        except Exception:
            pass

        self.timeline_view = TimelineMiniView()
        self.timeline_view.setMinimumHeight(156)
        root.addWidget(self.timeline_view, 0)
        ttools = QFrame()
        ttools.setStyleSheet(
            "QFrame{background: rgba(14,20,30,0.78); border:1px solid rgba(120,170,230,0.22); border-radius:10px;}"
        )
        tl = QHBoxLayout(ttools)
        tl.setContentsMargins(8, 4, 8, 4)
        tl.setSpacing(6)
        self.tl_tool_select_btn = QPushButton("Select")
        self.tl_tool_razor_btn = QPushButton("Razor")
        self.tl_tool_trim_btn = QPushButton("Trim")
        self.tl_tool_ripple_btn = QPushButton("Ripple")
        self.tl_tool_buttons = [
            self.tl_tool_select_btn,
            self.tl_tool_razor_btn,
            self.tl_tool_trim_btn,
            self.tl_tool_ripple_btn,
        ]
        tool_css = (
            "QPushButton{"
            "background: rgba(16,24,36,0.90);"
            "border:1px solid rgba(126,176,236,0.30);"
            "border-radius:10px;"
            "padding:6px 12px;"
            "font-weight:600;"
            "}"
            "QPushButton:hover{background: rgba(36,54,82,0.96); border:1px solid rgba(148,204,255,0.56);}"
            "QPushButton:checked{background: rgba(72,112,162,0.96); border:1px solid rgba(188,224,255,0.86);}"
            "QPushButton:pressed{background: rgba(90,134,188,0.96);}"
        )
        for b in self.tl_tool_buttons:
            b.setCheckable(True)
            b.setStyleSheet(tool_css)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(34)
            tl.addWidget(b)
        action_css = (
            "QPushButton{"
            "background: rgba(14,20,30,0.84);"
            "border:1px solid rgba(120,168,230,0.22);"
            "border-radius:9px;"
            "padding:5px 10px;"
            "}"
            "QPushButton:hover{background: rgba(28,42,62,0.92); border:1px solid rgba(148,204,255,0.52);}"
            "QPushButton:pressed{background: rgba(46,66,98,0.96);}"
        )
        self.tl_select_btn = QPushButton("Preview")
        self.tl_trim_start_btn = QPushButton("Trim Start")
        self.tl_trim_end_btn = QPushButton("Trim End")
        self.tl_kf_start_btn = QPushButton("KF In")
        self.tl_kf_end_btn = QPushButton("KF Out")
        self.tl_split_btn = QPushButton("Split")
        self.tl_ripple_btn = QPushButton("Ripple Del")
        for b in (
            self.tl_select_btn,
            self.tl_trim_start_btn,
            self.tl_trim_end_btn,
            self.tl_kf_start_btn,
            self.tl_kf_end_btn,
            self.tl_split_btn,
            self.tl_ripple_btn,
        ):
            b.setStyleSheet(action_css)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(30)
            tl.addWidget(b)
        try:
            col = "#dfe8f6"
            ico = self.host._load_svg_icon("arrow-right-circle", col)
            if ico is not None:
                self.tl_tool_select_btn.setIcon(ico)
                self.tl_select_btn.setIcon(ico)
            ico = self.host._load_svg_icon("crop", col)
            if ico is not None:
                self.tl_tool_trim_btn.setIcon(ico)
                self.tl_trim_start_btn.setIcon(ico)
                self.tl_trim_end_btn.setIcon(ico)
            ico = self.host._load_svg_icon("scissors", col)
            if ico is not None:
                self.tl_tool_razor_btn.setIcon(ico)
            ico = self.host._load_svg_icon("spark", col)
            if ico is not None:
                self.tl_kf_start_btn.setIcon(ico)
                self.tl_kf_end_btn.setIcon(ico)
            ico = self.host._load_svg_icon("refresh-cw", col)
            if ico is not None:
                self.tl_tool_ripple_btn.setIcon(ico)
                self.tl_ripple_btn.setIcon(ico)
            ico = self.host._load_svg_icon("scissors", col)
            if ico is not None:
                self.tl_split_btn.setIcon(ico)
        except Exception:
            pass
        tl.addStretch(1)
        self.timeline_tool_hint = QLabel("Timeline: Select/Razor/Trim/Ripple tools, drag keyframes, clip edges, Ctrl+Wheel zoom, MMB pan.")
        self.timeline_tool_hint.setStyleSheet("font-size:11px; color:#9fb3cc;")
        tl.addWidget(self.timeline_tool_hint)
        root.addWidget(ttools, 0)
        status_wrap = QFrame()
        status_wrap.setStyleSheet("QFrame{background: rgba(10,16,24,0.66); border:1px solid rgba(120,170,230,0.18); border-radius:8px;}")
        sw = QHBoxLayout(status_wrap)
        sw.setContentsMargins(8, 3, 8, 3)
        sw.setSpacing(8)
        self.timeline_status_icon = QLabel("V")
        self.timeline_status_icon.setStyleSheet("font-weight:700; color:#d7e8ff; min-width:18px;")
        self.timeline_status_text = QLabel("Select mode")
        self.timeline_status_text.setStyleSheet("font-size:11px; color:#9fb3cc;")
        sw.addWidget(self.timeline_status_icon, 0)
        sw.addWidget(self.timeline_status_text, 1)
        root.addWidget(status_wrap, 0)

        bottom = QHBoxLayout()
        self.reset_btn = QPushButton(self._t("editor_reset", "Reset editor"))
        self.apply_btn = QPushButton(self._t("editor_apply", "Apply to project"))
        self.cancel_btn = QPushButton(self._t("cancel", "Cancel"))
        for b in (self.reset_btn, self.apply_btn, self.cancel_btn):
            b.setStyleSheet(self.host._glass_btn_css())
            b.setCursor(Qt.PointingHandCursor)
        bottom.addWidget(self.reset_btn)
        bottom.addStretch(1)
        bottom.addWidget(self.apply_btn)
        bottom.addWidget(self.cancel_btn)
        root.addLayout(bottom)

        self.quick_add_text_btn.clicked.connect(self._add_layer)
        self.quick_add_media_btn.clicked.connect(self._add_media_layer_and_pick)
        self.quick_import_audio_btn.clicked.connect(self._audio_import)
        self.setAcceptDrops(True)
        self._connect_signals()
        if self.photo_mode:
            try:
                self._load_photo_paint_state()
            except Exception:
                pass
            try:
                if hasattr(self, "photo_brush_size_slider"):
                    self.photo_brush_size_slider.valueChanged.connect(
                        lambda v: (self.photo_brush_size_val.setText(str(int(v))), self._schedule_render_preview(0, fast=True))
                    )
                if hasattr(self, "photo_brush_opacity_slider"):
                    self.photo_brush_opacity_slider.valueChanged.connect(
                        lambda v: (self.photo_brush_opacity_val.setText(str(int(v))), self._schedule_render_preview(0, fast=True))
                    )
                if hasattr(self, "photo_paint_opacity_slider"):
                    self.photo_paint_opacity_slider.valueChanged.connect(
                        lambda v: (self.photo_paint_opacity_val.setText(str(int(v))), self._schedule_render_preview(0, fast=True))
                    )
                if hasattr(self, "photo_paint_enable_chk"):
                    self.photo_paint_enable_chk.stateChanged.connect(lambda *_: self._schedule_render_preview(0, fast=True))
                if hasattr(self, "photo_brush_color_btn"):
                    self.photo_brush_color_btn.clicked.connect(self._pick_photo_brush_color)
                    self._set_color_btn(self.photo_brush_color_btn, self._photo_brush_rgba)
                if hasattr(self, "photo_paint_clear_btn"):
                    self.photo_paint_clear_btn.clicked.connect(self._clear_photo_paint_layer)
            except Exception:
                pass
        self._refresh_timeline_view()
        self._animate_editor_entrance([left_wrap, self.preview_wrap, right_wrap, self.timeline_view, ttools])
        if self.photo_mode:
            self.play_btn.hide()
            self.stop_btn.hide()
            self.time_slider.hide()
            self.time_spin.hide()
            self.timeline_title_lbl.hide()
            self.interactive_badge.setText("Photo workspace")
            try:
                for ref in (getattr(self, "trim_tab_ref", None), getattr(self, "audio_tab_ref", None), getattr(self, "nodes_tab_ref", None)):
                    if ref is None:
                        continue
                    idx = self.tabs.indexOf(ref)
                    if idx >= 0:
                        self.tabs.removeTab(idx)
            except Exception:
                pass
            self.timeline_view.hide()
            ttools.hide()
            status_wrap.hide()
            self.timeline_tool_hint.setText("Photo editor mode: Photoshop-like layers/tools workspace.")

    def _build_tab_fx(self):
        tab = QFrame()
        lay = QFormLayout(tab)
        lay.setLabelAlignment(Qt.AlignLeft)
        self.fx_ctrl = {}
        defs = [
            ("brightness", self._t("brightness", "Brightness"), 0, 250),
            ("contrast", self._t("contrast", "Contrast"), 0, 250),
            ("saturation", self._t("saturation", "Saturation"), 0, 250),
            ("sharpness", self._t("sharpen", "Sharpen"), 0, 250),
            ("hue", self._t("hue", "Hue"), -180, 180),
            ("exposure", self._t("exposure", "Exposure"), -180, 180),
            ("temperature", self._t("temperature", "Temperature"), -180, 180),
        ]
        for key, title, lo, hi in defs:
            sl, row = self._slider_with_value(lo, hi, int(self.state.get(key, 100 if lo == 0 else 0)))
            self.fx_ctrl[key] = sl
            lay.addRow(title + ":", row)
        self.tabs.addTab(tab, self._t("style", "Adjust"))

    def _build_tab_ascii_bridge(self):
        tab = QFrame()
        lay = QFormLayout(tab)
        lay.setLabelAlignment(Qt.AlignLeft)
        self.ascii_preview_chk = QCheckBox(self._t("editor_ascii_preview", "Preview with ASCII style + Pro Tools"))
        self.ascii_apply_chk = QCheckBox(self._t("editor_ascii_apply", "Apply ASCII+PRO settings to main project"))
        self.ascii_style_combo = QComboBox()
        styles = []
        try:
            if hasattr(self.host, "style_combo") and self.host.style_combo is not None:
                styles = [self.host.style_combo.itemText(i) for i in range(self.host.style_combo.count())]
        except Exception:
            styles = []
        if not styles:
            styles = ["bw", "red", "color", "matrix", "matrix2", "neon", "pastel", "custom", "none"]
        for st in styles:
            self.ascii_style_combo.addItem(str(st))
        self.ascii_width_spin = QSpinBox()
        self.ascii_width_spin.setRange(40, 520)
        self.ascii_font_spin = QSpinBox()
        self.ascii_font_spin.setRange(6, 72)
        self.ascii_charset_edit = QLineEdit()
        self.ascii_charset_edit.setPlaceholderText(self._t("charset", "Charset"))
        self.ascii_fg_input = QLineEdit()
        self.ascii_bg_input = QLineEdit()
        self.ascii_fg_pick_btn = QPushButton(self._t("editor_pick_color", "Color"))
        self.ascii_bg_pick_btn = QPushButton(self._t("editor_pick_color", "Color"))
        for b in (self.ascii_fg_pick_btn, self.ascii_bg_pick_btn):
            b.setStyleSheet(self.host._glass_btn_css())
            b.setCursor(Qt.PointingHandCursor)
        fg_row = QHBoxLayout()
        fg_row.setContentsMargins(0, 0, 0, 0)
        fg_row.setSpacing(6)
        fg_row.addWidget(self.ascii_fg_input, 1)
        fg_row.addWidget(self.ascii_fg_pick_btn, 0)
        bg_row = QHBoxLayout()
        bg_row.setContentsMargins(0, 0, 0, 0)
        bg_row.setSpacing(6)
        bg_row.addWidget(self.ascii_bg_input, 1)
        bg_row.addWidget(self.ascii_bg_pick_btn, 0)
        self.ascii_pro_tools_chk = QCheckBox(self._t("enable_pro_tools", "Enable Pro Tools"))
        self.ascii_pro_bloom, self.ascii_pro_bloom_row = self._slider_with_value(0, 100, 0)
        self.ascii_pro_vignette, self.ascii_pro_vignette_row = self._slider_with_value(0, 100, 0)
        self.ascii_pro_grain, self.ascii_pro_grain_row = self._slider_with_value(0, 100, 0)
        self.ascii_pro_chroma, self.ascii_pro_chroma_row = self._slider_with_value(0, 24, 0)
        self.ascii_pro_glitch, self.ascii_pro_glitch_row = self._slider_with_value(0, 100, 0)
        self.ascii_preset_combo = QComboBox()
        self.ascii_preset_combo.addItems(["none", "soft", "cyber", "cinematic", "sketch", "retro", "vhs", "clean"])
        self.ascii_preset_apply_btn = QPushButton(self._t("apply", "Apply"))
        self.ascii_preset_apply_btn.setStyleSheet(self.host._glass_btn_css())
        self.ascii_preset_apply_btn.setCursor(Qt.PointingHandCursor)
        pre_row = QHBoxLayout()
        pre_row.setContentsMargins(0, 0, 0, 0)
        pre_row.setSpacing(6)
        pre_row.addWidget(self.ascii_preset_combo, 1)
        pre_row.addWidget(self.ascii_preset_apply_btn, 0)
        lay.addRow(self.ascii_preview_chk)
        lay.addRow(self.ascii_apply_chk)
        lay.addRow(self._t("style", "Style") + ":", self.ascii_style_combo)
        lay.addRow(self._t("width", "Width (chars)") + ":", self.ascii_width_spin)
        lay.addRow(self._t("font_size", "Font size") + ":", self.ascii_font_spin)
        lay.addRow(self._t("charset", "Charset") + ":", self.ascii_charset_edit)
        lay.addRow(self._t("text_color", "Text color") + ":", fg_row)
        lay.addRow(self._t("bg_color", "BG color") + ":", bg_row)
        lay.addRow(self.ascii_pro_tools_chk)
        lay.addRow(self._t("pro_bloom", "Bloom (%)") + ":", self.ascii_pro_bloom_row)
        lay.addRow(self._t("pro_vignette", "Vignette (%)") + ":", self.ascii_pro_vignette_row)
        lay.addRow(self._t("pro_grain", "Film grain (%)") + ":", self.ascii_pro_grain_row)
        lay.addRow(self._t("pro_chroma", "Chroma shift (px)") + ":", self.ascii_pro_chroma_row)
        lay.addRow(self._t("pro_glitch", "Glitch (%)") + ":", self.ascii_pro_glitch_row)
        lay.addRow(self._t("preset", "Preset") + ":", pre_row)
        hint = QLabel(
            self._t(
                "editor_ascii_hint",
                "This tab combines editor transforms with ASCII style and Pro Tools. "
                "Enable preview to see final look directly in editor.",
            )
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size:11px; color:#9fb3cc;")
        lay.addRow(hint)
        self.tabs.addTab(tab, self._t("editor_ascii_tab", "ASCII + PRO"))

    def _pick_ascii_hex(self, key):
        c = QColorDialog.getColor(parent=self)
        if not c.isValid():
            return
        he = str(c.name() or "#ffffff")
        if str(key) == "bg":
            self.ascii_bg_input.setText(he)
        else:
            self.ascii_fg_input.setText(he)
        self._save_ascii_bridge_controls()
        self._schedule_render_preview(0, fast=False)

    def _apply_ascii_local_preset(self):
        p = str(self.ascii_preset_combo.currentText() or "none").strip().lower()
        vals = {
            "none": (0, 0, 0, 0, 0),
            "soft": (16, 14, 12, 0, 0),
            "cyber": (24, 18, 8, 3, 26),
            "cinematic": (30, 34, 10, 1, 8),
            "sketch": (8, 22, 14, 0, 2),
            "retro": (20, 28, 20, 1, 22),
            "vhs": (12, 30, 24, 4, 34),
            "clean": (6, 8, 0, 0, 0),
        }.get(p, (0, 0, 0, 0, 0))
        self.ascii_pro_bloom.setValue(int(vals[0]))
        self.ascii_pro_vignette.setValue(int(vals[1]))
        self.ascii_pro_grain.setValue(int(vals[2]))
        self.ascii_pro_chroma.setValue(int(vals[3]))
        self.ascii_pro_glitch.setValue(int(vals[4]))
        self._save_ascii_bridge_controls()
        self._schedule_render_preview(0, fast=False)

    def _load_ascii_bridge_controls(self):
        if not hasattr(self, "ascii_preview_chk"):
            return
        s = self.state
        self._ui_lock = True
        try:
            self.ascii_preview_chk.setChecked(bool(s.get("ascii_bridge_enabled", False)))
            self.ascii_apply_chk.setChecked(bool(s.get("ascii_bridge_apply", False)))
            st = str(s.get("ascii_style", "bw") or "bw")
            j = self.ascii_style_combo.findText(st)
            self.ascii_style_combo.setCurrentIndex(j if j >= 0 else 0)
            self.ascii_width_spin.setValue(int(s.get("ascii_width", 120) or 120))
            self.ascii_font_spin.setValue(int(s.get("ascii_font_size", 10) or 10))
            self.ascii_charset_edit.setText(str(s.get("ascii_charset", "") or ""))
            self.ascii_fg_input.setText(str(s.get("ascii_fg_hex", "#ffffff") or "#ffffff"))
            self.ascii_bg_input.setText(str(s.get("ascii_bg_hex", "#000000") or "#000000"))
            self.ascii_pro_tools_chk.setChecked(bool(s.get("ascii_pro_tools", False)))
            self.ascii_pro_bloom.setValue(int(s.get("ascii_pro_bloom", 0) or 0))
            self.ascii_pro_vignette.setValue(int(s.get("ascii_pro_vignette", 0) or 0))
            self.ascii_pro_grain.setValue(int(s.get("ascii_pro_grain", 0) or 0))
            self.ascii_pro_chroma.setValue(int(s.get("ascii_pro_chroma", 0) or 0))
            self.ascii_pro_glitch.setValue(int(s.get("ascii_pro_glitch", 0) or 0))
        finally:
            self._ui_lock = False

    def _save_ascii_bridge_controls(self):
        if self._ui_lock or not hasattr(self, "ascii_preview_chk"):
            return
        self.state["ascii_bridge_enabled"] = bool(self.ascii_preview_chk.isChecked())
        self.state["ascii_bridge_apply"] = bool(self.ascii_apply_chk.isChecked())
        self.state["ascii_style"] = str(self.ascii_style_combo.currentText() or "bw")
        self.state["ascii_width"] = int(self.ascii_width_spin.value())
        self.state["ascii_font_size"] = int(self.ascii_font_spin.value())
        self.state["ascii_charset"] = str(self.ascii_charset_edit.text() or "")
        self.state["ascii_fg_hex"] = str(self.ascii_fg_input.text() or "#ffffff").strip() or "#ffffff"
        self.state["ascii_bg_hex"] = str(self.ascii_bg_input.text() or "#000000").strip() or "#000000"
        self.state["ascii_pro_tools"] = bool(self.ascii_pro_tools_chk.isChecked())
        self.state["ascii_pro_bloom"] = int(self.ascii_pro_bloom.value())
        self.state["ascii_pro_vignette"] = int(self.ascii_pro_vignette.value())
        self.state["ascii_pro_grain"] = int(self.ascii_pro_grain.value())
        self.state["ascii_pro_chroma"] = int(self.ascii_pro_chroma.value())
        self.state["ascii_pro_glitch"] = int(self.ascii_pro_glitch.value())

    def _apply_ascii_bridge_preview(self, img):
        if not hasattr(self, "ascii_preview_chk"):
            return img
        self._save_ascii_bridge_controls()
        if not bool(self.state.get("ascii_bridge_enabled", False)):
            return img
        host = self.host
        st = self.state
        keys = [
            "style",
            "width_chars",
            "font_size",
            "ascii_chars",
            "fg_hex",
            "bg_hex",
            "pro_tools",
            "pro_bloom",
            "pro_vignette",
            "pro_grain",
            "pro_chroma",
            "pro_glitch",
        ]
        backup = {k: getattr(host, k, None) for k in keys}
        try:
            host.style = str(st.get("ascii_style", host.style) or host.style)
            host.width_chars = int(st.get("ascii_width", getattr(host, "width_chars", 120)) or 120)
            host.font_size = int(st.get("ascii_font_size", getattr(host, "font_size", 10)) or 10)
            host.ascii_chars = str(st.get("ascii_charset", getattr(host, "ascii_chars", "")) or getattr(host, "ascii_chars", ""))
            host.fg_hex = str(st.get("ascii_fg_hex", getattr(host, "fg_hex", "#ffffff")) or "#ffffff")
            host.bg_hex = str(st.get("ascii_bg_hex", getattr(host, "bg_hex", "#000000")) or "#000000")
            host.pro_tools = bool(st.get("ascii_pro_tools", getattr(host, "pro_tools", False)))
            host.pro_bloom = int(st.get("ascii_pro_bloom", getattr(host, "pro_bloom", 0)) or 0)
            host.pro_vignette = int(st.get("ascii_pro_vignette", getattr(host, "pro_vignette", 0)) or 0)
            host.pro_grain = int(st.get("ascii_pro_grain", getattr(host, "pro_grain", 0)) or 0)
            host.pro_chroma = int(st.get("ascii_pro_chroma", getattr(host, "pro_chroma", 0)) or 0)
            host.pro_glitch = int(st.get("ascii_pro_glitch", getattr(host, "pro_glitch", 0)) or 0)
            out = host._render_with_style(img.convert("RGB"), output_size=img.size)
            if isinstance(out, Image.Image):
                return out.convert("RGB")
        except Exception:
            return img
        finally:
            for k, v in backup.items():
                try:
                    setattr(host, k, v)
                except Exception:
                    pass
        return img

    def _build_left_media_bin_tab(self):
        if not hasattr(self, "left_tabs") or self.left_tabs is None:
            return
        tab = QFrame()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)
        hint = QLabel("Media bin. Double click item to use as media layer.")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size:11px; color:#9fb3cc;")
        lay.addWidget(hint)
        self.media_bin_list = QListWidget()
        self.media_bin_list.setMinimumHeight(160)
        lay.addWidget(self.media_bin_list, 1)
        self.left_tabs.addTab(tab, self._t("gallery", "Gallery"))

    def _refresh_media_bin(self):
        if not hasattr(self, "media_bin_list") or self.media_bin_list is None:
            return
        self.media_bin_list.clear()
        rows = []
        try:
            src = str(getattr(self.host, "current_path", "") or "").strip()
        except Exception:
            src = ""
        if src:
            rows.append(("SOURCE", src))
        try:
            ap = str(self.state.get("audio_path", "") or "").strip()
        except Exception:
            ap = ""
        if ap:
            rows.append(("AUDIO", ap))
        for i, lyr in enumerate(self.state.get("media_layers", []) or []):
            p = str((lyr or {}).get("path", "") or "").strip()
            if not p:
                continue
            typ = str((lyr or {}).get("type", "image") or "image").upper()
            rows.append((f"M{i + 1}:{typ}", p))
        for tag, path in rows:
            nm = os.path.basename(path) if path else "-"
            it = QListWidgetItem(f"{tag}  {nm}")
            it.setToolTip(path)
            it.setData(Qt.UserRole, path)
            self.media_bin_list.addItem(it)

    def _on_media_bin_activate(self, item):
        if item is None:
            return
        path = str(item.data(Qt.UserRole) or "").strip()
        if not path:
            return
        low = path.lower()
        if low.endswith((".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac")):
            self.state["audio_path"] = path
            if hasattr(self, "audio_path_lbl"):
                self.audio_path_lbl.setText(path)
            self._render_preview()
            return
        layer, _ = self._selected_media_layer()
        if layer is None:
            self._add_media_layer()
            layer, _ = self._selected_media_layer()
        if layer is None:
            return
        layer["path"] = path
        if low.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm")):
            layer["type"] = "video"
        elif low.endswith(".gif"):
            layer["type"] = "gif"
        else:
            layer["type"] = "image"
        self._refresh_media_layers()
        self._load_media_layer_controls()
        self._render_preview()

    def _build_tab_layers(self):
        tab = QFrame()
        self.layers_tab_ref = tab
        tab_root = QVBoxLayout(tab)
        tab_root.setContentsMargins(0, 0, 0, 0)
        tab_root.setSpacing(0)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        sc.setWidget(body)
        tab_root.addWidget(sc, 1)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)
        self.layers_list = QListWidget()
        self.layers_list.setMinimumHeight(140)
        lay.addWidget(self.layers_list)
        row = QHBoxLayout()
        self.add_layer_btn = QPushButton("+Text")
        self.rem_layer_btn = QPushButton("-Text")
        for b in (self.add_layer_btn, self.rem_layer_btn):
            b.setStyleSheet(self.host._glass_btn_css())
            b.setCursor(Qt.PointingHandCursor)
            row.addWidget(b)
        self.add_layer_btn.setToolTip(self._t("editor_add_layer", "Add text layer"))
        self.rem_layer_btn.setToolTip(self._t("editor_remove_layer", "Remove layer"))
        lay.addLayout(row)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        self.lyr_enabled = QCheckBox(self._t("toggle", "Toggle enabled"))
        self.lyr_text = QLineEdit()
        self.lyr_font = QFontComboBox()
        self.lyr_size = QSpinBox(); self.lyr_size.setRange(6, 360)
        self.lyr_x = QSpinBox(); self.lyr_x.setRange(-8192, 8192)
        self.lyr_y = QSpinBox(); self.lyr_y.setRange(-8192, 8192)
        self.lyr_x1 = QSpinBox(); self.lyr_x1.setRange(-8192, 8192)
        self.lyr_y1 = QSpinBox(); self.lyr_y1.setRange(-8192, 8192)
        self.lyr_start = QSpinBox(); self.lyr_start.setRange(0, self.duration_ms)
        self.lyr_end = QSpinBox(); self.lyr_end.setRange(0, self.duration_ms)
        self.lyr_ease = QComboBox()
        self.lyr_ease.addItems(["linear", "ease_in", "ease_out", "ease_in_out", "bezier"])
        self.lyr_bx1 = QDoubleSpinBox(); self.lyr_bx1.setRange(0.0, 1.0); self.lyr_bx1.setDecimals(2); self.lyr_bx1.setSingleStep(0.01)
        self.lyr_by1 = QDoubleSpinBox(); self.lyr_by1.setRange(0.0, 1.0); self.lyr_by1.setDecimals(2); self.lyr_by1.setSingleStep(0.01)
        self.lyr_bx2 = QDoubleSpinBox(); self.lyr_bx2.setRange(0.0, 1.0); self.lyr_bx2.setDecimals(2); self.lyr_bx2.setSingleStep(0.01)
        self.lyr_by2 = QDoubleSpinBox(); self.lyr_by2.setRange(0.0, 1.0); self.lyr_by2.setDecimals(2); self.lyr_by2.setSingleStep(0.01)
        self.lyr_sx = QSpinBox(); self.lyr_sx.setRange(10, 800)
        self.lyr_sy = QSpinBox(); self.lyr_sy.setRange(10, 800)
        self.lyr_alpha, self.lyr_alpha_row = self._slider_with_value(0, 255, 220)
        self.lyr_color_btn = QPushButton(self._t("editor_pick_color", "Color"))
        self.lyr_color_btn.setStyleSheet(self.host._glass_btn_css())
        self.lyr_set_start_btn = QPushButton("Set start keyframe")
        self.lyr_set_end_btn = QPushButton("Set end keyframe")
        for b in (self.lyr_set_start_btn, self.lyr_set_end_btn):
            b.setStyleSheet(self.host._glass_btn_css())
            b.setCursor(Qt.PointingHandCursor)
        form.addRow(self.lyr_enabled)
        form.addRow(self._t("editor_text", "Text") + ":", self.lyr_text)
        form.addRow(self._t("font_family", "Fonts") + ":", self.lyr_font)
        form.addRow(self._t("font_size", "Font size") + ":", self.lyr_size)
        form.addRow("X0:", self.lyr_x); form.addRow("Y0:", self.lyr_y)
        form.addRow("X1:", self.lyr_x1); form.addRow("Y1:", self.lyr_y1)
        form.addRow("Scale X (%):", self.lyr_sx); form.addRow("Scale Y (%):", self.lyr_sy)
        form.addRow("Alpha:", self.lyr_alpha_row)
        form.addRow(self._t("editor_trim_start", "Trim start (ms)") + ":", self.lyr_start)
        form.addRow(self._t("editor_trim_end", "Trim end (ms)") + ":", self.lyr_end)
        form.addRow("Easing:", self.lyr_ease)
        form.addRow("Bezier x1:", self.lyr_bx1); form.addRow("Bezier y1:", self.lyr_by1)
        form.addRow("Bezier x2:", self.lyr_bx2); form.addRow("Bezier y2:", self.lyr_by2)
        form.addRow(self.lyr_color_btn)
        kf_row = QHBoxLayout()
        kf_row.addWidget(self.lyr_set_start_btn)
        kf_row.addWidget(self.lyr_set_end_btn)
        form.addRow(kf_row)
        lay.addLayout(form)

        # Unified "Layers" category: media layers are in the same tab below text layers.
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("QFrame{color: rgba(150,180,220,0.28);}")
        lay.addWidget(sep)
        media_title = QLabel(self._t("editor_media_layers", "Media layers"))
        media_title.setStyleSheet("font-weight:600; color:#cdddf2;")
        lay.addWidget(media_title)
        self.media_list = QListWidget()
        self.media_list.setMinimumHeight(130)
        lay.addWidget(self.media_list)
        row2 = QHBoxLayout()
        self.add_media_btn = QPushButton("+Media")
        self.rem_media_btn = QPushButton("-Media")
        self.pick_media_btn = QPushButton("Pick")
        for b in (self.add_media_btn, self.rem_media_btn, self.pick_media_btn):
            b.setStyleSheet(self.host._glass_btn_css())
            b.setCursor(Qt.PointingHandCursor)
            row2.addWidget(b)
        self.add_media_btn.setToolTip(self._t("editor_add_media_layer", "Add media layer"))
        self.rem_media_btn.setToolTip(self._t("editor_remove_media_layer", "Remove media layer"))
        self.pick_media_btn.setToolTip(self._t("editor_pick_media", "Choose media"))
        lay.addLayout(row2)
        mform = QFormLayout()
        mform.setLabelAlignment(Qt.AlignLeft)
        self.med_enabled = QCheckBox(self._t("toggle", "Toggle enabled"))
        self.med_path = QLineEdit()
        self.med_type = QComboBox()
        self.med_type.addItem("Image", "image")
        self.med_type.addItem("Video", "video")
        self.med_type.addItem("GIF", "gif")
        self.med_x = QSpinBox(); self.med_x.setRange(-8192, 8192)
        self.med_y = QSpinBox(); self.med_y.setRange(-8192, 8192)
        self.med_x1 = QSpinBox(); self.med_x1.setRange(-8192, 8192)
        self.med_y1 = QSpinBox(); self.med_y1.setRange(-8192, 8192)
        self.med_sx = QSpinBox(); self.med_sx.setRange(5, 800)
        self.med_sy = QSpinBox(); self.med_sy.setRange(5, 800)
        self.med_alpha, self.med_alpha_row = self._slider_with_value(0, 255, 255)
        self.med_start = QSpinBox(); self.med_start.setRange(0, self.duration_ms)
        self.med_end = QSpinBox(); self.med_end.setRange(0, self.duration_ms)
        self.med_speed = QDoubleSpinBox()
        self.med_speed.setRange(0.05, 16.0)
        self.med_speed.setDecimals(2)
        self.med_speed.setSingleStep(0.05)
        self.med_speed.setValue(1.0)
        self.med_ease = QComboBox()
        self.med_ease.addItems(["linear", "ease_in", "ease_out", "ease_in_out", "bezier"])
        self.med_bx1 = QDoubleSpinBox(); self.med_bx1.setRange(0.0, 1.0); self.med_bx1.setDecimals(2); self.med_bx1.setSingleStep(0.01)
        self.med_by1 = QDoubleSpinBox(); self.med_by1.setRange(0.0, 1.0); self.med_by1.setDecimals(2); self.med_by1.setSingleStep(0.01)
        self.med_bx2 = QDoubleSpinBox(); self.med_bx2.setRange(0.0, 1.0); self.med_bx2.setDecimals(2); self.med_bx2.setSingleStep(0.01)
        self.med_by2 = QDoubleSpinBox(); self.med_by2.setRange(0.0, 1.0); self.med_by2.setDecimals(2); self.med_by2.setSingleStep(0.01)
        self.med_blend = QComboBox()
        self.med_blend.addItems(["normal", "screen", "multiply", "add"])
        self.med_set_start_btn = QPushButton("Set start keyframe")
        self.med_set_end_btn = QPushButton("Set end keyframe")
        for b in (self.med_set_start_btn, self.med_set_end_btn):
            b.setStyleSheet(self.host._glass_btn_css())
            b.setCursor(Qt.PointingHandCursor)
        mform.addRow(self.med_enabled)
        mform.addRow("Path:", self.med_path)
        mform.addRow("Type:", self.med_type)
        mform.addRow("X0:", self.med_x); mform.addRow("Y0:", self.med_y)
        mform.addRow("X1:", self.med_x1); mform.addRow("Y1:", self.med_y1)
        mform.addRow("Scale X (%):", self.med_sx); mform.addRow("Scale Y (%):", self.med_sy)
        mform.addRow("Alpha:", self.med_alpha_row)
        mform.addRow(self._t("editor_blend", "Blend") + ":", self.med_blend)
        mform.addRow(self._t("editor_trim_start", "Trim start (ms)") + ":", self.med_start)
        mform.addRow(self._t("editor_trim_end", "Trim end (ms)") + ":", self.med_end)
        mform.addRow("Speed x:", self.med_speed)
        mform.addRow("Easing:", self.med_ease)
        mform.addRow("Bezier x1:", self.med_bx1); mform.addRow("Bezier y1:", self.med_by1)
        mform.addRow("Bezier x2:", self.med_bx2); mform.addRow("Bezier y2:", self.med_by2)
        mkf_row = QHBoxLayout()
        mkf_row.addWidget(self.med_set_start_btn)
        mkf_row.addWidget(self.med_set_end_btn)
        mform.addRow(mkf_row)
        lay.addLayout(mform)
        self.tabs.addTab(tab, self._t("editor_layers", "Layers"))

    def _build_tab_media_layers(self):
        tab = QFrame()
        tab_root = QVBoxLayout(tab)
        tab_root.setContentsMargins(0, 0, 0, 0)
        tab_root.setSpacing(0)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        sc.setWidget(body)
        tab_root.addWidget(sc, 1)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)
        self.media_list = QListWidget()
        self.media_list.setMinimumHeight(130)
        lay.addWidget(self.media_list)
        row = QHBoxLayout()
        self.add_media_btn = QPushButton("+Media")
        self.rem_media_btn = QPushButton("-Media")
        self.pick_media_btn = QPushButton("Pick")
        for b in (self.add_media_btn, self.rem_media_btn, self.pick_media_btn):
            b.setStyleSheet(self.host._glass_btn_css())
            b.setCursor(Qt.PointingHandCursor)
            row.addWidget(b)
        self.add_media_btn.setToolTip(self._t("editor_add_media_layer", "Add media layer"))
        self.rem_media_btn.setToolTip(self._t("editor_remove_media_layer", "Remove media layer"))
        self.pick_media_btn.setToolTip(self._t("editor_pick_media", "Choose media"))
        lay.addLayout(row)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        self.med_enabled = QCheckBox(self._t("toggle", "Toggle enabled"))
        self.med_path = QLineEdit()
        self.med_type = QComboBox()
        self.med_type.addItem("Image", "image")
        self.med_type.addItem("Video", "video")
        self.med_type.addItem("GIF", "gif")
        self.med_x = QSpinBox(); self.med_x.setRange(-8192, 8192)
        self.med_y = QSpinBox(); self.med_y.setRange(-8192, 8192)
        self.med_x1 = QSpinBox(); self.med_x1.setRange(-8192, 8192)
        self.med_y1 = QSpinBox(); self.med_y1.setRange(-8192, 8192)
        self.med_sx = QSpinBox(); self.med_sx.setRange(5, 800)
        self.med_sy = QSpinBox(); self.med_sy.setRange(5, 800)
        self.med_alpha, self.med_alpha_row = self._slider_with_value(0, 255, 255)
        self.med_start = QSpinBox(); self.med_start.setRange(0, self.duration_ms)
        self.med_end = QSpinBox(); self.med_end.setRange(0, self.duration_ms)
        self.med_ease = QComboBox()
        self.med_ease.addItems(["linear", "ease_in", "ease_out", "ease_in_out", "bezier"])
        self.med_bx1 = QDoubleSpinBox(); self.med_bx1.setRange(0.0, 1.0); self.med_bx1.setDecimals(2); self.med_bx1.setSingleStep(0.01)
        self.med_by1 = QDoubleSpinBox(); self.med_by1.setRange(0.0, 1.0); self.med_by1.setDecimals(2); self.med_by1.setSingleStep(0.01)
        self.med_bx2 = QDoubleSpinBox(); self.med_bx2.setRange(0.0, 1.0); self.med_bx2.setDecimals(2); self.med_bx2.setSingleStep(0.01)
        self.med_by2 = QDoubleSpinBox(); self.med_by2.setRange(0.0, 1.0); self.med_by2.setDecimals(2); self.med_by2.setSingleStep(0.01)
        self.med_blend = QComboBox()
        self.med_blend.addItems(["normal", "screen", "multiply", "add"])
        self.med_set_start_btn = QPushButton("Set start keyframe")
        self.med_set_end_btn = QPushButton("Set end keyframe")
        for b in (self.med_set_start_btn, self.med_set_end_btn):
            b.setStyleSheet(self.host._glass_btn_css())
            b.setCursor(Qt.PointingHandCursor)
        form.addRow(self.med_enabled)
        form.addRow("Path:", self.med_path)
        form.addRow("Type:", self.med_type)
        form.addRow("X0:", self.med_x); form.addRow("Y0:", self.med_y)
        form.addRow("X1:", self.med_x1); form.addRow("Y1:", self.med_y1)
        form.addRow("Scale X (%):", self.med_sx); form.addRow("Scale Y (%):", self.med_sy)
        form.addRow("Alpha:", self.med_alpha_row)
        form.addRow(self._t("editor_blend", "Blend") + ":", self.med_blend)
        form.addRow(self._t("editor_trim_start", "Trim start (ms)") + ":", self.med_start)
        form.addRow(self._t("editor_trim_end", "Trim end (ms)") + ":", self.med_end)
        form.addRow("Easing:", self.med_ease)
        form.addRow("Bezier x1:", self.med_bx1); form.addRow("Bezier y1:", self.med_by1)
        form.addRow("Bezier x2:", self.med_bx2); form.addRow("Bezier y2:", self.med_by2)
        mkf_row = QHBoxLayout()
        mkf_row.addWidget(self.med_set_start_btn)
        mkf_row.addWidget(self.med_set_end_btn)
        form.addRow(mkf_row)
        lay.addLayout(form)
        target = getattr(self, "left_tabs", None) or self.tabs
        target.addTab(tab, self._t("editor_media_layers", "Media layers"))

    def _build_tab_crop_mask(self):
        tab = QFrame()
        self.crop_mask_tab_ref = tab
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)
        crop_box = QFrame()
        crop_box.setStyleSheet("QFrame{background: rgba(255,255,255,0.05); border-radius:10px;}")
        cf = QFormLayout(crop_box)
        self.crop_enable = QCheckBox(self._t("crop", "Crop"))
        self.crop_x = QSpinBox(); self.crop_x.setRange(0, max(0, self.src.width - 1))
        self.crop_y = QSpinBox(); self.crop_y.setRange(0, max(0, self.src.height - 1))
        self.crop_w = QSpinBox(); self.crop_w.setRange(1, self.src.width)
        self.crop_h = QSpinBox(); self.crop_h.setRange(1, self.src.height)
        cf.addRow(self.crop_enable)
        cf.addRow("X:", self.crop_x); cf.addRow("Y:", self.crop_y)
        cf.addRow("W:", self.crop_w); cf.addRow("H:", self.crop_h)
        lay.addWidget(crop_box)
        mask_box = QFrame()
        mask_box.setStyleSheet("QFrame{background: rgba(255,255,255,0.05); border-radius:10px;}")
        mf = QFormLayout(mask_box)
        self.mask_enable = QCheckBox(self._t("editor_mask", "Mask"))
        self.mask_x = QSpinBox(); self.mask_x.setRange(0, max(0, self.src.width - 1))
        self.mask_y = QSpinBox(); self.mask_y.setRange(0, max(0, self.src.height - 1))
        self.mask_w = QSpinBox(); self.mask_w.setRange(1, self.src.width)
        self.mask_h = QSpinBox(); self.mask_h.setRange(1, self.src.height)
        self.mask_use_image_chk = QCheckBox("Use media mask")
        self.mask_media_path = QLineEdit()
        self.mask_media_path.setPlaceholderText("No mask media selected")
        self.mask_media_pick_btn = QPushButton("Choose mask media")
        self.mask_media_clear_btn = QPushButton("Clear mask media")
        for b in (self.mask_media_pick_btn, self.mask_media_clear_btn):
            b.setStyleSheet(self.host._glass_btn_css())
            b.setCursor(Qt.PointingHandCursor)
        mbtn_row = QHBoxLayout()
        mbtn_row.addWidget(self.mask_media_pick_btn)
        mbtn_row.addWidget(self.mask_media_clear_btn)
        mf.addRow(self.mask_enable)
        mf.addRow("X:", self.mask_x); mf.addRow("Y:", self.mask_y)
        mf.addRow("W:", self.mask_w); mf.addRow("H:", self.mask_h)
        mf.addRow(self.mask_use_image_chk)
        mf.addRow("Mask media:", self.mask_media_path)
        mf.addRow(mbtn_row)
        lay.addWidget(mask_box)
        lay.addStretch(1)
        self.tabs.addTab(tab, self._t("editor_mask", "Mask"))

    def _build_tab_trim(self):
        tab = QFrame()
        self.trim_tab_ref = tab
        lay = QFormLayout(tab)
        lay.setLabelAlignment(Qt.AlignLeft)
        self.trim_enable = QCheckBox(self._t("editor_trim", "Trim"))
        self.trim_start = QSpinBox(); self.trim_start.setRange(0, self.duration_ms)
        self.trim_end = QSpinBox(); self.trim_end.setRange(0, self.duration_ms)
        self.trim_start_slider = QSlider(Qt.Horizontal); self.trim_start_slider.setRange(0, self.duration_ms)
        self.trim_end_slider = QSlider(Qt.Horizontal); self.trim_end_slider.setRange(0, self.duration_ms)
        lay.addRow(self.trim_enable)
        lay.addRow(self._t("editor_trim_start", "Trim start (ms)") + ":", self.trim_start)
        lay.addRow(self.trim_start_slider)
        lay.addRow(self._t("editor_trim_end", "Trim end (ms)") + ":", self.trim_end)
        lay.addRow(self.trim_end_slider)
        self.tabs.addTab(tab, self._t("editor_trim", "Trim"))

    def _build_tab_audio(self):
        tab = QFrame()
        self.audio_tab_ref = tab
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)
        self.audio_path_lbl = QLabel("-")
        self.audio_path_lbl.setWordWrap(True)
        self.audio_path_lbl.setStyleSheet("font-size:11px; color:#b9c8dc;")
        lay.addWidget(self.audio_path_lbl)
        row = QHBoxLayout()
        self.audio_import_btn = QPushButton(self._t("editor_import_audio", "Import audio"))
        self.audio_source_btn = QPushButton(self._t("editor_audio_from_video", "Audio from source video"))
        self.audio_clear_btn = QPushButton(self._t("remove", "Remove"))
        for b in (self.audio_import_btn, self.audio_source_btn, self.audio_clear_btn):
            b.setStyleSheet(self.host._glass_btn_css())
            b.setCursor(Qt.PointingHandCursor)
            row.addWidget(b)
        lay.addLayout(row)
        self.audio_gain, self.audio_gain_row = self._slider_with_value(-24, 24, int(round(float(self.state.get("audio_gain_db", 0.0) or 0.0))))
        self.audio_low = QSpinBox(); self.audio_low.setRange(0, 20000)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.addRow(self._t("editor_gain", "Gain (dB)") + ":", self.audio_gain_row)
        form.addRow(self._t("editor_lowpass", "Low-pass (Hz)") + ":", self.audio_low)
        lay.addLayout(form)
        lay.addStretch(1)
        self.tabs.addTab(tab, self._t("editor_audio", "Audio"))

    def _build_tab_nodes(self):
        tab = QFrame()
        self.nodes_tab_ref = tab
        tab_root = QVBoxLayout(tab)
        tab_root.setContentsMargins(0, 0, 0, 0)
        tab_root.setSpacing(0)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        sc.setWidget(body)
        tab_root.addWidget(sc, 1)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(7)
        self.nodes_enable = QCheckBox(self._t("editor_nodes", "Nodes"))
        lay.addWidget(self.nodes_enable)
        filter_row = QHBoxLayout()
        self.node_family_combo = QComboBox()
        self.node_family_combo.addItems(["All", "Video", "Audio", "Data", "Logic", "Color", "Filter", "Stylize", "Utility"])
        self.node_search = QLineEdit()
        self.node_search.setPlaceholderText("Find node...")
        filter_row.addWidget(self.node_family_combo, 0)
        filter_row.addWidget(self.node_search, 1)
        lay.addLayout(filter_row)
        top = QHBoxLayout()
        self.node_combo = QComboBox()
        self.node_catalog = self._node_catalog()
        self.node_add_btn = QPushButton(self._t("editor_add_node", "Add node"))
        self.node_add_btn.setStyleSheet(self.host._glass_btn_css())
        self.node_add_btn.setCursor(Qt.PointingHandCursor)
        self._populate_node_picker()
        top.addWidget(self.node_combo, 1)
        top.addWidget(self.node_add_btn)
        lay.addLayout(top)
        self.node_desc_lbl = QLabel("")
        self.node_desc_lbl.setWordWrap(True)
        self.node_desc_lbl.setStyleSheet("font-size:11px; color:#9fb3cc;")
        lay.addWidget(self.node_desc_lbl)
        self.node_list = QListWidget()
        self.node_list.setMinimumHeight(118)
        lay.addWidget(self.node_list)
        self.node_graph = NodeGraphCanvas()
        self.node_graph.setMinimumHeight(360)
        self.node_graph.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(self.node_graph, 1)
        hint = QLabel("Drag from output port to input port to connect. Right click for connect/disconnect tools. Ctrl+Wheel zoom, middle button pan.")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size:11px; color:#9fb3cc;")
        lay.addWidget(hint)
        link_box = QFrame()
        link_box.setStyleSheet("QFrame{background: rgba(255,255,255,0.05); border-radius:10px;}")
        link_l = QVBoxLayout(link_box)
        link_l.setContentsMargins(8, 8, 8, 8)
        link_l.setSpacing(6)
        self.node_port_info_lbl = QLabel("Port inspector: select node input/output port to manage multi-links.")
        self.node_port_info_lbl.setWordWrap(True)
        self.node_port_info_lbl.setStyleSheet("font-size:11px; color:#a8bfdc;")
        link_l.addWidget(self.node_port_info_lbl)
        self.node_port_links_list = QListWidget()
        self.node_port_links_list.setMinimumHeight(92)
        link_l.addWidget(self.node_port_links_list, 1)
        link_btn_row = QHBoxLayout()
        self.node_port_detach_btn = QPushButton("Detach selected link")
        self.node_port_detach_all_btn = QPushButton("Detach all from port")
        for b in (self.node_port_detach_btn, self.node_port_detach_all_btn):
            b.setStyleSheet(self.host._glass_btn_css())
            b.setCursor(Qt.PointingHandCursor)
            link_btn_row.addWidget(b)
        link_l.addLayout(link_btn_row)
        lay.addWidget(link_box)
        self.node_preview_chk = QCheckBox("Node output preview")
        self.node_preview_chk.setChecked(bool(self.state.get("nodes_preview", False)))
        lay.addWidget(self.node_preview_chk)
        self.node_preview = QLabel("Select a node to preview partial graph output.")
        self.node_preview.setAlignment(Qt.AlignCenter)
        self.node_preview.setWordWrap(True)
        self.node_preview.setMinimumHeight(124)
        self.node_preview.setStyleSheet(
            "background: rgba(8,12,18,0.78);"
            "border:1px solid rgba(120,168,230,0.24);"
            "border-radius:10px;"
            "color:#9fb3cc;"
            "font-size:11px;"
        )
        lay.addWidget(self.node_preview)
        row = QGridLayout()
        row.setHorizontalSpacing(6)
        row.setVerticalSpacing(6)
        self.node_edit_btn = QPushButton("Edit selected")
        self.node_rem_btn = QPushButton(self._t("editor_remove_node", "Remove node"))
        self.node_up_btn = QPushButton(self._t("editor_move_up", "Up"))
        self.node_down_btn = QPushButton(self._t("editor_move_down", "Down"))
        self.node_save_graph_btn = QPushButton("Save graph")
        self.node_load_graph_btn = QPushButton("Load graph")
        self.node_clear_graph_btn = QPushButton("Clear graph")
        for b in (
            self.node_edit_btn,
            self.node_rem_btn,
            self.node_up_btn,
            self.node_down_btn,
            self.node_save_graph_btn,
            self.node_load_graph_btn,
            self.node_clear_graph_btn,
        ):
            b.setStyleSheet(self.host._glass_btn_css())
            b.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.node_edit_btn, 0, 0)
        row.addWidget(self.node_rem_btn, 0, 1)
        row.addWidget(self.node_up_btn, 0, 2)
        row.addWidget(self.node_down_btn, 1, 0)
        row.addWidget(self.node_save_graph_btn, 1, 1)
        row.addWidget(self.node_load_graph_btn, 1, 2)
        row.addWidget(self.node_clear_graph_btn, 2, 0, 1, 3)
        lay.addLayout(row)
        param_box = QFrame()
        param_box.setStyleSheet("QFrame{background: rgba(255,255,255,0.05); border-radius:10px;}")
        pf = QFormLayout(param_box)
        pf.setLabelAlignment(Qt.AlignLeft)
        self.node_enabled_chk = QCheckBox("Enabled")
        self.node_intensity, self.node_intensity_row = self._slider_with_value(0, 100, 55)
        self.node_radius = QSpinBox()
        self.node_radius.setRange(0, 32)
        self.node_radius.setValue(2)
        self.node_mix, self.node_mix_row = self._slider_with_value(0, 100, 100)
        self.node_value = QSpinBox()
        self.node_value.setRange(-200, 200)
        self.node_value.setValue(0)
        self.node_seed = QSpinBox()
        self.node_seed.setRange(0, 9999)
        self.node_seed.setValue(0)
        self.node_inputs_spin = QSpinBox()
        self.node_inputs_spin.setRange(1, 8)
        self.node_inputs_spin.setValue(1)
        self.node_outputs_spin = QSpinBox()
        self.node_outputs_spin.setRange(1, 8)
        self.node_outputs_spin.setValue(1)
        self.node_input_type_combo = QComboBox()
        self.node_output_type_combo = QComboBox()
        for c in (self.node_input_type_combo, self.node_output_type_combo):
            c.addItems(["video", "audio", "data", "any"])
        pf.addRow(self.node_enabled_chk)
        pf.addRow("Intensity:", self.node_intensity_row)
        pf.addRow("Radius:", self.node_radius)
        pf.addRow("Mix:", self.node_mix_row)
        pf.addRow("Value:", self.node_value)
        pf.addRow("Seed:", self.node_seed)
        pf.addRow("Inputs:", self.node_inputs_spin)
        pf.addRow("Outputs:", self.node_outputs_spin)
        pf.addRow("In type:", self.node_input_type_combo)
        pf.addRow("Out type:", self.node_output_type_combo)
        lay.addWidget(param_box)
        self.nodes_code = QTextEdit()
        self.nodes_code.setPlaceholderText("def process(image, t_ms, state):\n    return image")
        self.nodes_code.setMinimumHeight(170)
        lay.addWidget(self.nodes_code, 1)
        srow = QHBoxLayout()
        self.script_load_btn = QPushButton(self._t("editor_load_script", "Load script"))
        self.script_save_btn = QPushButton(self._t("editor_save_script", "Save script"))
        self.node_workspace_btn = QPushButton("Open node workspace")
        for b in (self.script_load_btn, self.script_save_btn):
            b.setStyleSheet(self.host._glass_btn_css())
            b.setCursor(Qt.PointingHandCursor)
            srow.addWidget(b)
        self.node_workspace_btn.setStyleSheet(self.host._glass_btn_css())
        self.node_workspace_btn.setCursor(Qt.PointingHandCursor)
        srow.addWidget(self.node_workspace_btn)
        lay.addLayout(srow)
        hint2 = QLabel("Shortcuts: Tab add node, V/C/T/R tools, Space play/pause, Ctrl+B split, Ctrl+D duplicate, Ctrl+R speed, Ctrl+G group, Ctrl+Shift+G ungroup, Del remove.")
        hint2.setStyleSheet("font-size:11px; color:#9fb3cc;")
        lay.addWidget(hint2)
        lay.addStretch(1)
        self.tabs.addTab(tab, self._t("editor_nodes", "Nodes"))

    def _node_catalog(self):
        return [
            ("Video", "Source In", "video-in"),
            ("Video", "Source Out", "video-out"),
            ("Color", "Brightness", "brightness-node"),
            ("Color", "Contrast", "contrast-node"),
            ("Color", "Saturation", "saturation-node"),
            ("Color", "Hue Shift", "hue-shift"),
            ("Color", "Gamma", "gamma-node"),
            ("Color", "Auto Contrast", "autocontrast"),
            ("Color", "Equalize", "equalize"),
            ("Filter", "Blur", "blur"),
            ("Filter", "Sharpen", "sharpen"),
            ("Filter", "Median Denoise", "median-denoise"),
            ("Filter", "Motion Blur", "motion-blur"),
            ("Stylize", "Edge", "edge"),
            ("Stylize", "Emboss", "emboss"),
            ("Stylize", "Posterize", "posterize"),
            ("Stylize", "Invert", "invert"),
            ("Stylize", "Grayscale", "grayscale"),
            ("Stylize", "Solarize", "solarize"),
            ("Stylize", "Pixelate", "pixelate"),
            ("Stylize", "Glitch Lite", "glitch-lite"),
            ("Stylize", "Vignette", "vignette"),
            ("Stylize", "Bloom Lite", "bloom-lite"),
            ("Stylize", "Threshold", "threshold"),
            ("Stylize", "Noise", "noise"),
            ("Stylize", "Channel Shift", "channel-shift"),
            ("Audio", "Audio Input", "audio-in"),
            ("Audio", "Audio Gain", "audio-gain"),
            ("Audio", "Audio Lowpass", "audio-lowpass"),
            ("Audio", "Audio Analyzer", "audio-analyzer"),
            ("Data", "Value", "value-node"),
            ("Data", "Math Add", "math-add"),
            ("Logic", "Switch", "switch-node"),
            ("Logic", "If", "if-node"),
            ("Logic", "Python Script", "python-script"),
            ("Utility", "Bypass", "bypass"),
        ]

    def _populate_node_picker(self):
        fam = "all"
        query = ""
        try:
            fam = str(self.node_family_combo.currentText() or "All").strip().lower()
        except Exception:
            pass
        try:
            query = str(self.node_search.text() or "").strip().lower()
        except Exception:
            pass
        current = str(self.node_combo.currentData() or "").strip().lower() if hasattr(self, "node_combo") else ""
        self.node_combo.blockSignals(True)
        self.node_combo.clear()
        for cat, label, nid in (self.node_catalog or []):
            cc = str(cat or "").strip().lower()
            ll = str(label or "").strip()
            nn = str(nid or "").strip()
            if fam not in ("", "all") and cc != fam:
                continue
            hay = f"{ll} {nn} {cat}".lower()
            if query and query not in hay:
                continue
            self.node_combo.addItem(f"{ll}  [{cat}]", nn)
        self.node_combo.blockSignals(False)
        if self.node_combo.count() == 0:
            self.node_combo.addItem("No nodes", "")
            if hasattr(self, "node_add_btn"):
                self.node_add_btn.setEnabled(False)
            return
        if hasattr(self, "node_add_btn"):
            self.node_add_btn.setEnabled(True)
        idx = self.node_combo.findData(current)
        self.node_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._update_node_desc()

    def _node_descriptions(self):
        return {
            "video-in": "Video source entry node. Produces video stream for graph start.",
            "video-out": "Video output node. Receives final composited video stream.",
            "brightness-node": "Adjusts luminance using Intensity + Value offset. Use Mix to blend.",
            "contrast-node": "Expands or compresses local contrast. Value controls extra gain.",
            "saturation-node": "Color intensity control; useful for muted/cinematic looks.",
            "hue-shift": "Shifts hue wheel. Value is signed hue offset in degrees.",
            "gamma-node": "Gamma correction for highlights/shadows balance.",
            "autocontrast": "Stretches histogram to full range.",
            "equalize": "Histogram equalization for flat images.",
            "blur": "Gaussian blur. Smooths details; radius controls spread.",
            "sharpen": "Unsharp mask. Adds local contrast to details.",
            "median-denoise": "Median denoise for compression artifacts and speckles.",
            "motion-blur": "Directional streak-like blur by shifting and blending.",
            "edge": "Edge extraction mixed with source image.",
            "posterize": "Reduces color levels for stylized look.",
            "invert": "Color inversion blended with original.",
            "emboss": "Embossed relief shading effect.",
            "grayscale": "Desaturates to grayscale, mixed with original.",
            "solarize": "Inverts bright ranges above threshold value.",
            "pixelate": "Blocky pixel-art style. Radius controls block size.",
            "glitch-lite": "Light chroma/scanline glitch for stylization.",
            "vignette": "Darkens edges and keeps focus in center.",
            "bloom-lite": "Soft glow by blending blurred highlights.",
            "threshold": "High-contrast threshold pass blended with source.",
            "noise": "Film-grain style noise texture.",
            "channel-shift": "Offsets RGB channels for chromatic split.",
            "audio-in": "Audio source entry node (audio stream).",
            "audio-gain": "Audio gain stage (audio -> audio).",
            "audio-lowpass": "Audio low-pass stage placeholder.",
            "audio-analyzer": "Converts audio stream to data channels.",
            "value-node": "Generates scalar data output.",
            "math-add": "Adds data channels/constants.",
            "switch-node": "Switches active input by control value.",
            "if-node": "Conditional routing for data logic.",
            "python-script": "Custom script node. Supports video/audio/data pipelines.",
            "bypass": "Pass-through node for routing and testing graph branches.",
        }

    def _update_node_desc(self):
        if not hasattr(self, "node_desc_lbl"):
            return
        nid = str(self.node_combo.currentData() or "").strip().lower()
        txt = self._node_descriptions().get(nid, "")
        self.node_desc_lbl.setText(txt)

    def _sync_from_state(self):
        s = self.state
        self._ui_lock = True
        try:
            self.time_slider.setValue(int(max(0, min(self.duration_ms, int(self.host._editor_last_preview_ms or 0)))))
            self.time_spin.setValue(self.time_slider.value())
            for k, sl in self.fx_ctrl.items():
                sl.setValue(int(s.get(k, 100 if k in ("brightness", "contrast", "saturation", "sharpness") else 0)))
            self.crop_enable.setChecked(bool(s.get("crop_enabled", False)))
            self.crop_x.setValue(int(s.get("crop_x", 0))); self.crop_y.setValue(int(s.get("crop_y", 0)))
            self.crop_w.setValue(int(s.get("crop_w", self.src.width))); self.crop_h.setValue(int(s.get("crop_h", self.src.height)))
            self.mask_enable.setChecked(bool(s.get("mask_enabled", False)))
            self.mask_x.setValue(int(s.get("mask_x", 0))); self.mask_y.setValue(int(s.get("mask_y", 0)))
            self.mask_w.setValue(int(s.get("mask_w", self.src.width))); self.mask_h.setValue(int(s.get("mask_h", self.src.height)))
            self.mask_use_image_chk.setChecked(bool(s.get("mask_use_image", False)))
            self.mask_media_path.setText(str(s.get("mask_image_path", "") or ""))
            self.trim_enable.setChecked(bool(s.get("trim_enabled", False)))
            self.trim_start.setValue(int(s.get("trim_start_ms", 0))); self.trim_end.setValue(int(s.get("trim_end_ms", self.duration_ms)))
            self.trim_start_slider.setValue(self.trim_start.value()); self.trim_end_slider.setValue(self.trim_end.value())
            self.audio_path_lbl.setText(str(s.get("audio_path", "") or "-"))
            self.audio_gain.setValue(int(round(float(s.get("audio_gain_db", 0.0) or 0.0))))
            self.audio_low.setValue(int(s.get("audio_lowpass_hz", 0) or 0))
            self.nodes_enable.setChecked(bool(s.get("nodes_enabled", False)))
            if hasattr(self, "node_preview_chk"):
                self.node_preview_chk.setChecked(bool(s.get("nodes_preview", False)))
            self.nodes_code.setPlainText(str(s.get("nodes_code", "") or ""))
            self._update_node_desc()
            self._refresh_layers()
            self._refresh_media_layers()
            self._refresh_nodes()
            self._load_node_param_controls()
            self._update_node_preview_visibility()
            self._load_layer_controls()
            self._load_media_layer_controls()
            self._load_ascii_bridge_controls()
            self._refresh_timeline_view()
            self._update_preview_hint()
            if bool(self.photo_mode):
                self._load_photo_paint_state()
        finally:
            self._ui_lock = False
        self._schedule_node_preview(30)

    def _refresh_layers(self, select_idx=None):
        cur = self.layers_list.currentRow()
        if select_idx is None:
            select_idx = cur if cur >= 0 else 0
        self.layers_list.clear()
        for i, layer in enumerate(self.state.get("text_layers", [])):
            txt = str((layer or {}).get("text", "") or "").strip() or f"Layer {i + 1}"
            t0 = int((layer or {}).get("start_ms", 0) or 0)
            t1 = int((layer or {}).get("end_ms", self.duration_ms) or self.duration_ms)
            name = f"T{i + 1}  {txt[:20]}   [{t0/1000:.1f}s-{t1/1000:.1f}s]"
            it = QListWidgetItem(name)
            if not bool((layer or {}).get("enabled", True)):
                it.setForeground(QColor("#6d7484"))
            self.layers_list.addItem(it)
        if self.layers_list.count() > 0:
            self.layers_list.setCurrentRow(max(0, min(self.layers_list.count() - 1, int(select_idx))))
        self._refresh_timeline_view()

    def _selected_layer(self):
        idx = self.layers_list.currentRow()
        arr = self.state.get("text_layers", [])
        if idx < 0 or idx >= len(arr):
            return None, -1
        return arr[idx], idx

    def _load_layer_controls(self):
        layer, _ = self._selected_layer()
        self._ui_lock = True
        try:
            widgets = (
                self.lyr_enabled, self.lyr_text, self.lyr_font, self.lyr_size, self.lyr_x, self.lyr_y,
                self.lyr_x1, self.lyr_y1, self.lyr_start, self.lyr_end, self.lyr_ease,
                self.lyr_bx1, self.lyr_by1, self.lyr_bx2, self.lyr_by2, self.lyr_sx, self.lyr_sy,
                self.lyr_alpha, self.lyr_color_btn,
            )
            has = layer is not None
            for w in widgets:
                w.setEnabled(has)
            if not has:
                return
            self.lyr_enabled.setChecked(bool(layer.get("enabled", True)))
            self.lyr_text.setText(str(layer.get("text", "") or ""))
            self.lyr_size.setValue(int(layer.get("size", 36)))
            self.lyr_x.setValue(int(layer.get("x", 0))); self.lyr_y.setValue(int(layer.get("y", 0)))
            self.lyr_x1.setValue(int(layer.get("x1", layer.get("x", 0))))
            self.lyr_y1.setValue(int(layer.get("y1", layer.get("y", 0))))
            self.lyr_start.setValue(int(layer.get("start_ms", 0)))
            self.lyr_end.setValue(int(layer.get("end_ms", self.duration_ms)))
            ease = str(layer.get("anim_ease", "linear") or "linear")
            j = self.lyr_ease.findText(ease)
            self.lyr_ease.setCurrentIndex(j if j >= 0 else 0)
            bz = layer.get("anim_bezier", [0.25, 0.1, 0.25, 1.0])
            if not isinstance(bz, (list, tuple)) or len(bz) < 4:
                bz = [0.25, 0.1, 0.25, 1.0]
            self.lyr_bx1.setValue(float(bz[0])); self.lyr_by1.setValue(float(bz[1]))
            self.lyr_bx2.setValue(float(bz[2])); self.lyr_by2.setValue(float(bz[3]))
            self.lyr_sx.setValue(int(round(float(layer.get("scale_x", 1.0)) * 100)))
            self.lyr_sy.setValue(int(round(float(layer.get("scale_y", 1.0)) * 100)))
            rgba = layer.get("color_rgba", (255, 255, 255, 220))
            self.lyr_alpha.setValue(int(rgba[3]))
            self._set_color_btn(self.lyr_color_btn, rgba)
            try:
                self.lyr_font.setCurrentFont(QFont(str(layer.get("font", "Arial") or "Arial")))
            except Exception:
                pass
        finally:
            self._ui_lock = False

    def _save_layer_controls(self):
        if self._ui_lock:
            return
        layer, idx = self._selected_layer()
        if layer is None:
            return
        layer["enabled"] = bool(self.lyr_enabled.isChecked())
        layer["text"] = str(self.lyr_text.text() or "")
        layer["font"] = str(self.lyr_font.currentFont().family() or "Arial")
        layer["size"] = int(self.lyr_size.value())
        layer["x"] = int(self.lyr_x.value()); layer["y"] = int(self.lyr_y.value())
        layer["x1"] = int(self.lyr_x1.value()); layer["y1"] = int(self.lyr_y1.value())
        layer["start_ms"] = int(max(0, min(self.duration_ms, self.lyr_start.value())))
        layer["end_ms"] = int(max(layer["start_ms"], min(self.duration_ms, self.lyr_end.value())))
        ai = int(layer.get("anim_in_ms", layer["start_ms"]) or layer["start_ms"])
        ao = int(layer.get("anim_out_ms", layer["end_ms"]) or layer["end_ms"])
        layer["anim_in_ms"] = max(int(layer["start_ms"]), min(int(layer["end_ms"]), ai))
        layer["anim_out_ms"] = max(int(layer["anim_in_ms"]), min(int(layer["end_ms"]), ao))
        layer["anim_ease"] = str(self.lyr_ease.currentText() or "linear").strip().lower()
        layer["anim_bezier"] = [
            float(self.lyr_bx1.value()),
            float(self.lyr_by1.value()),
            float(self.lyr_bx2.value()),
            float(self.lyr_by2.value()),
        ]
        layer["scale_x"] = max(0.1, min(8.0, float(self.lyr_sx.value()) / 100.0))
        layer["scale_y"] = max(0.1, min(8.0, float(self.lyr_sy.value()) / 100.0))
        col = layer.get("color_rgba", (255, 255, 255, 220))
        layer["color_rgba"] = (int(col[0]), int(col[1]), int(col[2]), int(self.lyr_alpha.value()))
        self._refresh_single_layer_row(idx)

    def _refresh_single_layer_row(self, idx):
        try:
            arr = self.state.get("text_layers", []) or []
            i = int(idx)
            if i < 0 or i >= len(arr) or i >= self.layers_list.count():
                return
            layer = arr[i]
            txt = str((layer or {}).get("text", "") or "").strip() or f"Layer {i + 1}"
            t0 = int((layer or {}).get("start_ms", 0) or 0)
            t1 = int((layer or {}).get("end_ms", self.duration_ms) or self.duration_ms)
            name = f"T{i + 1}  {txt[:20]}   [{t0/1000:.1f}s-{t1/1000:.1f}s]"
            it = self.layers_list.item(i)
            if it is not None:
                it.setText(name)
                it.setForeground(QColor("#6d7484") if not bool((layer or {}).get("enabled", True)) else QColor("#dfe8f6"))
        except Exception:
            pass
        self._refresh_timeline_view()

    def _refresh_media_layers(self, select_idx=None):
        cur = self.media_list.currentRow()
        if select_idx is None:
            select_idx = cur if cur >= 0 else 0
        self.media_list.clear()
        for i, layer in enumerate(self.state.get("media_layers", [])):
            p = str((layer or {}).get("path", "") or "").strip()
            typ = str((layer or {}).get("type", "image") or "image").upper()
            name = os.path.basename(p) if p else f"Media {i + 1}"
            t0 = int((layer or {}).get("start_ms", 0) or 0)
            t1 = int((layer or {}).get("end_ms", self.duration_ms) or self.duration_ms)
            full = f"M{i + 1} {typ}  {name[:18]}   [{t0/1000:.1f}s-{t1/1000:.1f}s]"
            it = QListWidgetItem(full)
            if not bool((layer or {}).get("enabled", True)):
                it.setForeground(QColor("#6d7484"))
            self.media_list.addItem(it)
        if self.media_list.count() > 0:
            self.media_list.setCurrentRow(max(0, min(self.media_list.count() - 1, int(select_idx))))
        self._refresh_media_bin()
        self._refresh_timeline_view()

    def _selected_media_layer(self):
        idx = self.media_list.currentRow()
        arr = self.state.get("media_layers", [])
        if idx < 0 or idx >= len(arr):
            return None, -1
        return arr[idx], idx

    def _load_media_layer_controls(self):
        layer, _ = self._selected_media_layer()
        self._ui_lock = True
        try:
            widgets = (
                self.med_enabled, self.med_path, self.med_type, self.med_x, self.med_y, self.med_x1, self.med_y1,
                self.med_sx, self.med_sy, self.med_alpha, self.med_start, self.med_end, self.med_speed, self.med_ease,
                self.med_bx1, self.med_by1, self.med_bx2, self.med_by2, self.med_blend,
            )
            has = layer is not None
            for w in widgets:
                w.setEnabled(has)
            if not has:
                return
            self.med_enabled.setChecked(bool(layer.get("enabled", True)))
            self.med_path.setText(str(layer.get("path", "") or ""))
            mt = str(layer.get("type", "image") or "image")
            j = self.med_type.findData(mt)
            self.med_type.setCurrentIndex(j if j >= 0 else 0)
            self.med_x.setValue(int(layer.get("x", 0))); self.med_y.setValue(int(layer.get("y", 0)))
            self.med_x1.setValue(int(layer.get("x1", layer.get("x", 0))))
            self.med_y1.setValue(int(layer.get("y1", layer.get("y", 0))))
            self.med_sx.setValue(int(round(float(layer.get("scale_x", 1.0)) * 100)))
            self.med_sy.setValue(int(round(float(layer.get("scale_y", 1.0)) * 100)))
            self.med_alpha.setValue(int(layer.get("alpha", 255)))
            self.med_start.setValue(int(layer.get("start_ms", 0)))
            self.med_end.setValue(int(layer.get("end_ms", self.duration_ms)))
            self.med_speed.setValue(float(layer.get("speed", 1.0) or 1.0))
            ease = str(layer.get("anim_ease", "linear") or "linear")
            j = self.med_ease.findText(ease)
            self.med_ease.setCurrentIndex(j if j >= 0 else 0)
            bz = layer.get("anim_bezier", [0.25, 0.1, 0.25, 1.0])
            if not isinstance(bz, (list, tuple)) or len(bz) < 4:
                bz = [0.25, 0.1, 0.25, 1.0]
            self.med_bx1.setValue(float(bz[0])); self.med_by1.setValue(float(bz[1]))
            self.med_bx2.setValue(float(bz[2])); self.med_by2.setValue(float(bz[3]))
            self.med_blend.setCurrentText(str(layer.get("blend", "normal") or "normal"))
        finally:
            self._ui_lock = False

    def _save_media_layer_controls(self):
        if self._ui_lock:
            return
        layer, idx = self._selected_media_layer()
        if layer is None:
            return
        layer["enabled"] = bool(self.med_enabled.isChecked())
        layer["path"] = str(self.med_path.text() or "")
        layer["type"] = str(self.med_type.currentData() or self.med_type.currentText() or "image")
        layer["x"] = int(self.med_x.value()); layer["y"] = int(self.med_y.value())
        layer["x1"] = int(self.med_x1.value()); layer["y1"] = int(self.med_y1.value())
        layer["scale_x"] = max(0.05, min(8.0, float(self.med_sx.value()) / 100.0))
        layer["scale_y"] = max(0.05, min(8.0, float(self.med_sy.value()) / 100.0))
        layer["alpha"] = max(0, min(255, int(self.med_alpha.value())))
        layer["start_ms"] = int(max(0, min(self.duration_ms, self.med_start.value())))
        layer["end_ms"] = int(max(layer["start_ms"], min(self.duration_ms, self.med_end.value())))
        layer["speed"] = max(0.05, min(16.0, float(self.med_speed.value())))
        ai = int(layer.get("anim_in_ms", layer["start_ms"]) or layer["start_ms"])
        ao = int(layer.get("anim_out_ms", layer["end_ms"]) or layer["end_ms"])
        layer["anim_in_ms"] = max(int(layer["start_ms"]), min(int(layer["end_ms"]), ai))
        layer["anim_out_ms"] = max(int(layer["anim_in_ms"]), min(int(layer["end_ms"]), ao))
        layer["anim_ease"] = str(self.med_ease.currentText() or "linear").strip().lower()
        layer["anim_bezier"] = [
            float(self.med_bx1.value()),
            float(self.med_by1.value()),
            float(self.med_bx2.value()),
            float(self.med_by2.value()),
        ]
        layer["blend"] = str(self.med_blend.currentText() or "normal")
        self._refresh_single_media_row(idx)

    def _refresh_single_media_row(self, idx):
        try:
            arr = self.state.get("media_layers", []) or []
            i = int(idx)
            if i < 0 or i >= len(arr) or i >= self.media_list.count():
                return
            layer = arr[i]
            p = str((layer or {}).get("path", "") or "").strip()
            typ = str((layer or {}).get("type", "image") or "image").upper()
            name = os.path.basename(p) if p else f"Media {i + 1}"
            t0 = int((layer or {}).get("start_ms", 0) or 0)
            t1 = int((layer or {}).get("end_ms", self.duration_ms) or self.duration_ms)
            full = f"M{i + 1} {typ}  {name[:18]}   [{t0/1000:.1f}s-{t1/1000:.1f}s]"
            it = self.media_list.item(i)
            if it is not None:
                it.setText(full)
                it.setForeground(QColor("#6d7484") if not bool((layer or {}).get("enabled", True)) else QColor("#dfe8f6"))
        except Exception:
            pass
        self._refresh_timeline_view()

    def _add_media_layer(self):
        arr = self.state.setdefault("media_layers", [])
        arr.append(self._default_media_layer(len(arr)))
        self._refresh_media_layers(select_idx=len(arr) - 1)
        self._load_media_layer_controls()
        self._render_preview()

    def _add_media_layer_and_pick(self):
        self._add_media_layer()
        self._pick_media_layer_path()

    def _remove_media_layer(self):
        layer, idx = self._selected_media_layer()
        if layer is None or idx < 0:
            return
        self.state["media_layers"].pop(idx)
        self._refresh_media_layers(select_idx=max(0, idx - 1))
        self._load_media_layer_controls()
        self._render_preview()

    def _pick_media_layer_path(self):
        layer, _ = self._selected_media_layer()
        if layer is None:
            return
        fn, _ = QFileDialog.getOpenFileName(
            self,
            self._t("editor_pick_media", "Choose media"),
            os.getcwd(),
            "Media (*.png *.jpg *.jpeg *.bmp *.gif *.mp4 *.mov *.avi *.mkv *.webm)",
        )
        if not fn:
            return
        layer["path"] = fn
        low = fn.lower()
        if low.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm")):
            layer["type"] = "video"
        elif low.endswith(".gif"):
            layer["type"] = "gif"
        else:
            layer["type"] = "image"
        self._load_media_layer_controls()
        self._refresh_media_layers()
        self._render_preview()

    def _pick_mask_media_path(self):
        fn, _ = QFileDialog.getOpenFileName(
            self,
            "Choose mask media",
            os.getcwd(),
            "Media (*.png *.jpg *.jpeg *.bmp *.gif *.mp4 *.mov *.avi *.mkv *.webm)",
        )
        if not fn:
            return
        self.mask_media_path.setText(fn)
        self.mask_use_image_chk.setChecked(True)
        self.mask_enable.setChecked(True)
        self._render_preview()

    def _clear_mask_media_path(self):
        self.mask_media_path.setText("")
        self.mask_use_image_chk.setChecked(False)
        self._render_preview()

    def _set_media_start_keyframe(self):
        layer, idx = self._selected_media_layer()
        if layer is None or idx < 0:
            return
        t = int(self.time_slider.value())
        layer["x"] = int(self.med_x.value())
        layer["y"] = int(self.med_y.value())
        layer["start_ms"] = max(0, min(int(layer.get("end_ms", self.duration_ms)), t))
        layer["anim_in_ms"] = int(layer["start_ms"])
        layer["anim_out_ms"] = max(int(layer["anim_in_ms"]), int(layer.get("anim_out_ms", layer.get("end_ms", self.duration_ms)) or layer.get("end_ms", self.duration_ms)))
        layer["anim_out_ms"] = min(int(layer.get("end_ms", self.duration_ms)), int(layer["anim_out_ms"]))
        self._load_media_layer_controls()
        self._refresh_media_layers(select_idx=idx)
        self._render_preview()

    def _set_media_end_keyframe(self):
        layer, idx = self._selected_media_layer()
        if layer is None or idx < 0:
            return
        t = int(self.time_slider.value())
        layer["x1"] = int(self.med_x1.value())
        layer["y1"] = int(self.med_y1.value())
        layer["end_ms"] = max(int(layer.get("start_ms", 0)), min(self.duration_ms, t))
        layer["anim_out_ms"] = int(layer["end_ms"])
        layer["anim_in_ms"] = min(int(layer["anim_out_ms"]), int(layer.get("anim_in_ms", layer.get("start_ms", 0)) or layer.get("start_ms", 0)))
        layer["anim_in_ms"] = max(int(layer.get("start_ms", 0)), int(layer["anim_in_ms"]))
        self._load_media_layer_controls()
        self._refresh_media_layers(select_idx=idx)
        self._render_preview()

    def _set_selected_start_keyframe(self):
        k, _, _ = self._selected_clip_ref()
        if k == "M":
            self._set_media_start_keyframe()
            return
        self._set_layer_start_keyframe()

    def _set_selected_end_keyframe(self):
        k, _, _ = self._selected_clip_ref()
        if k == "M":
            self._set_media_end_keyframe()
            return
        self._set_layer_end_keyframe()

    def _refresh_nodes(self):
        self._ensure_node_params()
        self._ensure_node_io()
        sel = self.node_list.currentRow()
        self.node_list.clear()
        chain = (self.state.get("node_chain", []) or [])
        for i, node in enumerate(chain):
            txt = str(node).strip()
            if not txt:
                continue
            prm = (self.state.get("node_params", []) or [])
            io = (self.state.get("node_io", []) or [])
            en = True
            intensity = 55
            mix = 100
            inc = 1
            outc = 1
            if i < len(prm) and isinstance(prm[i], dict):
                en = bool(prm[i].get("enabled", True))
                intensity = int(prm[i].get("intensity", 55) or 55)
                mix = int(prm[i].get("mix", 100) or 100)
            if i < len(io) and isinstance(io[i], dict):
                inc = int(io[i].get("inputs", 1) or 1)
                outc = int(io[i].get("outputs", 1) or 1)
                in_t = str((io[i].get("in_types", [io[i].get("input_type", "video")]) or ["video"])[0])
                out_t = str((io[i].get("out_types", [io[i].get("output_type", "video")]) or ["video"])[0])
            else:
                in_t = "video"
                out_t = "video"
            label = f"{txt}  ({intensity}%/{mix}%mix)  {inc}in/{outc}out  [{in_t}->{out_t}]"
            if not en:
                label = "[OFF] " + label
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, txt)
            if not en:
                it.setForeground(QColor("#6d7484"))
            self.node_list.addItem(it)
        if self.node_list.count() > 0:
            self.node_list.setCurrentRow(max(0, min(self.node_list.count() - 1, int(sel if sel >= 0 else 0))))
        try:
            self.node_graph.set_graph(chain, self.state.get("node_links", []) or [], self.state.get("node_io", []) or [])
            self.state["node_links"] = [list(x) for x in (self.node_graph.links or [])]
        except Exception:
            pass
        self._refresh_node_port_inspector()
        self._schedule_node_preview(40)

    def _ensure_node_params(self):
        chain = self.state.get("node_chain", []) or []
        arr = self.state.get("node_params", [])
        if not isinstance(arr, list):
            arr = []
        out = []
        for i, nid in enumerate(chain):
            d = self._default_node_params(nid)
            if i < len(arr) and isinstance(arr[i], dict):
                d.update(arr[i])
            d["enabled"] = bool(d.get("enabled", True))
            d["intensity"] = max(0, min(100, int(d.get("intensity", 55) or 55)))
            d["radius"] = max(0, min(32, int(d.get("radius", 2) or 2)))
            d["mix"] = max(0, min(100, int(d.get("mix", 100) or 100)))
            d["value"] = max(-200, min(200, int(d.get("value", 0) or 0)))
            d["seed"] = max(0, min(9999, int(d.get("seed", 0) or 0)))
            out.append(d)
        self.state["node_params"] = out

    def _ensure_node_io(self):
        chain = self.state.get("node_chain", []) or []
        arr = self.state.get("node_io", [])
        if not isinstance(arr, list):
            arr = []
        out = []
        for i, nid in enumerate(chain):
            d = dict(self._default_node_io(nid))
            if i < len(arr) and isinstance(arr[i], dict):
                try:
                    d["inputs"] = max(1, min(8, int(arr[i].get("inputs", 1) or 1)))
                    d["outputs"] = max(1, min(8, int(arr[i].get("outputs", 1) or 1)))
                except Exception:
                    pass
                in_types = arr[i].get("in_types", arr[i].get("input_type", d.get("in_types", ["video"])))
                out_types = arr[i].get("out_types", arr[i].get("output_type", d.get("out_types", ["video"])))
                if not isinstance(in_types, list):
                    in_types = [in_types]
                if not isinstance(out_types, list):
                    out_types = [out_types]
            else:
                in_types = d.get("in_types", ["video"])
                out_types = d.get("out_types", ["video"])
            in_norm = []
            out_norm = []
            for t in in_types:
                tv = str(t or "").strip().lower()
                if tv not in ("video", "audio", "data", "any"):
                    tv = "video"
                in_norm.append(tv)
            for t in out_types:
                tv = str(t or "").strip().lower()
                if tv not in ("video", "audio", "data", "any"):
                    tv = "video"
                out_norm.append(tv)
            if not in_norm:
                in_norm = [str(d.get("in_types", ["video"])[0])]
            if not out_norm:
                out_norm = [str(d.get("out_types", ["video"])[0])]
            while len(in_norm) < int(d["inputs"]):
                in_norm.append(in_norm[-1])
            while len(out_norm) < int(d["outputs"]):
                out_norm.append(out_norm[-1])
            d["in_types"] = in_norm[: int(d["inputs"])]
            d["out_types"] = out_norm[: int(d["outputs"])]
            d["input_type"] = str(d["in_types"][0])
            d["output_type"] = str(d["out_types"][0])
            out.append(d)
        self.state["node_io"] = out

    def _selected_node(self):
        idx = self.node_list.currentRow()
        chain = self.state.get("node_chain", []) or []
        if idx < 0 or idx >= len(chain):
            return None, -1
        return str(chain[idx]), int(idx)

    def _node_port_type_from_state(self, idx, side="out"):
        io_arr = self.state.get("node_io", []) or []
        if idx < 0 or idx >= len(io_arr) or not isinstance(io_arr[idx], dict):
            return "video"
        io = io_arr[idx]
        if str(side) == "in":
            arr = io.get("in_types", [io.get("input_type", "video")]) or ["video"]
        else:
            arr = io.get("out_types", [io.get("output_type", "video")]) or ["video"]
        t = str(arr[0] if arr else "video").strip().lower()
        if t not in ("video", "audio", "data", "any"):
            return "video"
        return t

    def _node_ports_compatible_state(self, src_idx, dst_idx):
        a = self._node_port_type_from_state(int(src_idx), "out")
        b = self._node_port_type_from_state(int(dst_idx), "in")
        return a == "any" or b == "any" or a == b

    def _load_node_param_controls(self):
        self._ensure_node_params()
        self._ensure_node_io()
        _, idx = self._selected_node()
        has = idx >= 0
        self._ui_lock = True
        try:
            for w in (
                self.node_enabled_chk,
                self.node_intensity,
                self.node_radius,
                self.node_mix,
                self.node_value,
                self.node_seed,
                self.node_inputs_spin,
                self.node_outputs_spin,
                self.node_input_type_combo,
                self.node_output_type_combo,
            ):
                w.setEnabled(has)
            if not has:
                return
            p = (self.state.get("node_params", []) or [])[idx]
            io = (self.state.get("node_io", []) or [])[idx]
            self.node_enabled_chk.setChecked(bool(p.get("enabled", True)))
            self.node_intensity.setValue(int(p.get("intensity", 55)))
            self.node_radius.setValue(int(p.get("radius", 2)))
            self.node_mix.setValue(int(p.get("mix", 100)))
            self.node_value.setValue(int(p.get("value", 0)))
            self.node_seed.setValue(int(p.get("seed", 0)))
            self.node_inputs_spin.setValue(int(io.get("inputs", 1)))
            self.node_outputs_spin.setValue(int(io.get("outputs", 1)))
            in_types = io.get("in_types", [io.get("input_type", "video")]) or ["video"]
            out_types = io.get("out_types", [io.get("output_type", "video")]) or ["video"]
            in_type = str(in_types[0]).strip().lower()
            out_type = str(out_types[0]).strip().lower()
            ii = self.node_input_type_combo.findText(in_type)
            oi = self.node_output_type_combo.findText(out_type)
            self.node_input_type_combo.setCurrentIndex(ii if ii >= 0 else 0)
            self.node_output_type_combo.setCurrentIndex(oi if oi >= 0 else 0)
        finally:
            self._ui_lock = False

    def _save_node_param_controls(self):
        if self._ui_lock:
            return
        self._ensure_node_params()
        self._ensure_node_io()
        _, idx = self._selected_node()
        if idx < 0:
            return
        p = (self.state.get("node_params", []) or [])[idx]
        io = (self.state.get("node_io", []) or [])[idx]
        p["enabled"] = bool(self.node_enabled_chk.isChecked())
        p["intensity"] = int(self.node_intensity.value())
        p["radius"] = int(self.node_radius.value())
        p["mix"] = int(self.node_mix.value())
        p["value"] = int(self.node_value.value())
        p["seed"] = int(self.node_seed.value())
        io["inputs"] = int(self.node_inputs_spin.value())
        io["outputs"] = int(self.node_outputs_spin.value())
        in_t = str(self.node_input_type_combo.currentText() or "video").strip().lower()
        out_t = str(self.node_output_type_combo.currentText() or "video").strip().lower()
        if in_t not in ("video", "audio", "data", "any"):
            in_t = "video"
        if out_t not in ("video", "audio", "data", "any"):
            out_t = "video"
        io["in_types"] = [in_t for _ in range(max(1, int(io["inputs"])))]
        io["out_types"] = [out_t for _ in range(max(1, int(io["outputs"])))]
        io["input_type"] = in_t
        io["output_type"] = out_t

    def _pull_state_from_widgets(self):
        for k, sl in self.fx_ctrl.items():
            self.state[k] = int(sl.value())
        self.state["crop_enabled"] = bool(self.crop_enable.isChecked())
        self.state["crop_x"], self.state["crop_y"], self.state["crop_w"], self.state["crop_h"] = self._clamp_rect(
            self.crop_x.value(), self.crop_y.value(), self.crop_w.value(), self.crop_h.value()
        )
        self.state["mask_enabled"] = bool(self.mask_enable.isChecked())
        self.state["mask_x"], self.state["mask_y"], self.state["mask_w"], self.state["mask_h"] = self._clamp_rect(
            self.mask_x.value(), self.mask_y.value(), self.mask_w.value(), self.mask_h.value()
        )
        self.state["mask_use_image"] = bool(self.mask_use_image_chk.isChecked())
        self.state["mask_image_path"] = str(self.mask_media_path.text() or "")
        self.state["trim_enabled"] = bool(self.trim_enable.isChecked())
        self.state["trim_start_ms"] = int(max(0, min(self.duration_ms, self.trim_start.value())))
        self.state["trim_end_ms"] = int(max(self.state["trim_start_ms"], min(self.duration_ms, self.trim_end.value())))
        self.state["audio_gain_db"] = float(self.audio_gain.value())
        self.state["audio_lowpass_hz"] = int(self.audio_low.value())
        self.state["nodes_enabled"] = bool(self.nodes_enable.isChecked())
        self.state["nodes_preview"] = bool(self.node_preview_chk.isChecked()) if hasattr(self, "node_preview_chk") else bool(self.state.get("nodes_preview", False))
        self.state["nodes_code"] = str(self.nodes_code.toPlainText() or "")
        if bool(self.photo_mode):
            self.state["photo_paint_enabled"] = bool(self.photo_paint_enable_chk.isChecked()) if hasattr(self, "photo_paint_enable_chk") else bool(self.state.get("photo_paint_enabled", False))
            self.state["photo_paint_opacity"] = int(self.photo_paint_opacity_slider.value()) if hasattr(self, "photo_paint_opacity_slider") else int(self.state.get("photo_paint_opacity", 100))
            self.state["photo_brush_size"] = int(self.photo_brush_size_slider.value()) if hasattr(self, "photo_brush_size_slider") else int(self.state.get("photo_brush_size", 26))
            self.state["photo_brush_opacity"] = int(self.photo_brush_opacity_slider.value()) if hasattr(self, "photo_brush_opacity_slider") else int(self.state.get("photo_brush_opacity", 92))
            self.state["photo_brush_color_rgba"] = list(getattr(self, "_photo_brush_rgba", (236, 244, 255, 220)))
            if bool(getattr(self, "_photo_paint_dirty", False)) and not bool(getattr(self, "_photo_paint_stroking", False)):
                self._commit_photo_paint_state()
        self._save_ascii_bridge_controls()
        chain = []
        for i in range(self.node_list.count()):
            it = self.node_list.item(i)
            if it is None:
                continue
            txt = str(it.data(Qt.UserRole) or it.text() or "").strip()
            if txt:
                chain.append(txt)
        self.state["node_chain"] = chain
        self.state["node_chain"] = [x for x in self.state["node_chain"] if x]
        try:
            self.state["node_links"] = [list(x) for x in (getattr(self.node_graph, "links", []) or [])]
        except Exception:
            self.state["node_links"] = []
        self._ensure_node_io()
        self._save_node_param_controls()
        # Keep preview responsive: update enabled flag immediately for live-apply.
        has_layers = any(bool(str((ly or {}).get("text", "")).strip()) for ly in (self.state.get("text_layers", []) or []))
        has_media = any(bool(str((ly or {}).get("path", "")).strip()) and bool((ly or {}).get("enabled", True)) for ly in (self.state.get("media_layers", []) or []))
        defaults_changed = (
            int(self.state.get("brightness", 100)) != 100
            or int(self.state.get("contrast", 100)) != 100
            or int(self.state.get("saturation", 100)) != 100
            or int(self.state.get("sharpness", 100)) != 100
            or int(self.state.get("hue", 0)) != 0
            or int(self.state.get("exposure", 0)) != 0
            or int(self.state.get("temperature", 0)) != 0
        )
        self.state["enabled"] = bool(
            defaults_changed
            or bool(self.state.get("crop_enabled", False))
            or bool(self.state.get("mask_enabled", False))
            or (bool(self.state.get("mask_use_image", False)) and bool(str(self.state.get("mask_image_path", "") or "").strip()))
            or bool(self.state.get("trim_enabled", False))
            or bool(self.state.get("nodes_enabled", False))
            or bool(self.state.get("audio_path", ""))
            or bool(self.state.get("ascii_bridge_apply", False))
            or (bool(self.state.get("photo_paint_enabled", False)) and bool(str(self.state.get("photo_paint_png_b64", "") or "").strip()))
            or has_media
            or has_layers
        )

    def _connect_signals(self):
        self.time_slider.valueChanged.connect(self._sync_time_slider)
        self.time_spin.valueChanged.connect(self._sync_time_spin)
        self.full_btn.clicked.connect(self._toggle_fullscreen)
        self.play_btn.clicked.connect(self._toggle_timeline_play)
        self.stop_btn.clicked.connect(self._stop_timeline_play)
        self.mode_combo.currentIndexChanged.connect(self._update_preview_hint)
        if hasattr(self, "media_bin_list") and self.media_bin_list is not None:
            self.media_bin_list.itemDoubleClicked.connect(self._on_media_bin_activate)
        self.layers_list.currentRowChanged.connect(lambda *_: (self._load_layer_controls(), self._render_preview()))
        self.media_list.currentRowChanged.connect(lambda *_: (self._load_media_layer_controls(), self._render_preview()))
        self.media_list.itemDoubleClicked.connect(lambda *_: self._pick_media_layer_path())
        self.add_layer_btn.clicked.connect(self._add_layer)
        self.rem_layer_btn.clicked.connect(self._remove_layer)
        self.lyr_set_start_btn.clicked.connect(self._set_layer_start_keyframe)
        self.lyr_set_end_btn.clicked.connect(self._set_layer_end_keyframe)
        self.add_media_btn.clicked.connect(self._add_media_layer)
        self.rem_media_btn.clicked.connect(self._remove_media_layer)
        self.pick_media_btn.clicked.connect(self._pick_media_layer_path)
        self.med_set_start_btn.clicked.connect(self._set_media_start_keyframe)
        self.med_set_end_btn.clicked.connect(self._set_media_end_keyframe)
        for sl in self.fx_ctrl.values():
            sl.valueChanged.connect(self._render_preview)
        for w in (self.crop_enable, self.crop_x, self.crop_y, self.crop_w, self.crop_h, self.mask_enable, self.mask_x, self.mask_y, self.mask_w, self.mask_h, self.mask_use_image_chk, self.trim_enable, self.trim_start, self.trim_end, self.trim_start_slider, self.trim_end_slider, self.audio_gain, self.audio_low, self.nodes_enable):
            if isinstance(w, QCheckBox):
                w.stateChanged.connect(self._render_preview)
            else:
                w.valueChanged.connect(self._render_preview)
        self.trim_start.valueChanged.connect(lambda v: self.trim_start_slider.setValue(int(v)))
        self.trim_end.valueChanged.connect(lambda v: self.trim_end_slider.setValue(int(v)))
        self.trim_start_slider.valueChanged.connect(lambda v: self.trim_start.setValue(min(int(v), int(self.trim_end.value()))))
        self.trim_end_slider.valueChanged.connect(lambda v: self.trim_end.setValue(max(int(v), int(self.trim_start.value()))))

        for w in (
            self.lyr_enabled, self.lyr_text, self.lyr_font, self.lyr_size, self.lyr_x, self.lyr_y,
            self.lyr_x1, self.lyr_y1, self.lyr_start, self.lyr_end, self.lyr_ease,
            self.lyr_bx1, self.lyr_by1, self.lyr_bx2, self.lyr_by2,
            self.lyr_sx, self.lyr_sy, self.lyr_alpha,
        ):
            if isinstance(w, QCheckBox):
                w.stateChanged.connect(self._on_layer_change)
            elif isinstance(w, QLineEdit):
                w.textChanged.connect(self._on_layer_change)
            elif isinstance(w, QComboBox):
                w.currentTextChanged.connect(self._on_layer_change)
            elif isinstance(w, QFontComboBox):
                w.currentFontChanged.connect(self._on_layer_change)
            else:
                w.valueChanged.connect(self._on_layer_change)
        self.lyr_color_btn.clicked.connect(self._pick_layer_color)

        for w in (
            self.med_enabled, self.med_path, self.med_type, self.med_x, self.med_y, self.med_x1, self.med_y1,
            self.med_sx, self.med_sy, self.med_alpha, self.med_start, self.med_end, self.med_speed, self.med_ease,
            self.med_bx1, self.med_by1, self.med_bx2, self.med_by2, self.med_blend,
        ):
            if isinstance(w, QCheckBox):
                w.stateChanged.connect(self._on_media_layer_change)
            elif isinstance(w, QLineEdit):
                w.textChanged.connect(self._on_media_layer_change)
            elif isinstance(w, QComboBox):
                w.currentTextChanged.connect(self._on_media_layer_change)
            else:
                w.valueChanged.connect(self._on_media_layer_change)

        self.audio_import_btn.clicked.connect(self._audio_import)
        self.audio_source_btn.clicked.connect(self._audio_from_source)
        self.audio_clear_btn.clicked.connect(self._audio_clear)
        self.mask_media_pick_btn.clicked.connect(self._pick_mask_media_path)
        self.mask_media_clear_btn.clicked.connect(self._clear_mask_media_path)
        self.mask_media_path.textChanged.connect(self._render_preview)
        self.node_add_btn.clicked.connect(self._add_node)
        self.node_edit_btn.clicked.connect(self._edit_selected_node)
        self.node_rem_btn.clicked.connect(self._remove_node)
        self.node_up_btn.clicked.connect(lambda: self._move_node(-1))
        self.node_down_btn.clicked.connect(lambda: self._move_node(1))
        self.node_list.currentRowChanged.connect(self._on_node_list_selected)
        self.node_list.itemDoubleClicked.connect(lambda *_: self._edit_selected_node())
        self.node_graph.linksChanged.connect(self._on_node_links_changed)
        self.node_graph.nodeSelected.connect(self._on_node_graph_selected)
        self.node_graph.portSelected.connect(self._on_node_port_selected)
        self.node_graph.requestRemoveNode.connect(self._remove_node_by_index)
        self.node_enabled_chk.stateChanged.connect(self._on_node_param_change)
        self.node_intensity.valueChanged.connect(self._on_node_param_change)
        self.node_radius.valueChanged.connect(self._on_node_param_change)
        self.node_mix.valueChanged.connect(self._on_node_param_change)
        self.node_value.valueChanged.connect(self._on_node_param_change)
        self.node_seed.valueChanged.connect(self._on_node_param_change)
        self.node_inputs_spin.valueChanged.connect(self._on_node_param_change)
        self.node_outputs_spin.valueChanged.connect(self._on_node_param_change)
        self.node_input_type_combo.currentTextChanged.connect(self._on_node_param_change)
        self.node_output_type_combo.currentTextChanged.connect(self._on_node_param_change)
        self.node_combo.currentIndexChanged.connect(self._update_node_desc)
        self.node_family_combo.currentIndexChanged.connect(self._populate_node_picker)
        self.node_search.textChanged.connect(self._populate_node_picker)
        self.node_search.returnPressed.connect(self._add_node)
        self.node_save_graph_btn.clicked.connect(self._save_node_graph)
        self.node_load_graph_btn.clicked.connect(self._load_node_graph)
        self.node_clear_graph_btn.clicked.connect(self._clear_node_graph)
        self.nodes_code.textChanged.connect(self._render_preview)
        self.script_load_btn.clicked.connect(self._load_script)
        self.script_save_btn.clicked.connect(self._save_script)
        self.node_workspace_btn.clicked.connect(self._open_node_workspace)
        self.node_graph.connectionRejected.connect(self._on_node_connection_rejected)
        self.node_preview_chk.stateChanged.connect(self._on_node_preview_toggle)
        self.node_port_detach_btn.clicked.connect(self._detach_selected_port_link)
        self.node_port_detach_all_btn.clicked.connect(self._detach_all_links_from_selected_port)
        if hasattr(self, "ascii_preview_chk"):
            for w in (
                self.ascii_preview_chk,
                self.ascii_apply_chk,
                self.ascii_style_combo,
                self.ascii_width_spin,
                self.ascii_font_spin,
                self.ascii_charset_edit,
                self.ascii_fg_input,
                self.ascii_bg_input,
                self.ascii_pro_tools_chk,
                self.ascii_pro_bloom,
                self.ascii_pro_vignette,
                self.ascii_pro_grain,
                self.ascii_pro_chroma,
                self.ascii_pro_glitch,
            ):
                if isinstance(w, QCheckBox):
                    w.stateChanged.connect(lambda *_: (self._save_ascii_bridge_controls(), self._render_preview()))
                elif isinstance(w, QComboBox):
                    w.currentTextChanged.connect(lambda *_: (self._save_ascii_bridge_controls(), self._render_preview()))
                elif isinstance(w, QLineEdit):
                    w.textChanged.connect(lambda *_: (self._save_ascii_bridge_controls(), self._render_preview()))
                else:
                    w.valueChanged.connect(lambda *_: (self._save_ascii_bridge_controls(), self._render_preview()))
            self.ascii_fg_pick_btn.clicked.connect(lambda: self._pick_ascii_hex("fg"))
            self.ascii_bg_pick_btn.clicked.connect(lambda: self._pick_ascii_hex("bg"))
            self.ascii_preset_apply_btn.clicked.connect(self._apply_ascii_local_preset)

        self.reset_btn.clicked.connect(self._reset_editor)
        self.apply_btn.clicked.connect(self._request_accept)
        self.cancel_btn.clicked.connect(self._request_reject)

        self.preview.mousePressEvent = self._preview_press
        self.preview.mouseMoveEvent = self._preview_move
        self.preview.mouseReleaseEvent = self._preview_release
        self.preview.wheelEvent = self._preview_wheel
        self.preview.customContextMenuRequested.connect(self._open_preview_context_menu)
        if hasattr(self, "timeline_view") and self.timeline_view is not None:
            self.timeline_view.seekRequested.connect(lambda ms: self.time_slider.setValue(int(ms)))
            self.timeline_view.clipSelected.connect(self._on_timeline_clip_selected)
            self.timeline_view.clipRangeChanged.connect(self._on_timeline_clip_range_changed)
            self.timeline_view.clipSplitRequested.connect(self._split_clip_at_time)
            self.timeline_view.clipRippleDeleteRequested.connect(self._on_timeline_clip_ripple_delete)
            self.timeline_view.clipKeyframeChanged.connect(self._on_timeline_keyframe_changed)
        self.tl_select_btn.clicked.connect(lambda: self._schedule_render_preview(0, fast=False))
        self.tl_trim_start_btn.clicked.connect(self._trim_selected_to_playhead_start)
        self.tl_trim_end_btn.clicked.connect(self._trim_selected_to_playhead_end)
        self.tl_kf_start_btn.clicked.connect(self._set_selected_start_keyframe)
        self.tl_kf_end_btn.clicked.connect(self._set_selected_end_keyframe)
        self.tl_split_btn.clicked.connect(lambda: self._split_selected_clip_at_time(int(self.time_slider.value())))
        self.tl_ripple_btn.clicked.connect(self._ripple_delete_selected_clip)
        self.tl_tool_select_btn.clicked.connect(lambda: self._set_timeline_tool_mode("select"))
        self.tl_tool_razor_btn.clicked.connect(lambda: self._set_timeline_tool_mode("razor"))
        self.tl_tool_trim_btn.clicked.connect(lambda: self._set_timeline_tool_mode("trim"))
        self.tl_tool_ripple_btn.clicked.connect(lambda: self._set_timeline_tool_mode("ripple"))
        if self.photo_mode and hasattr(self, "photo_tool_buttons"):
            for b in self.photo_tool_buttons:
                b.clicked.connect(lambda _=False, btn=b: self._select_photo_tool(btn))
        self._wire_button_feedback()
        self._init_shortcuts()
        self._set_timeline_tool_mode("select")
        self._update_node_preview_visibility()
        for w in (
            self,
            self.preview,
            self.tabs,
            self.node_search,
            self.node_combo,
            self.node_list,
            self.node_graph,
        ):
            try:
                if w is not None:
                    w.installEventFilter(self)
            except Exception:
                pass

    def _update_preview_hint(self):
        if bool(getattr(self, "_always_interactive", False)):
            txt = (
                "Interactive mode is always ON: drag crop/mask handles directly, "
                "drag selected text/media, and drag corner handles to scale. Ctrl+Wheel zoom, middle mouse pan."
            )
            if self.photo_mode:
                txt = "Photo mode: Photoshop-like canvas. Brush/Eraser paint on non-destructive layer. Ctrl+Wheel zoom, middle button pan."
            self.preview_hint.setText(txt)
            return
        mode = str(self.mode_combo.currentData() or "off")
        if mode == "crop":
            txt = "Crop mode: drag inside to move, drag corner/edge handles to resize. Ctrl+Wheel zoom, MMB pan."
        elif mode == "mask":
            txt = "Mask mode: drag inside to move, drag corner/edge handles to resize. Drop media to use as mask."
        elif mode == "text":
            txt = "Text mode: drag selected text layer on preview. Use keyframe buttons for in/out animation."
        elif mode == "media":
            txt = "Media mode: drag selected media layer on preview. Right click timeline clip to split."
        else:
            txt = "Right click on preview for quick tools. Ctrl+Wheel zoom, middle mouse button pans canvas."
        if self.photo_mode:
            txt = "Photo mode: Photoshop-like canvas. Brush/Eraser paint on non-destructive layer. Ctrl+Wheel zoom, middle button pan."
        self.preview_hint.setText(txt)

    def _select_photo_tool(self, btn):
        if not self.photo_mode or not hasattr(self, "photo_tool_buttons"):
            return
        for b in self.photo_tool_buttons:
            b.setChecked(b is btn)
        name = str(btn.text() if btn is not None else "Move")
        self.timeline_tool_hint.setText(f"Photo tool: {name}")
        try:
            nm = name.strip().lower()
            self._photo_active_tool = str(nm or "move")
            if nm in ("move", "text"):
                if hasattr(self, "tabs") and self.layers_tab_ref is not None:
                    self.tabs.setCurrentWidget(self.layers_tab_ref)
                if nm == "text":
                    if (self.layers_list.count() <= 0):
                        self._add_layer()
                    elif self.layers_list.currentRow() < 0:
                        self.layers_list.setCurrentRow(0)
                    j = self.mode_combo.findData("text")
                    if j >= 0:
                        self.mode_combo.setCurrentIndex(j)
                else:
                    med, _ = self._selected_media_layer()
                    target_mode = "media" if med is not None else "text"
                    if target_mode == "text" and self.layers_list.count() <= 0:
                        self._add_layer()
                    j = self.mode_combo.findData(target_mode)
                    if j >= 0:
                        self.mode_combo.setCurrentIndex(j)
            elif nm in ("marquee", "crop"):
                if hasattr(self, "tabs") and self.crop_mask_tab_ref is not None:
                    self.tabs.setCurrentWidget(self.crop_mask_tab_ref)
                self.crop_enable.setChecked(True)
                j = self.mode_combo.findData("crop")
                if j >= 0:
                    self.mode_combo.setCurrentIndex(j)
            elif nm in ("lasso", "mask"):
                if hasattr(self, "tabs") and self.crop_mask_tab_ref is not None:
                    self.tabs.setCurrentWidget(self.crop_mask_tab_ref)
                self.mask_enable.setChecked(True)
                j = self.mode_combo.findData("mask")
                if j >= 0:
                    self.mode_combo.setCurrentIndex(j)
            elif nm in ("brush", "eraser"):
                if hasattr(self, "tabs"):
                    self.tabs.setCurrentWidget(self.crop_mask_tab_ref if self.crop_mask_tab_ref is not None else self.tabs.currentWidget())
                j = self.mode_combo.findData("off")
                if j >= 0:
                    self.mode_combo.setCurrentIndex(j)
            self._update_preview_hint()
            self._schedule_render_preview(0, fast=True)
        except Exception:
            pass

    def _set_timeline_tool_mode(self, mode):
        m = str(mode or "select").strip().lower()
        if m not in ("select", "razor", "trim", "ripple"):
            m = "select"
        self._timeline_tool_mode = m
        try:
            if hasattr(self, "timeline_view") and self.timeline_view is not None:
                self.timeline_view.set_tool_mode(m)
        except Exception:
            pass
        self._sync_timeline_tool_buttons()

    def _sync_timeline_tool_buttons(self):
        mapping = {
            "select": getattr(self, "tl_tool_select_btn", None),
            "razor": getattr(self, "tl_tool_razor_btn", None),
            "trim": getattr(self, "tl_tool_trim_btn", None),
            "ripple": getattr(self, "tl_tool_ripple_btn", None),
        }
        for k, btn in mapping.items():
            if btn is None:
                continue
            btn.blockSignals(True)
            btn.setChecked(k == getattr(self, "_timeline_tool_mode", "select"))
            btn.blockSignals(False)
        mode_name = str(getattr(self, "_timeline_tool_mode", "select")).upper()
        if hasattr(self, "timeline_tool_hint"):
            self.timeline_tool_hint.setText(
                f"Tool: {mode_name} | Drag keyframes, drag clip edges, right-click split, Ctrl+Wheel zoom, MMB pan."
            )
        if hasattr(self, "timeline_status_icon") and hasattr(self, "timeline_status_text"):
            icon_map = {"select": "V", "razor": "C", "trim": "T", "ripple": "R"}
            desc_map = {
                "select": "Select: move clips, drag keyframes and trim edges.",
                "razor": "Razor: click clip to split at cursor.",
                "trim": "Trim: adjust clip boundaries quickly.",
                "ripple": "Ripple: remove clip and close gap.",
            }
            m = str(getattr(self, "_timeline_tool_mode", "select")).strip().lower()
            self.timeline_status_icon.setText(icon_map.get(m, "V"))
            self.timeline_status_text.setText(desc_map.get(m, "Select mode"))

    def _animate_editor_entrance(self, widgets):
        self._ui_anims = []
        for i, w in enumerate(widgets or []):
            if w is None:
                continue
            try:
                eff = QGraphicsOpacityEffect(w)
                eff.setOpacity(0.0)
                w.setGraphicsEffect(eff)
                an = QPropertyAnimation(eff, b"opacity", self)
                an.setDuration(220 + i * 60)
                an.setStartValue(0.0)
                an.setEndValue(1.0)
                an.setEasingCurve(QEasingCurve.OutCubic)
                an.finished.connect(lambda ww=w: ww.setGraphicsEffect(None))
                self._track_ui_anim(an)
                QTimer.singleShot(i * 36, an.start)
            except Exception:
                continue

    def _track_ui_anim(self, anim):
        try:
            if anim is None:
                return
            self._ui_anims.append(anim)
            if len(self._ui_anims) > 24:
                del self._ui_anims[:-24]
            anim.finished.connect(lambda a=anim: self._ui_anims.remove(a) if a in self._ui_anims else None)
        except Exception:
            pass

    def _wire_button_feedback(self):
        for b in self.findChildren(QPushButton):
            if b is None or getattr(b, "_editor_feedback_hooked", False):
                continue
            b._editor_feedback_hooked = True
            b.pressed.connect(lambda bb=b: self._animate_button_feedback(bb))

    def _animate_button_feedback(self, btn):
        if btn is None:
            return
        try:
            eff = QGraphicsOpacityEffect(btn)
            btn.setGraphicsEffect(eff)
            an = QPropertyAnimation(eff, b"opacity", self)
            an.setDuration(110)
            an.setStartValue(0.90)
            an.setEndValue(1.0)
            an.setEasingCurve(QEasingCurve.OutCubic)
            an.finished.connect(lambda b=btn: b.setGraphicsEffect(None))
            self._track_ui_anim(an)
            an.start()
        except Exception:
            pass

    def _schedule_render_preview(self, delay_ms=16, fast=False):
        try:
            self._preview_fast_hint = bool(self._preview_fast_hint or fast)
            delay = max(0, int(delay_ms))
            if fast and self._preview_render_timer.isActive():
                return
            if self._preview_render_timer.isActive():
                self._preview_render_timer.stop()
            self._preview_render_timer.start(delay)
        except Exception:
            pass

    def _render_preview(self, *_):
        self._schedule_render_preview(24, fast=False)

    def _sync_time_slider(self, v):
        if self._ui_lock:
            return
        self._ui_lock = True
        try:
            self.time_spin.setValue(int(v))
        finally:
            self._ui_lock = False
        self._refresh_timeline_view()
        self._schedule_render_preview(0, fast=bool(self._timeline_playing))

    def _sync_time_spin(self, v):
        if self._ui_lock:
            return
        self._ui_lock = True
        try:
            self.time_slider.setValue(int(v))
        finally:
            self._ui_lock = False
        self._refresh_timeline_view()
        self._schedule_render_preview(0, fast=bool(self._timeline_playing))

    def _toggle_fullscreen(self):
        if self.embedded and hasattr(self.host, "_toggle_embedded_editor_fullscreen"):
            try:
                full = bool(self.host._toggle_embedded_editor_fullscreen())
            except Exception:
                full = False
            self._full = full
            self.full_btn.setText(
                self._t("editor_fullscreen_exit", "Exit fullscreen editor")
                if full
                else self._t("editor_fullscreen", "Fullscreen editor")
            )
            try:
                if bool(self.photo_mode):
                    self._timeline_timer.setInterval(50 if self._full else 41)
                else:
                    self._timeline_timer.setInterval(42 if self._full else 33)
            except Exception:
                pass
            self._render_preview()
            return
        self._full = not bool(self._full)
        if self._full:
            try:
                self._normal_geometry = self.geometry()
            except Exception:
                self._normal_geometry = None
            self.showFullScreen()
            self.full_btn.setText(self._t("editor_fullscreen_exit", "Exit fullscreen editor"))
        else:
            self.showNormal()
            try:
                if self._normal_geometry is not None:
                    self.setGeometry(self._normal_geometry)
                else:
                    self.resize(1360, 860)
            except Exception:
                self.resize(1360, 860)
            self.full_btn.setText(self._t("editor_fullscreen", "Fullscreen editor"))
        try:
            self._timeline_timer.setInterval(50 if self._full else 41)
        except Exception:
            pass
        self._render_preview()

    def set_embedded_fullscreen_state(self, full):
        self._full = bool(full)
        try:
            self._timeline_timer.setInterval(50 if self._full else 41)
        except Exception:
            pass
        self.full_btn.setText(
            self._t("editor_fullscreen_exit", "Exit fullscreen editor")
            if self._full
            else self._t("editor_fullscreen", "Fullscreen editor")
        )

    def keyPressEvent(self, ev):
        try:
            if ev.key() == Qt.Key_Tab and not bool(ev.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)):
                if self._nodes_tab_active() and not self._focused_text_input():
                    self._add_node()
                    ev.accept()
                    return
            if ev.key() in (Qt.Key_F11,):
                self._toggle_fullscreen()
                ev.accept()
                return
            if ev.key() in (Qt.Key_Escape,):
                if bool(self._full):
                    self._toggle_fullscreen()
                    ev.accept()
                    return
                if self.embedded:
                    self._request_reject()
                    ev.accept()
                    return
            if ev.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
                if not self._focused_text_input():
                    step = 10 if bool(ev.modifiers() & Qt.ShiftModifier) else 1
                    dx = -step if ev.key() == Qt.Key_Left else step if ev.key() == Qt.Key_Right else 0
                    dy = -step if ev.key() == Qt.Key_Up else step if ev.key() == Qt.Key_Down else 0
                    self._nudge_selected(dx, dy)
                    ev.accept()
                    return
        except Exception:
            pass
        return super().keyPressEvent(ev)

    def eventFilter(self, obj, ev):
        try:
            if ev is not None and ev.type() == QEvent.KeyPress:
                if ev.key() == Qt.Key_Tab and not bool(ev.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)):
                    if self._nodes_tab_active() and not self._focused_text_input():
                        self._add_node()
                        ev.accept()
                        return True
        except Exception:
            pass
        return super().eventFilter(obj, ev)

    def showEvent(self, ev):
        try:
            super().showEvent(ev)
        finally:
            self._schedule_render_preview(0, fast=False)
            self._schedule_node_preview(60)

    def _nudge_selected(self, dx, dy):
        moved = False
        if bool(getattr(self, "_always_interactive", False)):
            k, _, _ = self._selected_clip_ref()
            mode = "media" if k == "M" else ("text" if k == "T" else "off")
        else:
            mode = str(self.mode_combo.currentData() or "off")
        if mode == "media":
            layer, idx = self._selected_media_layer()
            if layer is not None and idx >= 0:
                layer["x"] = int(layer.get("x", 0)) + int(dx)
                layer["y"] = int(layer.get("y", 0)) + int(dy)
                layer["x1"] = int(layer.get("x1", layer["x"])) + int(dx)
                layer["y1"] = int(layer.get("y1", layer["y"])) + int(dy)
                self._load_media_layer_controls()
                moved = True
        if not moved:
            layer, idx = self._selected_layer()
            if layer is not None and idx >= 0:
                layer["x"] = int(layer.get("x", 0)) + int(dx)
                layer["y"] = int(layer.get("y", 0)) + int(dy)
                layer["x1"] = int(layer.get("x1", layer["x"])) + int(dx)
                layer["y1"] = int(layer.get("y1", layer["y"])) + int(dy)
                self._load_layer_controls()
                moved = True
        if moved:
            self._schedule_render_preview(0, fast=True)

    def dragEnterEvent(self, ev):
        try:
            md = ev.mimeData()
            if md and md.hasUrls():
                for u in md.urls():
                    p = u.toLocalFile()
                    if p and os.path.exists(p):
                        ev.acceptProposedAction()
                        return
        except Exception:
            pass
        return super().dragEnterEvent(ev)

    def dropEvent(self, ev):
        try:
            md = ev.mimeData()
            if not md or not md.hasUrls():
                return super().dropEvent(ev)
            paths = []
            for u in md.urls():
                p = str(u.toLocalFile() or "").strip()
                if p and os.path.exists(p):
                    paths.append(p)
            if not paths:
                return super().dropEvent(ev)
            for p in paths:
                self._handle_dropped_path(p)
            ev.acceptProposedAction()
            self._render_preview()
            return
        except Exception:
            pass
        return super().dropEvent(ev)

    def _handle_dropped_path(self, path):
        p = str(path or "").strip()
        if not p:
            return
        low = p.lower()
        if low.endswith((".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac")):
            self.state["audio_path"] = p
            self.audio_path_lbl.setText(p)
            self._refresh_media_bin()
            return
        # In always-interactive mode: if mask is enabled, dropped media can be used as mask.
        mask_drop_mode = bool(str(self.mode_combo.currentData() or "") == "mask")
        if bool(getattr(self, "_always_interactive", False)):
            mask_drop_mode = bool(self.mask_enable.isChecked())
        if mask_drop_mode:
            self.mask_media_path.setText(p)
            self.mask_use_image_chk.setChecked(True)
            self.mask_enable.setChecked(True)
            return
        # Otherwise create media layer from drop.
        arr = self.state.setdefault("media_layers", [])
        lyr = self._default_media_layer(len(arr))
        lyr["path"] = p
        if low.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm")):
            lyr["type"] = "video"
        elif low.endswith(".gif"):
            lyr["type"] = "gif"
        else:
            lyr["type"] = "image"
        arr.append(lyr)
        self._refresh_media_layers(select_idx=len(arr) - 1)
        self._load_media_layer_controls()

    def _on_layer_change(self, *_):
        self._save_layer_controls()
        self._render_preview()

    def _on_media_layer_change(self, *_):
        self._save_media_layer_controls()
        self._render_preview()

    def _pick_layer_color(self):
        layer, _ = self._selected_layer()
        if layer is None:
            return
        col = QColorDialog.getColor(options=QColorDialog.ShowAlphaChannel)
        if not col.isValid():
            return
        layer["color_rgba"] = (col.red(), col.green(), col.blue(), col.alpha())
        self._set_color_btn(self.lyr_color_btn, layer["color_rgba"])
        self._render_preview()

    def _add_layer(self):
        arr = self.state.setdefault("text_layers", [])
        arr.append(self._default_layer(len(arr)))
        self._refresh_layers(select_idx=len(arr) - 1)
        self._load_layer_controls()
        self._render_preview()

    def _remove_layer(self):
        layer, idx = self._selected_layer()
        if layer is None or idx < 0:
            return
        self.state["text_layers"].pop(idx)
        self._refresh_layers(select_idx=max(0, idx - 1))
        self._load_layer_controls()
        self._render_preview()

    def _set_layer_start_keyframe(self):
        layer, idx = self._selected_layer()
        if layer is None or idx < 0:
            return
        t = int(self.time_slider.value())
        layer["x"] = int(self.lyr_x.value())
        layer["y"] = int(self.lyr_y.value())
        layer["start_ms"] = max(0, min(int(layer.get("end_ms", self.duration_ms)), t))
        layer["anim_in_ms"] = int(layer["start_ms"])
        layer["anim_out_ms"] = max(int(layer["anim_in_ms"]), int(layer.get("anim_out_ms", layer.get("end_ms", self.duration_ms)) or layer.get("end_ms", self.duration_ms)))
        layer["anim_out_ms"] = min(int(layer.get("end_ms", self.duration_ms)), int(layer["anim_out_ms"]))
        self._load_layer_controls()
        self._refresh_layers(select_idx=idx)
        self._render_preview()

    def _set_layer_end_keyframe(self):
        layer, idx = self._selected_layer()
        if layer is None or idx < 0:
            return
        t = int(self.time_slider.value())
        layer["x1"] = int(self.lyr_x1.value())
        layer["y1"] = int(self.lyr_y1.value())
        layer["end_ms"] = max(int(layer.get("start_ms", 0)), min(self.duration_ms, t))
        layer["anim_out_ms"] = int(layer["end_ms"])
        layer["anim_in_ms"] = min(int(layer["anim_out_ms"]), int(layer.get("anim_in_ms", layer.get("start_ms", 0)) or layer.get("start_ms", 0)))
        layer["anim_in_ms"] = max(int(layer.get("start_ms", 0)), int(layer["anim_in_ms"]))
        self._load_layer_controls()
        self._refresh_layers(select_idx=idx)
        self._render_preview()

    def _audio_import(self):
        fn, _ = QFileDialog.getOpenFileName(
            self,
            self._t("editor_import_audio", "Import audio"),
            os.getcwd(),
            "Audio/Video (*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.mp4 *.mov *.mkv *.avi)",
        )
        if not fn:
            return
        self.state["audio_path"] = fn
        self.audio_path_lbl.setText(fn)
        self._refresh_media_bin()
        self._render_preview()

    def _audio_from_source(self):
        cand = str(getattr(self.host, "original_source_path", "") or getattr(self.host, "current_path", "") or "")
        if cand and os.path.exists(cand):
            self.state["audio_path"] = cand
            self.audio_path_lbl.setText(cand)
            self._refresh_media_bin()
            self._render_preview()

    def _audio_clear(self):
        self.state["audio_path"] = ""
        self.audio_path_lbl.setText("-")
        self._refresh_media_bin()
        self._render_preview()

    def _add_node(self):
        node_id = str(self.node_combo.currentData() or "").strip()
        if not node_id:
            return
        arr = self.state.setdefault("node_chain", [])
        arr.append(node_id)
        p = self.state.setdefault("node_params", [])
        p.append(self._default_node_params(node_id))
        io = self.state.setdefault("node_io", [])
        io.append(dict(self._default_node_io(node_id)))
        links = self.state.setdefault("node_links", [])
        if len(arr) >= 2 and not links and self._node_ports_compatible_state(len(arr) - 2, len(arr) - 1):
            links.append([len(arr) - 2, len(arr) - 1, 0, 0])
        self._refresh_nodes()
        self.node_list.setCurrentRow(max(0, self.node_list.count() - 1))
        self._render_preview()

    def _remove_node(self):
        self._remove_node_by_index(self.node_list.currentRow())

    def _remove_node_by_index(self, idx):
        idx = int(idx)
        arr = self.state.setdefault("node_chain", [])
        if idx < 0 or idx >= len(arr):
            return
        arr.pop(idx)
        parr = self.state.setdefault("node_params", [])
        if idx < len(parr):
            parr.pop(idx)
        io = self.state.setdefault("node_io", [])
        if idx < len(io):
            io.pop(idx)
        links = []
        for link in (self.state.get("node_links", []) or []):
            try:
                a, b = int(link[0]), int(link[1])
                op = int(link[2]) if len(link) >= 3 else 0
                ip = int(link[3]) if len(link) >= 4 else 0
            except Exception:
                continue
            if a == idx or b == idx:
                continue
            if a > idx:
                a -= 1
            if b > idx:
                b -= 1
            if a != b:
                links.append([a, b, op, ip])
        self.state["node_links"] = links
        self._refresh_nodes()
        self._render_preview()

    def _move_node(self, delta):
        idx = self.node_list.currentRow()
        arr = self.state.setdefault("node_chain", [])
        if idx < 0 or idx >= len(arr):
            return
        j = max(0, min(len(arr) - 1, idx + int(delta)))
        if j == idx:
            return
        arr[idx], arr[j] = arr[j], arr[idx]
        parr = self.state.setdefault("node_params", [])
        if idx < len(parr) and j < len(parr):
            parr[idx], parr[j] = parr[j], parr[idx]
        io = self.state.setdefault("node_io", [])
        if idx < len(io) and j < len(io):
            io[idx], io[j] = io[j], io[idx]
        remap = {idx: j, j: idx}
        new_links = []
        for link in (self.state.get("node_links", []) or []):
            try:
                a, b = int(link[0]), int(link[1])
                op = int(link[2]) if len(link) >= 3 else 0
                ip = int(link[3]) if len(link) >= 4 else 0
            except Exception:
                continue
            a = remap.get(a, a)
            b = remap.get(b, b)
            if a != b:
                new_links.append([a, b, op, ip])
        self.state["node_links"] = new_links
        self._refresh_nodes()
        self.node_list.setCurrentRow(j)
        self._render_preview()

    def _refresh_node_port_inspector(self):
        if not hasattr(self, "node_port_info_lbl") or not hasattr(self, "node_port_links_list"):
            return
        self.node_port_links_list.clear()
        info = self.node_graph.selected_port() if hasattr(self, "node_graph") else None
        if not isinstance(info, dict):
            self.node_port_info_lbl.setText("Port inspector: select node input/output port to manage multi-links.")
            try:
                self.node_port_detach_btn.setEnabled(False)
                self.node_port_detach_all_btn.setEnabled(False)
            except Exception:
                pass
            return
        try:
            idx = int(info.get("idx", -1))
            side = str(info.get("side", "")).strip().lower()
            port = int(info.get("port", 0))
        except Exception:
            idx = -1
            side = ""
            port = 0
        chain = self.state.get("node_chain", []) or []
        if idx < 0 or idx >= len(chain) or side not in ("in", "out"):
            self.node_port_info_lbl.setText("Port inspector: select node input/output port to manage multi-links.")
            return
        ptype = self.node_graph._port_type(idx, side, port)
        badge = self.node_graph._port_badge(ptype)
        side_name = "Input" if side == "in" else "Output"
        self.node_port_info_lbl.setText(
            f"{chain[idx]}  {side_name} {port + 1}  [{ptype}/{badge}]"
        )
        links = self.node_graph.links_for_port(info)
        for lk in links:
            try:
                a, b = int(lk[0]), int(lk[1])
                op = int(lk[2]) if len(lk) >= 3 else 0
                ip = int(lk[3]) if len(lk) >= 4 else 0
            except Exception:
                continue
            src_name = chain[a] if 0 <= a < len(chain) else f"node {a}"
            dst_name = chain[b] if 0 <= b < len(chain) else f"node {b}"
            it = QListWidgetItem(f"{src_name}:O{op + 1}  ->  {dst_name}:I{ip + 1}")
            it.setData(Qt.UserRole, [a, b, op, ip])
            self.node_port_links_list.addItem(it)
        has_links = self.node_port_links_list.count() > 0
        try:
            self.node_port_detach_btn.setEnabled(has_links)
            self.node_port_detach_all_btn.setEnabled(has_links)
        except Exception:
            pass

    def _on_node_port_selected(self, idx, side, port):
        _ = (idx, side, port)
        self._refresh_node_port_inspector()

    def _detach_selected_port_link(self):
        if not hasattr(self, "node_port_links_list"):
            return
        item = self.node_port_links_list.currentItem()
        if item is None:
            return
        link = item.data(Qt.UserRole)
        self.node_graph.remove_link(link)
        self.state["node_links"] = [list(x) for x in (self.node_graph.links or [])]
        self._refresh_node_port_inspector()
        self._render_preview()
        self._schedule_node_preview(20)

    def _detach_all_links_from_selected_port(self):
        if not hasattr(self, "node_graph"):
            return
        self.node_graph.remove_links_for_port()
        self.state["node_links"] = [list(x) for x in (self.node_graph.links or [])]
        self._refresh_node_port_inspector()
        self._render_preview()
        self._schedule_node_preview(20)

    def _on_node_links_changed(self, links):
        self.state["node_links"] = [list(x) for x in (links or [])]
        self._refresh_node_port_inspector()
        self._render_preview()
        self._schedule_node_preview(30)

    def _on_node_connection_rejected(self, reason):
        msg = str(reason or "Incompatible node ports")
        try:
            self.timeline_tool_hint.setText(msg)
        except Exception:
            pass

    def _on_node_graph_selected(self, idx):
        try:
            if self.node_list.count() > int(idx) >= 0:
                self.node_list.setCurrentRow(int(idx))
        except Exception:
            pass
        self._refresh_node_port_inspector()

    def _on_node_list_selected(self, idx):
        try:
            self.node_graph._selected = int(idx)
            self.node_graph.update()
        except Exception:
            pass
        self._refresh_node_port_inspector()
        self._load_node_param_controls()
        self._schedule_node_preview(20)

    def _on_node_param_change(self, *_):
        self._save_node_param_controls()
        self._refresh_single_node_row()
        try:
            self.node_graph.set_graph(
                self.state.get("node_chain", []) or [],
                self.state.get("node_links", []) or [],
                self.state.get("node_io", []) or [],
            )
            self.state["node_links"] = [list(x) for x in (self.node_graph.links or [])]
        except Exception:
            pass
        self._refresh_node_port_inspector()
        self._render_preview()
        self._schedule_node_preview(30)

    def _on_node_preview_toggle(self, *_):
        try:
            self.state["nodes_preview"] = bool(self.node_preview_chk.isChecked())
        except Exception:
            self.state["nodes_preview"] = False
        self._update_node_preview_visibility()
        self._schedule_node_preview(0)

    def _update_node_preview_visibility(self):
        try:
            en = bool(self.node_preview_chk.isChecked())
        except Exception:
            en = False
        try:
            self.node_preview.setVisible(en)
        except Exception:
            pass
        if not en:
            try:
                self.node_preview.clear()
                self.node_preview.setText("Node output preview is disabled.")
            except Exception:
                pass

    def _schedule_node_preview(self, delay_ms=80):
        try:
            if not hasattr(self, "node_preview_chk") or not bool(self.node_preview_chk.isChecked()):
                return
            if self._node_preview_timer.isActive():
                self._node_preview_timer.stop()
            base = 140 if self.isFullScreen() else 95
            self._node_preview_timer.start(max(base, int(delay_ms)))
        except Exception:
            pass

    def _render_node_preview_now(self):
        if self._node_preview_rendering:
            return
        if not hasattr(self, "node_preview_chk") or not bool(self.node_preview_chk.isChecked()):
            return
        self._node_preview_rendering = True
        try:
            try:
                self._pull_state_from_widgets()
            except Exception:
                pass
            idx = int(self.node_list.currentRow())
            chain = self.state.get("node_chain", []) or []
            if idx < 0 or idx >= len(chain):
                self.node_preview.setPixmap(QPixmap())
                self.node_preview.setText("Select a node to preview partial graph output.")
                return
            t_ms = int(self.time_slider.value())
            sig = (int(idx), int(t_ms // 140), len(chain), str(chain[idx]))
            now = time.time()
            if sig == getattr(self, "_node_preview_last_sig", None) and (now - float(getattr(self, "_node_preview_last_ts", 0.0))) < 0.28:
                return
            st = copy.deepcopy(self.result_state(include_photo_blob=False))
            st["nodes_enabled"] = True
            st["nodes_preview"] = True
            st["node_chain"] = list((st.get("node_chain", []) or [])[: idx + 1])
            st["node_params"] = list((st.get("node_params", []) or [])[: idx + 1])
            st["node_io"] = list((st.get("node_io", []) or [])[: idx + 1])
            sub_links = []
            for lk in (st.get("node_links", []) or []):
                try:
                    a = int(lk[0]); b = int(lk[1]); op = int(lk[2]) if len(lk) >= 3 else 0; ip = int(lk[3]) if len(lk) >= 4 else 0
                except Exception:
                    continue
                if a <= idx and b <= idx and a != b:
                    sub_links.append([a, b, op, ip])
            st["node_links"] = sub_links
            old = self.host.editor_state
            self.host.editor_state = st
            try:
                src_frame = self._source_frame_for_time(t_ms, fast=False)
                img = self.host._apply_editor_state(src_frame.copy(), t_ms=t_ms).convert("RGB")
                if bool(self.photo_mode):
                    img = self._apply_photo_paint_overlay(img, self.state)
            except Exception:
                img = self.src.copy().convert("RGB")
            finally:
                self.host.editor_state = old
            pw = max(96, int(self.node_preview.width() - 8))
            ph = max(72, int(self.node_preview.height() - 8))
            k = min(float(pw) / float(img.width), float(ph) / float(img.height))
            dw = max(1, int(round(img.width * k)))
            dh = max(1, int(round(img.height * k)))
            canvas = Image.new("RGB", (pw, ph), (10, 13, 18))
            canvas.paste(img.resize((dw, dh), Image.Resampling.BILINEAR), ((pw - dw) // 2, (ph - dh) // 2))
            self.node_preview.setText("")
            self.node_preview.setPixmap(pil_to_qpixmap(canvas))
            self._node_preview_last_sig = sig
            self._node_preview_last_ts = now
        finally:
            self._node_preview_rendering = False

    def _refresh_single_node_row(self):
        try:
            idx = int(self.node_list.currentRow())
            chain = self.state.get("node_chain", []) or []
            prm = self.state.get("node_params", []) or []
            io = self.state.get("node_io", []) or []
            if idx < 0 or idx >= len(chain) or idx >= self.node_list.count():
                return
            txt = str(chain[idx] or "").strip()
            if not txt:
                return
            p = prm[idx] if idx < len(prm) and isinstance(prm[idx], dict) else {}
            iop = io[idx] if idx < len(io) and isinstance(io[idx], dict) else {}
            en = bool(p.get("enabled", True))
            intensity = int(p.get("intensity", 55) or 55)
            mix = int(p.get("mix", 100) or 100)
            inc = int(iop.get("inputs", 1) or 1)
            outc = int(iop.get("outputs", 1) or 1)
            in_t = str((iop.get("in_types", [iop.get("input_type", "video")]) or ["video"])[0])
            out_t = str((iop.get("out_types", [iop.get("output_type", "video")]) or ["video"])[0])
            label = f"{txt}  ({intensity}%/{mix}%mix)  {inc}in/{outc}out  [{in_t}->{out_t}]"
            if not en:
                label = "[OFF] " + label
            it = self.node_list.item(idx)
            if it is not None:
                it.setText(label)
                it.setData(Qt.UserRole, txt)
                it.setForeground(QColor("#6d7484") if not en else QColor("#dfe8f6"))
        except Exception:
            pass

    def _toggle_timeline_play(self):
        self._timeline_playing = not bool(self._timeline_playing)
        if self._timeline_playing:
            self.play_btn.setText(self._t("pause", "Pause"))
            self._timeline_timer.start()
        else:
            self.play_btn.setText(self._t("play", "Play"))
            self._timeline_timer.stop()
            self._schedule_render_preview(0, fast=False)

    def _stop_timeline_play(self):
        self._timeline_playing = False
        self._timeline_timer.stop()
        self.play_btn.setText(self._t("play", "Play"))
        self.time_slider.setValue(0)
        self._schedule_render_preview(0, fast=False)

    def _timeline_tick(self):
        if not self._timeline_playing:
            return
        cur = int(self.time_slider.value())
        step = max(10, int(self._timeline_timer.interval() or 41))
        nxt = cur + step
        if nxt >= self.duration_ms:
            nxt = self.duration_ms
            self._timeline_playing = False
            self._timeline_timer.stop()
            self.play_btn.setText(self._t("play", "Play"))
        self.time_slider.setValue(int(nxt))

    def _refresh_timeline_view(self):
        if not hasattr(self, "timeline_view") or self.timeline_view is None:
            return
        try:
            self.timeline_view.set_data(
                int(self.duration_ms),
                int(self.time_slider.value()),
                self.state.get("text_layers", []) or [],
                self.state.get("media_layers", []) or [],
                selected_text=int(self.layers_list.currentRow()) if hasattr(self, "layers_list") else -1,
                selected_media=int(self.media_list.currentRow()) if hasattr(self, "media_list") else -1,
                audio_path=str(self.state.get("audio_path", "") or ""),
            )
            self.timeline_view.set_tool_mode(getattr(self, "_timeline_tool_mode", "select"))
        except Exception:
            pass

    def _on_timeline_clip_selected(self, kind, idx):
        try:
            k = str(kind or "")
            i = int(idx)
        except Exception:
            return
        if k == "T" and hasattr(self, "layers_list"):
            if 0 <= i < self.layers_list.count():
                self.layers_list.setCurrentRow(i)
        elif k == "M" and hasattr(self, "media_list"):
            if 0 <= i < self.media_list.count():
                self.media_list.setCurrentRow(i)
        self._refresh_timeline_view()

    def _on_timeline_clip_range_changed(self, kind, idx, start_ms, end_ms):
        try:
            i = int(idx)
            t0 = int(max(0, min(self.duration_ms, start_ms)))
            t1 = int(max(t0, min(self.duration_ms, end_ms)))
        except Exception:
            return
        if str(kind) == "T":
            arr = self.state.get("text_layers", []) or []
            if 0 <= i < len(arr):
                arr[i]["start_ms"] = t0
                arr[i]["end_ms"] = t1
                arr[i]["anim_in_ms"] = max(t0, min(t1, int(arr[i].get("anim_in_ms", t0) or t0)))
                arr[i]["anim_out_ms"] = max(int(arr[i]["anim_in_ms"]), min(t1, int(arr[i].get("anim_out_ms", t1) or t1)))
                self._load_layer_controls()
                self._refresh_layers(select_idx=i)
        elif str(kind) == "M":
            arr = self.state.get("media_layers", []) or []
            if 0 <= i < len(arr):
                arr[i]["start_ms"] = t0
                arr[i]["end_ms"] = t1
                arr[i]["anim_in_ms"] = max(t0, min(t1, int(arr[i].get("anim_in_ms", t0) or t0)))
                arr[i]["anim_out_ms"] = max(int(arr[i]["anim_in_ms"]), min(t1, int(arr[i].get("anim_out_ms", t1) or t1)))
                self._load_media_layer_controls()
                self._refresh_media_layers(select_idx=i)
        self._render_preview()

    def _on_timeline_clip_ripple_delete(self, kind, idx):
        self._on_timeline_clip_selected(kind, idx)
        self._ripple_delete_selected_clip()

    def _on_timeline_keyframe_changed(self, kind, idx, key, ms):
        try:
            i = int(idx)
            tm = int(max(0, min(self.duration_ms, int(ms))))
        except Exception:
            return
        if str(kind) == "T":
            arr = self.state.get("text_layers", []) or []
            if i < 0 or i >= len(arr):
                return
            lyr = arr[i]
            t0 = int(lyr.get("start_ms", 0) or 0)
            t1 = int(lyr.get("end_ms", self.duration_ms) or self.duration_ms)
            tm = max(t0, min(t1, tm))
            if str(key) == "in":
                lyr["anim_in_ms"] = tm
                lyr["anim_out_ms"] = max(tm, int(lyr.get("anim_out_ms", t1) or t1))
            else:
                lyr["anim_out_ms"] = tm
                lyr["anim_in_ms"] = min(tm, int(lyr.get("anim_in_ms", t0) or t0))
            self._refresh_layers(select_idx=i)
            self._load_layer_controls()
        elif str(kind) == "M":
            arr = self.state.get("media_layers", []) or []
            if i < 0 or i >= len(arr):
                return
            lyr = arr[i]
            t0 = int(lyr.get("start_ms", 0) or 0)
            t1 = int(lyr.get("end_ms", self.duration_ms) or self.duration_ms)
            tm = max(t0, min(t1, tm))
            if str(key) == "in":
                lyr["anim_in_ms"] = tm
                lyr["anim_out_ms"] = max(tm, int(lyr.get("anim_out_ms", t1) or t1))
            else:
                lyr["anim_out_ms"] = tm
                lyr["anim_in_ms"] = min(tm, int(lyr.get("anim_in_ms", t0) or t0))
            self._refresh_media_layers(select_idx=i)
            self._load_media_layer_controls()
        else:
            return
        self._schedule_render_preview(0, fast=True)

    def _selected_clip_ref(self):
        m_idx = int(self.media_list.currentRow()) if hasattr(self, "media_list") else -1
        if m_idx >= 0:
            arr = self.state.get("media_layers", []) or []
            if m_idx < len(arr):
                return "M", m_idx, arr
        t_idx = int(self.layers_list.currentRow()) if hasattr(self, "layers_list") else -1
        if t_idx >= 0:
            arr = self.state.get("text_layers", []) or []
            if t_idx < len(arr):
                return "T", t_idx, arr
        return "", -1, []

    def _selected_clip_object(self):
        k, i, arr = self._selected_clip_ref()
        if not k or i < 0 or i >= len(arr):
            return "", -1, None
        return k, i, arr[i]

    def _frame_step_ms(self):
        try:
            fps = int(getattr(self.host, "render_fps", 24) or 24)
        except Exception:
            fps = 24
        fps = max(1, min(240, fps))
        return max(1, int(round(1000.0 / float(fps))))

    def _timeline_seek_relative(self, delta_ms):
        if self._focused_text_input():
            return
        try:
            nv = int(self.time_slider.value()) + int(delta_ms)
            self.time_slider.setValue(max(0, min(int(self.duration_ms), nv)))
        except Exception:
            pass

    def _timeline_seek_home(self):
        if self._focused_text_input():
            return
        self.time_slider.setValue(0)

    def _timeline_seek_end(self):
        if self._focused_text_input():
            return
        self.time_slider.setValue(int(self.duration_ms))

    def _timeline_zoom_by(self, factor):
        try:
            if hasattr(self, "timeline_view") and self.timeline_view is not None:
                self.timeline_view.zoom_by(float(factor), anchor_ms=int(self.time_slider.value()))
        except Exception:
            pass

    def _timeline_zoom_in(self):
        self._timeline_zoom_by(1.12)

    def _timeline_zoom_out(self):
        self._timeline_zoom_by(1.0 / 1.12)

    def _duplicate_selected_clip(self):
        k, i, clip = self._selected_clip_object()
        if not k or clip is None:
            return
        arr = self.state.get("media_layers", []) if k == "M" else self.state.get("text_layers", [])
        if not isinstance(arr, list):
            return
        dupe = copy.deepcopy(clip)
        t0 = int(dupe.get("start_ms", 0) or 0)
        t1 = int(dupe.get("end_ms", t0 + 1) or (t0 + 1))
        ln = max(1, t1 - t0)
        shift = max(120, min(1200, ln // 3))
        nt0 = min(max(0, t0 + shift), max(0, self.duration_ms - 1))
        nt1 = min(self.duration_ms, nt0 + ln)
        if nt1 <= nt0:
            nt1 = min(self.duration_ms, nt0 + 1)
        dupe["start_ms"] = int(nt0)
        dupe["end_ms"] = int(nt1)
        ai = int(dupe.get("anim_in_ms", t0) or t0) + shift
        ao = int(dupe.get("anim_out_ms", t1) or t1) + shift
        dupe["anim_in_ms"] = max(nt0, min(nt1, ai))
        dupe["anim_out_ms"] = max(int(dupe["anim_in_ms"]), min(nt1, ao))
        arr.insert(i + 1, dupe)
        if k == "M":
            self._refresh_media_layers(select_idx=i + 1)
            self.media_list.setCurrentRow(i + 1)
            self._load_media_layer_controls()
        else:
            self._refresh_layers(select_idx=i + 1)
            self.layers_list.setCurrentRow(i + 1)
            self._load_layer_controls()
        self._render_preview()

    def _group_selected_clip(self):
        k, i, clip = self._selected_clip_object()
        if not k or clip is None:
            return
        gid = 1
        for arr in (self.state.get("text_layers", []) or [], self.state.get("media_layers", []) or []):
            for x in arr:
                try:
                    gid = max(gid, int((x or {}).get("group_id", 0) or 0) + 1)
                except Exception:
                    continue
        clip["group_id"] = int(gid)
        try:
            self.timeline_tool_hint.setText(f"Grouped clip: G{gid}")
        except Exception:
            pass
        self._render_preview()

    def _ungroup_selected_clip(self):
        k, i, clip = self._selected_clip_object()
        if not k or clip is None:
            return
        try:
            clip.pop("group_id", None)
        except Exception:
            pass
        try:
            self.timeline_tool_hint.setText("Clip ungrouped")
        except Exception:
            pass
        self._render_preview()

    def _change_selected_clip_speed(self):
        k, i, clip = self._selected_clip_object()
        if not k or clip is None:
            return
        t0 = int(clip.get("start_ms", 0) or 0)
        t1 = int(clip.get("end_ms", t0 + 1) or (t0 + 1))
        ln = max(1, t1 - t0)
        speeds = [0.5, 1.0, 1.5, 2.0]
        cur = float(clip.get("speed", 1.0) or 1.0)
        nxt = speeds[0]
        for sp in speeds:
            if sp > cur + 1e-6:
                nxt = sp
                break
            nxt = speeds[0]
        clip["speed"] = float(nxt)
        new_len = max(1, int(round(float(ln) * (cur / nxt))))
        nt1 = min(int(self.duration_ms), int(t0 + new_len))
        clip["end_ms"] = int(max(t0 + 1, nt1))
        clip["anim_in_ms"] = max(t0, min(int(clip["end_ms"]), int(clip.get("anim_in_ms", t0) or t0)))
        clip["anim_out_ms"] = max(int(clip["anim_in_ms"]), min(int(clip["end_ms"]), int(clip.get("anim_out_ms", clip["end_ms"]) or clip["end_ms"])))
        if k == "M":
            self._refresh_media_layers(select_idx=i)
            self._load_media_layer_controls()
        else:
            self._refresh_layers(select_idx=i)
            self._load_layer_controls()
        try:
            self.timeline_tool_hint.setText(f"Speed set to {nxt:.1f}x for selected clip.")
        except Exception:
            pass
        self._render_preview()

    def _split_selected_clip_at_time(self, t_ms):
        k, i, arr = self._selected_clip_ref()
        if not k or i < 0 or i >= len(arr):
            return
        self._split_clip_at_time(k, i, int(t_ms))

    def _split_clip_at_time(self, kind, idx, t_ms):
        try:
            i = int(idx)
            tm = int(max(0, min(self.duration_ms, t_ms)))
        except Exception:
            return
        if str(kind) == "T":
            arr = self.state.get("text_layers", []) or []
        else:
            arr = self.state.get("media_layers", []) or []
        if i < 0 or i >= len(arr):
            return
        src = arr[i]
        t0 = int(src.get("start_ms", 0) or 0)
        t1 = int(src.get("end_ms", self.duration_ms) or self.duration_ms)
        if tm <= t0 + 20 or tm >= t1 - 20:
            return
        part2 = copy.deepcopy(src)
        src["end_ms"] = tm
        part2["start_ms"] = tm
        # Keep animation keyframes valid after split.
        ai = int(src.get("anim_in_ms", t0) or t0)
        ao = int(src.get("anim_out_ms", t1) or t1)
        src["anim_in_ms"] = max(t0, min(tm, ai))
        src["anim_out_ms"] = max(src["anim_in_ms"], min(tm, ao))
        ai2 = int(part2.get("anim_in_ms", tm) or tm)
        ao2 = int(part2.get("anim_out_ms", t1) or t1)
        part2["anim_in_ms"] = max(tm, min(t1, ai2))
        part2["anim_out_ms"] = max(part2["anim_in_ms"], min(t1, ao2))
        arr.insert(i + 1, part2)
        if str(kind) == "T":
            self._refresh_layers(select_idx=i)
            self.layers_list.setCurrentRow(i + 1)
        else:
            self._refresh_media_layers(select_idx=i)
            self.media_list.setCurrentRow(i + 1)
        self._render_preview()

    def _trim_selected_to_playhead_start(self):
        k, i, arr = self._selected_clip_ref()
        if not k:
            return
        tm = int(self.time_slider.value())
        obj = arr[i]
        obj["start_ms"] = max(0, min(int(obj.get("end_ms", self.duration_ms) or self.duration_ms), tm))
        obj["anim_in_ms"] = max(int(obj["start_ms"]), min(int(obj.get("end_ms", self.duration_ms) or self.duration_ms), int(obj.get("anim_in_ms", obj["start_ms"]) or obj["start_ms"])))
        obj["anim_out_ms"] = max(int(obj["anim_in_ms"]), min(int(obj.get("end_ms", self.duration_ms) or self.duration_ms), int(obj.get("anim_out_ms", obj.get("end_ms", self.duration_ms)) or obj.get("end_ms", self.duration_ms))))
        if k == "T":
            self._refresh_layers(select_idx=i)
            self._load_layer_controls()
        else:
            self._refresh_media_layers(select_idx=i)
            self._load_media_layer_controls()
        self._render_preview()

    def _trim_selected_to_playhead_end(self):
        k, i, arr = self._selected_clip_ref()
        if not k:
            return
        tm = int(self.time_slider.value())
        obj = arr[i]
        obj["end_ms"] = max(int(obj.get("start_ms", 0) or 0), min(self.duration_ms, tm))
        obj["anim_in_ms"] = max(int(obj.get("start_ms", 0) or 0), min(int(obj["end_ms"]), int(obj.get("anim_in_ms", obj.get("start_ms", 0)) or obj.get("start_ms", 0))))
        obj["anim_out_ms"] = max(int(obj["anim_in_ms"]), min(int(obj["end_ms"]), int(obj.get("anim_out_ms", obj["end_ms"]) or obj["end_ms"])))
        if k == "T":
            self._refresh_layers(select_idx=i)
            self._load_layer_controls()
        else:
            self._refresh_media_layers(select_idx=i)
            self._load_media_layer_controls()
        self._render_preview()

    def _ripple_delete_selected_clip(self):
        k, i, arr = self._selected_clip_ref()
        if not k or i < 0 or i >= len(arr):
            return
        clip = arr[i]
        t0 = int(clip.get("start_ms", 0) or 0)
        t1 = int(clip.get("end_ms", t0) or t0)
        delta = max(0, t1 - t0)
        arr.pop(i)
        if delta > 0:
            for j in range(i, len(arr)):
                it = arr[j]
                it["start_ms"] = max(0, int(it.get("start_ms", 0) or 0) - delta)
                it["end_ms"] = max(int(it["start_ms"]), int(it.get("end_ms", it["start_ms"]) or it["start_ms"]) - delta)
        if k == "T":
            self._refresh_layers(select_idx=max(0, i - 1))
            self._load_layer_controls()
        else:
            self._refresh_media_layers(select_idx=max(0, i - 1))
            self._load_media_layer_controls()
        self._render_preview()

    def _edit_selected_node(self):
        _, idx = self._selected_node()
        if idx < 0:
            self._add_node()
            _, idx = self._selected_node()
        if idx < 0:
            return
        self._open_node_workspace(focus_idx=idx)

    def _open_node_workspace(self, focus_idx=None):
        self._ensure_node_params()
        self._ensure_node_io()
        backup_chain = copy.deepcopy(self.state.get("node_chain", []) or [])
        backup_params = copy.deepcopy(self.state.get("node_params", []) or [])
        backup_io = copy.deepcopy(self.state.get("node_io", []) or [])
        backup_links = copy.deepcopy(self.state.get("node_links", []) or [])
        dlg = QDialog(self)
        dlg.setWindowTitle("Node workspace")
        dlg.resize(1360, 860)
        lay = QVBoxLayout(dlg)
        row = QHBoxLayout()
        row.addWidget(QLabel("Node workspace: drag nodes, right click to connect/disconnect typed ports (video/audio/data)."))
        row.addStretch(1)
        fs = QPushButton("Fullscreen")
        fs.setStyleSheet(self.host._glass_btn_css())
        fs.setCursor(Qt.PointingHandCursor)
        row.addWidget(fs)
        lay.addLayout(row)
        split = QSplitter(Qt.Horizontal)
        left = QFrame()
        ll = QVBoxLayout(left)
        add_row = QHBoxLayout()
        node_pick = QComboBox()
        for cat, label, nid in (self.node_catalog or self._node_catalog()):
            node_pick.addItem(f"{label}  [{cat}]", nid)
        add_btn = QPushButton(self._t("editor_add_node", "Add node"))
        rem_btn = QPushButton(self._t("editor_remove_node", "Remove node"))
        for b in (add_btn, rem_btn):
            b.setStyleSheet(self.host._glass_btn_css())
            b.setCursor(Qt.PointingHandCursor)
        add_row.addWidget(node_pick, 1)
        add_row.addWidget(add_btn)
        add_row.addWidget(rem_btn)
        ll.addLayout(add_row)
        lst = QListWidget()
        for n in (self.state.get("node_chain", []) or []):
            lst.addItem(str(n))
        ll.addWidget(lst, 1)
        inspector = QFrame()
        inf = QFormLayout(inspector)
        inf.setLabelAlignment(Qt.AlignLeft)
        en = QCheckBox("Enabled")
        intensity = QSlider(Qt.Horizontal)
        intensity.setRange(0, 100)
        radius = QSpinBox()
        radius.setRange(0, 32)
        mix = QSlider(Qt.Horizontal)
        mix.setRange(0, 100)
        value = QSpinBox()
        value.setRange(-200, 200)
        seed = QSpinBox()
        seed.setRange(0, 9999)
        in_spin = QSpinBox()
        in_spin.setRange(1, 8)
        out_spin = QSpinBox()
        out_spin.setRange(1, 8)
        in_type = QComboBox()
        out_type = QComboBox()
        in_type.addItems(["video", "audio", "data", "any"])
        out_type.addItems(["video", "audio", "data", "any"])
        desc = QLabel("")
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size:11px; color:#9fb3cc;")
        inf.addRow(en)
        inf.addRow("Intensity:", intensity)
        inf.addRow("Radius:", radius)
        inf.addRow("Mix:", mix)
        inf.addRow("Value:", value)
        inf.addRow("Seed:", seed)
        inf.addRow("Inputs:", in_spin)
        inf.addRow("Outputs:", out_spin)
        inf.addRow("In type:", in_type)
        inf.addRow("Out type:", out_type)
        inf.addRow(desc)
        ll.addWidget(inspector, 0)
        split.addWidget(left)
        right = QFrame()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)
        canvas = NodeGraphCanvas()
        canvas.set_graph(
            self.state.get("node_chain", []) or [],
            self.state.get("node_links", []) or [],
            self.state.get("node_io", []) or [],
        )
        canvas.connectionRejected.connect(lambda msg: desc.setText(str(msg or "")))
        rl.addWidget(canvas, 1)
        conn_box = QFrame()
        conn_box.setStyleSheet("QFrame{background: rgba(255,255,255,0.05); border-radius:10px;}")
        conn_l = QVBoxLayout(conn_box)
        conn_l.setContentsMargins(8, 8, 8, 8)
        conn_l.setSpacing(6)
        conn_info = QLabel("Port inspector: select node input/output port.")
        conn_info.setWordWrap(True)
        conn_info.setStyleSheet("font-size:11px; color:#9fb3cc;")
        conn_list = QListWidget()
        conn_list.setMinimumHeight(92)
        conn_btn_row = QHBoxLayout()
        conn_detach = QPushButton("Detach selected")
        conn_detach_all = QPushButton("Detach all from port")
        for b in (conn_detach, conn_detach_all):
            b.setStyleSheet(self.host._glass_btn_css())
            b.setCursor(Qt.PointingHandCursor)
            conn_btn_row.addWidget(b)
        conn_l.addWidget(conn_info)
        conn_l.addWidget(conn_list, 1)
        conn_l.addLayout(conn_btn_row)
        rl.addWidget(conn_box, 0)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 4)
        lay.addWidget(split, 1)
        btm = QHBoxLayout()
        ok = QPushButton(self._t("ok", "OK"))
        cancel = QPushButton(self._t("cancel", "Cancel"))
        ok.setStyleSheet(self.host._glass_btn_css())
        cancel.setStyleSheet(self.host._glass_btn_css())
        btm.addStretch(1)
        btm.addWidget(ok)
        btm.addWidget(cancel)
        lay.addLayout(btm)
        state = {"full": False}

        def _tog():
            state["full"] = not state["full"]
            if state["full"]:
                dlg.showFullScreen()
            else:
                dlg.showNormal()

        fs.clicked.connect(_tog)

        def _refresh_list():
            chain = self.state.get("node_chain", []) or []
            lst.blockSignals(True)
            lst.clear()
            for n in chain:
                lst.addItem(str(n))
            lst.blockSignals(False)
            canvas.set_graph(chain, self.state.get("node_links", []) or [], self.state.get("node_io", []) or [])
            if lst.count() > 0:
                lst.setCurrentRow(max(0, min(lst.count() - 1, int(canvas._selected if canvas._selected >= 0 else 0))))
            _refresh_port_links()

        def _refresh_port_links():
            conn_list.clear()
            info = canvas.selected_port()
            if not isinstance(info, dict):
                conn_info.setText("Port inspector: select node input/output port.")
                conn_detach.setEnabled(False)
                conn_detach_all.setEnabled(False)
                return
            try:
                pidx = int(info.get("idx", -1))
                pside = str(info.get("side", "")).strip().lower()
                pnum = int(info.get("port", 0))
            except Exception:
                pidx = -1
                pside = ""
                pnum = 0
            chain = self.state.get("node_chain", []) or []
            if pidx < 0 or pidx >= len(chain) or pside not in ("in", "out"):
                conn_info.setText("Port inspector: select node input/output port.")
                conn_detach.setEnabled(False)
                conn_detach_all.setEnabled(False)
                return
            ptype = canvas._port_type(pidx, pside, pnum)
            badge = canvas._port_badge(ptype)
            side_name = "Input" if pside == "in" else "Output"
            conn_info.setText(f"{chain[pidx]}  {side_name} {pnum + 1}  [{ptype}/{badge}]")
            links = canvas.links_for_port(info)
            for lk in links:
                try:
                    a, b = int(lk[0]), int(lk[1])
                    op = int(lk[2]) if len(lk) >= 3 else 0
                    ip = int(lk[3]) if len(lk) >= 4 else 0
                except Exception:
                    continue
                sname = chain[a] if 0 <= a < len(chain) else f"node {a}"
                dname = chain[b] if 0 <= b < len(chain) else f"node {b}"
                it = QListWidgetItem(f"{sname}:O{op + 1}  ->  {dname}:I{ip + 1}")
                it.setData(Qt.UserRole, [a, b, op, ip])
                conn_list.addItem(it)
            has = conn_list.count() > 0
            conn_detach.setEnabled(has)
            conn_detach_all.setEnabled(has)

        def _load_idx(i):
            try:
                i = int(i)
            except Exception:
                i = -1
            arr = self.state.get("node_params", []) or []
            io_arr = self.state.get("node_io", []) or []
            chain = self.state.get("node_chain", []) or []
            if i < 0 or i >= len(arr):
                en.setChecked(False)
                intensity.setValue(0)
                radius.setValue(0)
                mix.setValue(100)
                value.setValue(0)
                seed.setValue(0)
                in_spin.setValue(1)
                out_spin.setValue(1)
                in_type.setCurrentIndex(0)
                out_type.setCurrentIndex(0)
                en.setEnabled(False)
                intensity.setEnabled(False)
                radius.setEnabled(False)
                mix.setEnabled(False)
                value.setEnabled(False)
                seed.setEnabled(False)
                in_spin.setEnabled(False)
                out_spin.setEnabled(False)
                in_type.setEnabled(False)
                out_type.setEnabled(False)
                desc.setText("")
                return
            en.setEnabled(True)
            intensity.setEnabled(True)
            radius.setEnabled(True)
            mix.setEnabled(True)
            value.setEnabled(True)
            seed.setEnabled(True)
            in_spin.setEnabled(True)
            out_spin.setEnabled(True)
            in_type.setEnabled(True)
            out_type.setEnabled(True)
            p = arr[i]
            io = io_arr[i] if i < len(io_arr) and isinstance(io_arr[i], dict) else {"inputs": 1, "outputs": 1}
            en.setChecked(bool(p.get("enabled", True)))
            intensity.setValue(int(p.get("intensity", 55)))
            radius.setValue(int(p.get("radius", 2)))
            mix.setValue(int(p.get("mix", 100)))
            value.setValue(int(p.get("value", 0)))
            seed.setValue(int(p.get("seed", 0)))
            in_spin.setValue(int(io.get("inputs", 1)))
            out_spin.setValue(int(io.get("outputs", 1)))
            in_types = io.get("in_types", [io.get("input_type", "video")]) or ["video"]
            out_types = io.get("out_types", [io.get("output_type", "video")]) or ["video"]
            ii = in_type.findText(str(in_types[0]).strip().lower())
            oi = out_type.findText(str(out_types[0]).strip().lower())
            in_type.setCurrentIndex(ii if ii >= 0 else 0)
            out_type.setCurrentIndex(oi if oi >= 0 else 0)
            node_id = str(chain[i]).strip().lower() if i < len(chain) else ""
            desc.setText(self._node_descriptions().get(node_id, ""))

        def _save_idx():
            i = lst.currentRow()
            arr = self.state.get("node_params", []) or []
            if i < 0 or i >= len(arr):
                return
            arr[i]["enabled"] = bool(en.isChecked())
            arr[i]["intensity"] = int(intensity.value())
            arr[i]["radius"] = int(radius.value())
            arr[i]["mix"] = int(mix.value())
            arr[i]["value"] = int(value.value())
            arr[i]["seed"] = int(seed.value())
            io_arr = self.state.get("node_io", []) or []
            if i >= 0 and i < len(io_arr):
                io_arr[i]["inputs"] = int(in_spin.value())
                io_arr[i]["outputs"] = int(out_spin.value())
                it = str(in_type.currentText() or "video").strip().lower()
                ot = str(out_type.currentText() or "video").strip().lower()
                if it not in ("video", "audio", "data", "any"):
                    it = "video"
                if ot not in ("video", "audio", "data", "any"):
                    ot = "video"
                io_arr[i]["in_types"] = [it for _ in range(max(1, int(io_arr[i]["inputs"])))]
                io_arr[i]["out_types"] = [ot for _ in range(max(1, int(io_arr[i]["outputs"])))]
                io_arr[i]["input_type"] = it
                io_arr[i]["output_type"] = ot
            canvas.set_graph(self.state.get("node_chain", []) or [], self.state.get("node_links", []) or [], self.state.get("node_io", []) or [])
            _refresh_port_links()

        def _add_local():
            node_id = str(node_pick.currentData() or "").strip()
            if not node_id:
                return
            chain = self.state.setdefault("node_chain", [])
            chain.append(node_id)
            prm = self.state.setdefault("node_params", [])
            prm.append(self._default_node_params(node_id))
            io_arr = self.state.setdefault("node_io", [])
            io_arr.append(dict(self._default_node_io(node_id)))
            links = self.state.setdefault("node_links", [])
            if len(chain) >= 2 and not links:
                src = len(chain) - 2
                dst = len(chain) - 1
                a = self._node_port_type_from_state(src, "out")
                b = self._node_port_type_from_state(dst, "in")
                if a == "any" or b == "any" or a == b:
                    links.append([src, dst, 0, 0])
            _refresh_list()
            lst.setCurrentRow(max(0, lst.count() - 1))

        def _remove_local():
            i = int(lst.currentRow())
            chain = self.state.setdefault("node_chain", [])
            if i < 0 or i >= len(chain):
                return
            chain.pop(i)
            prm = self.state.setdefault("node_params", [])
            if i < len(prm):
                prm.pop(i)
            io_arr = self.state.setdefault("node_io", [])
            if i < len(io_arr):
                io_arr.pop(i)
            links = []
            for link in (self.state.get("node_links", []) or []):
                try:
                    a, b = int(link[0]), int(link[1])
                    op = int(link[2]) if len(link) >= 3 else 0
                    ip = int(link[3]) if len(link) >= 4 else 0
                except Exception:
                    continue
                if a == i or b == i:
                    continue
                if a > i:
                    a -= 1
                if b > i:
                    b -= 1
                if a != b:
                    links.append([a, b, op, ip])
            self.state["node_links"] = links
            _refresh_list()

        lst.currentRowChanged.connect(lambda i: (canvas.nodeSelected.emit(int(i)), _load_idx(i)))
        canvas.nodeSelected.connect(lambda i: lst.setCurrentRow(int(i)))
        canvas.linksChanged.connect(lambda links: self.state.__setitem__("node_links", [list(x) for x in (links or [])]))
        canvas.portSelected.connect(lambda *_: _refresh_port_links())
        canvas.linksChanged.connect(lambda *_: _refresh_port_links())
        add_btn.clicked.connect(_add_local)
        rem_btn.clicked.connect(_remove_local)
        conn_detach.clicked.connect(lambda: (canvas.remove_link(conn_list.currentItem().data(Qt.UserRole)) if conn_list.currentItem() is not None else None))
        conn_detach_all.clicked.connect(lambda: canvas.remove_links_for_port())
        en.stateChanged.connect(lambda *_: _save_idx())
        intensity.valueChanged.connect(lambda *_: _save_idx())
        radius.valueChanged.connect(lambda *_: _save_idx())
        mix.valueChanged.connect(lambda *_: _save_idx())
        value.valueChanged.connect(lambda *_: _save_idx())
        seed.valueChanged.connect(lambda *_: _save_idx())
        in_spin.valueChanged.connect(lambda *_: _save_idx())
        out_spin.valueChanged.connect(lambda *_: _save_idx())
        in_type.currentTextChanged.connect(lambda *_: _save_idx())
        out_type.currentTextChanged.connect(lambda *_: _save_idx())
        if lst.count() > 0:
            try:
                idx0 = int(focus_idx)
            except Exception:
                idx0 = 0
            idx0 = max(0, min(lst.count() - 1, idx0))
            lst.setCurrentRow(idx0)
        _refresh_port_links()
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        if dlg.exec() == QDialog.Accepted:
            self.state["node_links"] = [list(x) for x in (canvas.links or [])]
            self._refresh_nodes()
            self._render_preview()
        else:
            self.state["node_chain"] = backup_chain
            self.state["node_params"] = backup_params
            self.state["node_io"] = backup_io
            self.state["node_links"] = backup_links
            self._refresh_nodes()
            self._render_preview()

    def _open_preview_context_menu(self, pos):
        menu = QMenu(self)
        add_text = QAction(self._t("editor_add_layer", "Add text layer"), self)
        add_media = QAction(self._t("editor_add_media_layer", "Add media layer"), self)
        add_node = QAction(self._t("editor_add_node", "Add node"), self)
        add_audio = QAction(self._t("editor_import_audio", "Import audio"), self)
        reset_crop = QAction("Reset crop", self)
        reset_mask = QAction("Reset mask", self)
        trim_start = QAction("Trim selected start to playhead", self)
        trim_end = QAction("Trim selected end to playhead", self)
        split_clip = QAction("Split selected clip at playhead", self)
        add_text.triggered.connect(self._add_layer)
        add_media.triggered.connect(self._add_media_layer_and_pick)
        add_node.triggered.connect(self._add_node)
        add_audio.triggered.connect(self._audio_import)
        reset_crop.triggered.connect(self._reset_crop)
        reset_mask.triggered.connect(self._reset_mask)
        trim_start.triggered.connect(self._trim_selected_to_playhead_start)
        trim_end.triggered.connect(self._trim_selected_to_playhead_end)
        split_clip.triggered.connect(lambda: self._split_selected_clip_at_time(int(self.time_slider.value())))
        menu.addAction(add_text)
        menu.addAction(add_media)
        menu.addAction(add_audio)
        menu.addAction(add_node)
        menu.addSeparator()
        mode_crop = QAction(self._t("editor_crop_mode", "Crop area"), self)
        mode_mask = QAction(self._t("editor_mask_mode", "Mask area"), self)
        mode_text = QAction(self._t("editor_text_mode", "Layer move"), self)
        mode_media = QAction(self._t("editor_media_mode", "Media layer move"), self)
        mode_crop.triggered.connect(lambda: (self.crop_enable.setChecked(True), self.tabs.setCurrentWidget(getattr(self, "crop_mask_tab_ref", self.tabs.currentWidget()))))
        mode_mask.triggered.connect(lambda: (self.mask_enable.setChecked(True), self.tabs.setCurrentWidget(getattr(self, "crop_mask_tab_ref", self.tabs.currentWidget()))))
        mode_text.triggered.connect(lambda: self.tabs.setCurrentWidget(getattr(self, "layers_tab_ref", self.tabs.currentWidget())))
        mode_media.triggered.connect(lambda: self.tabs.setCurrentWidget(getattr(self, "layers_tab_ref", self.tabs.currentWidget())))
        menu.addAction(mode_crop)
        menu.addAction(mode_mask)
        menu.addAction(mode_text)
        menu.addAction(mode_media)
        menu.addSeparator()
        menu.addAction(trim_start)
        menu.addAction(trim_end)
        menu.addAction(split_clip)
        menu.addSeparator()
        menu.addAction(reset_crop)
        menu.addAction(reset_mask)
        menu.exec(self.preview.mapToGlobal(pos))

    def _reset_crop(self):
        self.crop_enable.setChecked(False)
        self.crop_x.setValue(0)
        self.crop_y.setValue(0)
        self.crop_w.setValue(int(self.src.width))
        self.crop_h.setValue(int(self.src.height))
        self._render_preview()

    def _reset_mask(self):
        self.mask_enable.setChecked(False)
        self.mask_x.setValue(0)
        self.mask_y.setValue(0)
        self.mask_w.setValue(int(self.src.width))
        self.mask_h.setValue(int(self.src.height))
        self.mask_use_image_chk.setChecked(False)
        self.mask_media_path.setText("")
        self._render_preview()

    def _load_script(self):
        fn, _ = QFileDialog.getOpenFileName(self, self._t("editor_load_script", "Load script"), os.getcwd(), "Python (*.py)")
        if not fn:
            return
        try:
            self.nodes_code.setPlainText(Path(fn).read_text(encoding="utf-8"))
        except Exception:
            pass

    def _save_script(self):
        fn, _ = QFileDialog.getSaveFileName(self, self._t("editor_save_script", "Save script"), os.getcwd(), "Python (*.py)")
        if not fn:
            return
        try:
            if not fn.lower().endswith(".py"):
                fn += ".py"
            Path(fn).write_text(self.nodes_code.toPlainText(), encoding="utf-8")
        except Exception:
            pass

    def _save_node_graph(self):
        fn, _ = QFileDialog.getSaveFileName(self, "Save node graph", os.getcwd(), "JSON (*.json)")
        if not fn:
            return
        if not fn.lower().endswith(".json"):
            fn += ".json"
        try:
            import json
            payload = {
                "node_chain": copy.deepcopy(self.state.get("node_chain", []) or []),
                "node_params": copy.deepcopy(self.state.get("node_params", []) or []),
                "node_io": copy.deepcopy(self.state.get("node_io", []) or []),
                "node_links": copy.deepcopy(self.state.get("node_links", []) or []),
                "nodes_code": str(self.nodes_code.toPlainText() or ""),
            }
            Path(fn).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_node_graph(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Load node graph", os.getcwd(), "JSON (*.json)")
        if not fn:
            return
        try:
            import json
            data = json.loads(Path(fn).read_text(encoding="utf-8"))
            self.state["node_chain"] = list(data.get("node_chain", []) or [])
            self.state["node_params"] = list(data.get("node_params", []) or [])
            self.state["node_io"] = list(data.get("node_io", []) or [])
            self.state["node_links"] = list(data.get("node_links", []) or [])
            code = str(data.get("nodes_code", "") or "")
            self.nodes_code.setPlainText(code)
            self._normalize_state()
            self._ensure_node_params()
            self._ensure_node_io()
            self._refresh_nodes()
            self._load_node_param_controls()
            self._render_preview()
        except Exception:
            pass

    def _clear_node_graph(self):
        self.state["node_chain"] = []
        self.state["node_params"] = []
        self.state["node_io"] = []
        self.state["node_links"] = []
        self.state["nodes_enabled"] = False
        try:
            self.nodes_enable.setChecked(False)
        except Exception:
            pass
        try:
            self.nodes_code.clear()
        except Exception:
            pass
        self._refresh_nodes()
        self._schedule_node_preview(0)
        self._render_preview()

    def _focused_text_input(self):
        try:
            fw = self.focusWidget()
            return isinstance(fw, (QLineEdit, QTextEdit))
        except Exception:
            return False

    def _delete_selected_entity(self):
        if self._focused_text_input():
            return
        if hasattr(self, "tabs"):
            cw = self.tabs.currentWidget()
            if cw is getattr(self, "nodes_tab_ref", None):
                self._remove_node()
                return
            if cw is getattr(self, "audio_tab_ref", None):
                self._audio_clear()
                return
        if hasattr(self, "media_list") and self.media_list.hasFocus():
            self._remove_media_layer()
            return
        if hasattr(self, "layers_list") and self.layers_list.hasFocus():
            self._remove_layer()
            return
        # Fallback: remove selected clip from timeline context.
        self._ripple_delete_selected_clip()

    def _toggle_play_shortcut(self):
        if self._focused_text_input():
            return
        self._toggle_timeline_play()

    def _timeline_mode_shortcut(self, mode):
        if self._focused_text_input():
            return
        self._set_timeline_tool_mode(mode)

    def _nodes_tab_active(self):
        try:
            return bool(hasattr(self, "tabs") and self.tabs.currentWidget() is getattr(self, "nodes_tab_ref", None))
        except Exception:
            return False

    def _tab_add_node_shortcut(self):
        if self._focused_text_input():
            return
        if not self._nodes_tab_active():
            return
        self._add_node()

    def _init_shortcuts(self):
        self._shortcuts = []

        def _mk(seq, fn):
            try:
                sc = QShortcut(QKeySequence(seq), self)
                sc.setContext(Qt.ApplicationShortcut)
                sc.activated.connect(lambda f=fn: f())
                self._shortcuts.append(sc)
            except Exception:
                pass

        _mk("Space", self._toggle_play_shortcut)
        _mk("K", self._stop_timeline_play)
        _mk("Ctrl+B", lambda: self._split_selected_clip_at_time(int(self.time_slider.value())))
        _mk("Ctrl+D", self._duplicate_selected_clip)
        _mk("Ctrl+R", self._change_selected_clip_speed)
        _mk("Ctrl+G", self._group_selected_clip)
        _mk("Ctrl+Shift+G", self._ungroup_selected_clip)
        _mk("I", self._set_selected_start_keyframe)
        _mk("O", self._set_selected_end_keyframe)
        _mk("Delete", self._delete_selected_entity)
        _mk("Ctrl+N", self._reset_editor)
        _mk("Ctrl+Shift+N", self._add_layer)
        _mk("Ctrl+M", self._add_media_layer_and_pick)
        _mk("Ctrl+Alt+G", self._open_node_workspace)
        _mk("Ctrl+I", self._add_media_layer_and_pick)
        _mk("Ctrl+O", self._add_media_layer_and_pick)
        _mk("Ctrl+S", self._request_accept)
        _mk("Ctrl+Shift+S", self._save_node_graph)
        _mk("Ctrl+E", self._request_accept)
        _mk("Ctrl+Q", self._request_reject)
        _mk("Ctrl+W", self._request_reject)
        _mk("F11", self._toggle_fullscreen)
        _mk("Left", lambda: self._timeline_seek_relative(-self._frame_step_ms()))
        _mk("Right", lambda: self._timeline_seek_relative(self._frame_step_ms()))
        _mk("Shift+Left", lambda: self._timeline_seek_relative(-max(10, self._frame_step_ms() * 5)))
        _mk("Shift+Right", lambda: self._timeline_seek_relative(max(10, self._frame_step_ms() * 5)))
        _mk("Home", self._timeline_seek_home)
        _mk("End", self._timeline_seek_end)
        _mk("Ctrl++", self._timeline_zoom_in)
        _mk("Ctrl+=", self._timeline_zoom_in)
        _mk("Ctrl+-", self._timeline_zoom_out)
        _mk("V", lambda: self._timeline_mode_shortcut("select"))
        _mk("C", lambda: self._timeline_mode_shortcut("razor"))
        _mk("T", lambda: self._timeline_mode_shortcut("trim"))
        _mk("R", lambda: self._timeline_mode_shortcut("ripple"))
        if not bool(getattr(self, "_always_interactive", False)):
            _mk("Alt+1", lambda: self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData("off"))))
            _mk("Alt+2", lambda: self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData("crop"))))
            _mk("Alt+3", lambda: self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData("mask"))))
            _mk("Alt+4", lambda: self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData("text"))))
            _mk("Alt+5", lambda: self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData("media"))))

    def _reset_editor(self):
        self._preview_zoom = 1.0
        self._preview_zoom_target = 1.0
        self._preview_pan_x = 0.0
        self._preview_pan_y = 0.0
        self._preview_cache_key = ""
        self._preview_cache_img = None
        self.state = {
            "enabled": False,
            "brightness": 100,
            "contrast": 100,
            "saturation": 100,
            "sharpness": 100,
            "hue": 0,
            "exposure": 0,
            "temperature": 0,
            "crop_enabled": False,
            "crop_x": 0,
            "crop_y": 0,
            "crop_w": self.src.width,
            "crop_h": self.src.height,
            "mask_enabled": False,
            "mask_x": 0,
            "mask_y": 0,
            "mask_w": self.src.width,
            "mask_h": self.src.height,
            "mask_use_image": False,
            "mask_image_path": "",
            "trim_enabled": False,
            "trim_start_ms": 0,
            "trim_end_ms": self.duration_ms,
            "audio_path": "",
            "audio_gain_db": 0.0,
            "audio_lowpass_hz": 0,
            "nodes_enabled": False,
            "nodes_preview": False,
            "nodes_code": "",
            "node_chain": [],
            "node_links": [],
            "node_params": [],
            "node_io": [],
            "ascii_bridge_enabled": False,
            "ascii_bridge_apply": False,
            "ascii_style": str(getattr(self.host, "style", "bw") or "bw"),
            "ascii_width": int(getattr(self.host, "width_chars", 120) or 120),
            "ascii_font_size": int(getattr(self.host, "font_size", 10) or 10),
            "ascii_charset": str(getattr(self.host, "ascii_chars", "") or ""),
            "ascii_fg_hex": str(getattr(self.host, "fg_hex", "#ffffff") or "#ffffff"),
            "ascii_bg_hex": str(getattr(self.host, "bg_hex", "#000000") or "#000000"),
            "ascii_pro_tools": bool(getattr(self.host, "pro_tools", False)),
            "ascii_pro_bloom": int(getattr(self.host, "pro_bloom", 0) or 0),
            "ascii_pro_vignette": int(getattr(self.host, "pro_vignette", 0) or 0),
            "ascii_pro_grain": int(getattr(self.host, "pro_grain", 0) or 0),
            "ascii_pro_chroma": int(getattr(self.host, "pro_chroma", 0) or 0),
            "ascii_pro_glitch": int(getattr(self.host, "pro_glitch", 0) or 0),
            "photo_paint_enabled": False,
            "photo_paint_opacity": 100,
            "photo_paint_png_b64": "",
            "photo_paint_hash": "",
            "photo_brush_size": 26,
            "photo_brush_opacity": 92,
            "photo_brush_color_rgba": list(getattr(self, "_photo_brush_rgba", (236, 244, 255, 220))),
            "media_layers": [],
            "text_layers": [],
        }
        self._photo_paint_layer = None
        self._photo_paint_serialized = ""
        self._photo_paint_dirty = False
        self._sync_from_state()
        self._render_preview()

    def _view_to_img(self, vx, vy):
        ox = int(self.preview_meta["ox"])
        oy = int(self.preview_meta["oy"])
        sc = float(self.preview_meta["scale"])
        if sc <= 0.0:
            return 0, 0
        ix = int((float(vx) - ox) / sc)
        iy = int((float(vy) - oy) / sc)
        ix = max(0, min(self.src.width - 1, ix))
        iy = max(0, min(self.src.height - 1, iy))
        return ix, iy

    def _img_to_view(self, ix, iy):
        ox = int(self.preview_meta["ox"])
        oy = int(self.preview_meta["oy"])
        sc = float(self.preview_meta["scale"])
        if sc <= 0.0:
            return int(ix), int(iy)
        vx = int(round(float(ix) * sc + ox))
        vy = int(round(float(iy) * sc + oy))
        return vx, vy

    def _rect_hit_type(self, ix, iy, rect):
        try:
            x, y, w, h = [int(v) for v in rect]
        except Exception:
            return None
        x2 = x + w
        y2 = y + h
        sc = max(0.2, float(self.preview_meta.get("scale", 1.0) or 1.0))
        tol = max(3, int(round(9.0 / sc)))
        pts = {
            "nw": (x, y),
            "ne": (x2, y),
            "sw": (x, y2),
            "se": (x2, y2),
        }
        for name, (px, py) in pts.items():
            if abs(ix - px) <= tol and abs(iy - py) <= tol:
                return name
        if abs(iy - y) <= tol and x <= ix <= x2:
            return "n"
        if abs(iy - y2) <= tol and x <= ix <= x2:
            return "s"
        if abs(ix - x) <= tol and y <= iy <= y2:
            return "w"
        if abs(ix - x2) <= tol and y <= iy <= y2:
            return "e"
        if x <= ix <= x2 and y <= iy <= y2:
            return "move"
        return None

    def _detect_rect_drag(self, ix, iy):
        crop_rect = self._clamp_rect(self.crop_x.value(), self.crop_y.value(), self.crop_w.value(), self.crop_h.value())
        mask_rect = self._clamp_rect(self.mask_x.value(), self.mask_y.value(), self.mask_w.value(), self.mask_h.value())
        text_rect = None
        media_rect = None
        try:
            text_rect = self._guide_rects.get("text")
        except Exception:
            text_rect = None
        try:
            media_rect = self._guide_rects.get("media")
        except Exception:
            media_rect = None
        # Fallback for first click before guides are drawn.
        try:
            if text_rect is None:
                layer, _ = self._selected_layer()
                if layer is not None and bool(str(layer.get("text", "") or "").strip()):
                    lx, ly = self.host._layer_t_xy(layer, int(self.time_slider.value()))
                    font = self.host._safe_font(layer.get("font", "Arial"), int(layer.get("size", 36)))
                    dummy = Image.new("RGB", (8, 8), (0, 0, 0))
                    dd = ImageDraw.Draw(dummy)
                    bb = dd.textbbox((0, 0), str(layer.get("text", "")), font=font)
                    tw = max(1, bb[2] - bb[0]); th = max(1, bb[3] - bb[1])
                    tw = int(tw * max(0.1, min(8.0, float(layer.get("scale_x", 1.0)))))
                    th = int(th * max(0.1, min(8.0, float(layer.get("scale_y", 1.0)))))
                    text_rect = (int(lx), int(ly), max(1, int(tw)), max(1, int(th)))
        except Exception:
            text_rect = None
        try:
            if media_rect is None:
                med, _ = self._selected_media_layer()
                if med is not None and bool(str(med.get("path", "") or "").strip()):
                    frame = self.host._load_media_layer_frame(med, int(self.time_slider.value()))
                    if frame is not None:
                        sx = max(0.05, min(8.0, float(med.get("scale_x", 1.0) or 1.0)))
                        sy = max(0.05, min(8.0, float(med.get("scale_y", 1.0) or 1.0)))
                        mw = max(1, int(frame.width * sx))
                        mh = max(1, int(frame.height * sy))
                        mx, my = self.host._layer_t_xy(med, int(self.time_slider.value()))
                        media_rect = (int(mx), int(my), max(1, int(mw)), max(1, int(mh)))
        except Exception:
            media_rect = None

        pref = str(self._active_interaction_mode() or "off")
        checks = []
        if pref in ("media", "text", "crop", "mask"):
            checks.append(pref)
        for m in ("media", "text", "crop", "mask"):
            if m not in checks:
                checks.append(m)
        for mode in checks:
            if mode == "crop":
                enabled = bool(self.crop_enable.isChecked())
                rect = crop_rect
            elif mode == "mask":
                enabled = bool(self.mask_enable.isChecked()) or bool(self.mask_use_image_chk.isChecked())
                rect = mask_rect
            elif mode == "text":
                lyr, _ = self._selected_layer()
                enabled = lyr is not None and text_rect is not None
                rect = text_rect
            else:
                med, _ = self._selected_media_layer()
                enabled = med is not None and media_rect is not None
                rect = media_rect
            if not enabled or rect is None:
                continue
            hit = self._rect_hit_type(ix, iy, rect)
            if not hit:
                continue
            kind = "move" if hit == "move" else "resize_handle"
            return {"mode": mode, "kind": kind, "handle": None if hit == "move" else hit, "rect": rect}
        return None

    def _drag_rect(self, rect, dx, dy, kind, handle=None):
        x, y, w, h = [int(v) for v in rect]
        if kind == "move":
            return self._clamp_rect(x + dx, y + dy, w, h)
        if kind == "resize":
            return self._clamp_rect(x, y, w + dx, h + dy)
        x0 = int(x)
        y0 = int(y)
        x1 = int(x + w)
        y1 = int(y + h)
        handle = str(handle or "").lower()
        if "w" in handle:
            x0 += int(dx)
        if "e" in handle:
            x1 += int(dx)
        if "n" in handle:
            y0 += int(dy)
        if "s" in handle:
            y1 += int(dy)
        x0 = max(0, min(self.src.width - 1, x0))
        y0 = max(0, min(self.src.height - 1, y0))
        x1 = max(x0 + 1, min(self.src.width, x1))
        y1 = max(y0 + 1, min(self.src.height, y1))
        return self._clamp_rect(x0, y0, x1 - x0, y1 - y0)

    def _preview_press(self, ev):
        try:
            if ev.button() == Qt.MiddleButton:
                self._preview_pan_drag = True
                try:
                    pos = ev.position()
                except Exception:
                    pos = ev.pos()
                self._preview_pan_anchor = QPoint(int(pos.x()), int(pos.y()))
                self._preview_pan_start = (float(self._preview_pan_x), float(self._preview_pan_y))
                return
        except Exception:
            pass
        try:
            if ev.button() == Qt.RightButton:
                self.drag["kind"] = None
                self.drag["handle"] = None
                return
        except Exception:
            pass
        try:
            pos = ev.position()
        except Exception:
            pos = ev.pos()
        ix, iy = self._view_to_img(pos.x(), pos.y())
        if bool(self.photo_mode):
            try:
                tool = str(getattr(self, "_photo_active_tool", "move") or "move").strip().lower()
            except Exception:
                tool = "move"
            if ev.button() == Qt.LeftButton and tool in ("brush", "eraser"):
                try:
                    if hasattr(self, "photo_paint_enable_chk") and (not self.photo_paint_enable_chk.isChecked()):
                        return
                except Exception:
                    pass
                ix = max(0, min(self.src.width - 1, int(ix)))
                iy = max(0, min(self.src.height - 1, int(iy)))
                self._photo_paint_stroking = True
                self._photo_last_paint_xy = (int(ix), int(iy))
                self._paint_photo_stroke(ix, iy, ix, iy)
                self._schedule_render_preview(0, fast=True)
                return
        direct = self._detect_rect_drag(ix, iy)
        if direct is not None:
            self.drag["mode"] = str(direct.get("mode", "off"))
            self.drag["kind"] = str(direct.get("kind", "move"))
            self.drag["handle"] = direct.get("handle")
            self.drag["start_ix"] = int(ix)
            self.drag["start_iy"] = int(iy)
            self.drag["rect"] = tuple(direct.get("rect", (0, 0, 1, 1)))
            if self.drag["mode"] == "crop":
                self.crop_enable.setChecked(True)
            elif self.drag["mode"] == "mask":
                self.mask_enable.setChecked(True)
            elif self.drag["mode"] == "text":
                layer, idx = self._selected_layer()
                self.drag["layer"] = idx
                if layer is not None:
                    self.drag["base_scale_x"] = float(layer.get("scale_x", 1.0) or 1.0)
                    self.drag["base_scale_y"] = float(layer.get("scale_y", 1.0) or 1.0)
                    self.drag["base_x"] = int(layer.get("x", 0) or 0)
                    self.drag["base_y"] = int(layer.get("y", 0) or 0)
                    self.drag["base_x1"] = int(layer.get("x1", self.drag["base_x"]) or self.drag["base_x"])
                    self.drag["base_y1"] = int(layer.get("y1", self.drag["base_y"]) or self.drag["base_y"])
            elif self.drag["mode"] == "media":
                layer, idx = self._selected_media_layer()
                self.drag["layer"] = idx
                if layer is not None:
                    self.drag["base_scale_x"] = float(layer.get("scale_x", 1.0) or 1.0)
                    self.drag["base_scale_y"] = float(layer.get("scale_y", 1.0) or 1.0)
                    self.drag["base_x"] = int(layer.get("x", 0) or 0)
                    self.drag["base_y"] = int(layer.get("y", 0) or 0)
                    self.drag["base_x1"] = int(layer.get("x1", self.drag["base_x"]) or self.drag["base_x"])
                    self.drag["base_y1"] = int(layer.get("y1", self.drag["base_y"]) or self.drag["base_y"])
            j = self.mode_combo.findData(self.drag["mode"])
            if j >= 0:
                self.mode_combo.setCurrentIndex(j)
            return
        mode = self._active_interaction_mode()
        self.drag["mode"] = mode
        resize_mod = False
        try:
            resize_mod = bool(ev.modifiers() & Qt.ShiftModifier)
        except Exception:
            resize_mod = False
        self.drag["kind"] = "resize" if resize_mod else "move"
        self.drag["handle"] = None
        self.drag["start_ix"] = int(ix)
        self.drag["start_iy"] = int(iy)
        if mode == "crop":
            self.crop_enable.setChecked(True)
            self.drag["rect"] = self._clamp_rect(self.crop_x.value(), self.crop_y.value(), self.crop_w.value(), self.crop_h.value())
        elif mode == "mask":
            self.mask_enable.setChecked(True)
            self.drag["rect"] = self._clamp_rect(self.mask_x.value(), self.mask_y.value(), self.mask_w.value(), self.mask_h.value())
        elif mode == "text":
            _, idx = self._selected_layer()
            self.drag["layer"] = idx
            layer, _ = self._selected_layer()
            if layer is not None:
                self.drag["base_scale_x"] = float(layer.get("scale_x", 1.0) or 1.0)
                self.drag["base_scale_y"] = float(layer.get("scale_y", 1.0) or 1.0)
                self.drag["base_x"] = int(layer.get("x", 0) or 0)
                self.drag["base_y"] = int(layer.get("y", 0) or 0)
                self.drag["base_x1"] = int(layer.get("x1", self.drag["base_x"]) or self.drag["base_x"])
                self.drag["base_y1"] = int(layer.get("y1", self.drag["base_y"]) or self.drag["base_y"])
                try:
                    self.drag["rect"] = tuple(self._guide_rects.get("text") or self.drag.get("rect", (0, 0, 1, 1)))
                except Exception:
                    pass
        elif mode == "media":
            _, idx = self._selected_media_layer()
            self.drag["layer"] = idx
            layer, _ = self._selected_media_layer()
            if layer is not None:
                self.drag["base_scale_x"] = float(layer.get("scale_x", 1.0) or 1.0)
                self.drag["base_scale_y"] = float(layer.get("scale_y", 1.0) or 1.0)
                self.drag["base_x"] = int(layer.get("x", 0) or 0)
                self.drag["base_y"] = int(layer.get("y", 0) or 0)
                self.drag["base_x1"] = int(layer.get("x1", self.drag["base_x"]) or self.drag["base_x"])
                self.drag["base_y1"] = int(layer.get("y1", self.drag["base_y"]) or self.drag["base_y"])
                try:
                    self.drag["rect"] = tuple(self._guide_rects.get("media") or self.drag.get("rect", (0, 0, 1, 1)))
                except Exception:
                    pass
        else:
            self.drag["kind"] = None

    def _preview_move(self, ev):
        if bool(self._preview_pan_drag):
            try:
                pos = ev.position()
            except Exception:
                pos = ev.pos()
            dx = float(pos.x() - self._preview_pan_anchor.x())
            dy = float(pos.y() - self._preview_pan_anchor.y())
            self._preview_pan_x = float(self._preview_pan_start[0] + dx)
            self._preview_pan_y = float(self._preview_pan_start[1] + dy)
            self._schedule_render_preview(0, fast=True)
            return
        if bool(self.photo_mode) and bool(getattr(self, "_photo_paint_stroking", False)):
            try:
                pos = ev.position()
            except Exception:
                pos = ev.pos()
            ix, iy = self._view_to_img(pos.x(), pos.y())
            ix = max(0, min(self.src.width - 1, int(ix)))
            iy = max(0, min(self.src.height - 1, int(iy)))
            lx, ly = self._photo_last_paint_xy if isinstance(self._photo_last_paint_xy, tuple) else (ix, iy)
            self._paint_photo_stroke(lx, ly, ix, iy)
            self._photo_last_paint_xy = (ix, iy)
            self._schedule_render_preview(0, fast=True)
            return
        if not self.drag.get("kind"):
            return
        try:
            pos = ev.position()
        except Exception:
            pos = ev.pos()
        ix, iy = self._view_to_img(pos.x(), pos.y())
        dx = int(ix - self.drag.get("start_ix", 0))
        dy = int(iy - self.drag.get("start_iy", 0))
        mode = self.drag.get("mode")
        if mode in ("crop", "mask"):
            x, y, w, h = self.drag.get("rect", (0, 0, 1, 1))
            if self.drag.get("kind") == "resize":
                nx, ny, nw, nh = self._drag_rect((x, y, w, h), dx, dy, "resize")
            elif self.drag.get("kind") == "resize_handle":
                nx, ny, nw, nh = self._drag_rect((x, y, w, h), dx, dy, "resize_handle", self.drag.get("handle"))
            else:
                nx, ny, nw, nh = self._drag_rect((x, y, w, h), dx, dy, "move")
            if mode == "crop":
                self.crop_x.setValue(nx); self.crop_y.setValue(ny); self.crop_w.setValue(nw); self.crop_h.setValue(nh)
            else:
                self.mask_x.setValue(nx); self.mask_y.setValue(ny); self.mask_w.setValue(nw); self.mask_h.setValue(nh)
        elif mode == "text":
            layer, idx = self._selected_layer()
            if layer is None or idx < 0:
                return
            if self.drag.get("kind") in ("resize", "resize_handle"):
                rx, ry, rw, rh = [int(v) for v in self.drag.get("rect", (0, 0, 1, 1))]
                if self.drag.get("kind") == "resize_handle":
                    nx, ny, nw, nh = self._drag_rect((rx, ry, rw, rh), dx, dy, "resize_handle", self.drag.get("handle"))
                else:
                    nx, ny, nw, nh = self._drag_rect((rx, ry, rw, rh), dx, dy, "resize")
                sx0 = max(0.1, float(self.drag.get("base_scale_x", layer.get("scale_x", 1.0) or 1.0)))
                sy0 = max(0.1, float(self.drag.get("base_scale_y", layer.get("scale_y", 1.0) or 1.0)))
                layer["scale_x"] = max(0.1, min(8.0, sx0 * (float(nw) / float(max(1, rw)))))
                layer["scale_y"] = max(0.1, min(8.0, sy0 * (float(nh) / float(max(1, rh)))))
                ddx = int(nx - rx)
                ddy = int(ny - ry)
                layer["x"] = int(self.drag.get("base_x", layer.get("x", 0))) + ddx
                layer["y"] = int(self.drag.get("base_y", layer.get("y", 0))) + ddy
                layer["x1"] = int(self.drag.get("base_x1", layer.get("x1", layer["x"]))) + ddx
                layer["y1"] = int(self.drag.get("base_y1", layer.get("y1", layer["y"]))) + ddy
            else:
                layer["x"] = int(layer.get("x", 0)) + dx
                layer["y"] = int(layer.get("y", 0)) + dy
                layer["x1"] = int(layer.get("x1", layer["x"])) + dx
                layer["y1"] = int(layer.get("y1", layer["y"])) + dy
                self.drag["start_ix"] = int(ix)
                self.drag["start_iy"] = int(iy)
            self._load_layer_controls()
        elif mode == "media":
            layer, idx = self._selected_media_layer()
            if layer is None or idx < 0:
                return
            if self.drag.get("kind") in ("resize", "resize_handle"):
                rx, ry, rw, rh = [int(v) for v in self.drag.get("rect", (0, 0, 1, 1))]
                if self.drag.get("kind") == "resize_handle":
                    nx, ny, nw, nh = self._drag_rect((rx, ry, rw, rh), dx, dy, "resize_handle", self.drag.get("handle"))
                else:
                    nx, ny, nw, nh = self._drag_rect((rx, ry, rw, rh), dx, dy, "resize")
                sx0 = max(0.05, float(self.drag.get("base_scale_x", layer.get("scale_x", 1.0) or 1.0)))
                sy0 = max(0.05, float(self.drag.get("base_scale_y", layer.get("scale_y", 1.0) or 1.0)))
                layer["scale_x"] = max(0.05, min(8.0, sx0 * (float(nw) / float(max(1, rw)))))
                layer["scale_y"] = max(0.05, min(8.0, sy0 * (float(nh) / float(max(1, rh)))))
                ddx = int(nx - rx)
                ddy = int(ny - ry)
                layer["x"] = int(self.drag.get("base_x", layer.get("x", 0))) + ddx
                layer["y"] = int(self.drag.get("base_y", layer.get("y", 0))) + ddy
                layer["x1"] = int(self.drag.get("base_x1", layer.get("x1", layer["x"]))) + ddx
                layer["y1"] = int(self.drag.get("base_y1", layer.get("y1", layer["y"]))) + ddy
            else:
                layer["x"] = int(layer.get("x", 0)) + dx
                layer["y"] = int(layer.get("y", 0)) + dy
                layer["x1"] = int(layer.get("x1", layer["x"])) + dx
                layer["y1"] = int(layer.get("y1", layer["y"])) + dy
                self.drag["start_ix"] = int(ix)
                self.drag["start_iy"] = int(iy)
            self._load_media_layer_controls()
        self._schedule_render_preview(0, fast=True)

    def _preview_release(self, _ev):
        if bool(self.photo_mode) and bool(getattr(self, "_photo_paint_stroking", False)):
            self._photo_paint_stroking = False
            self._photo_last_paint_xy = None
            self._commit_photo_paint_state()
            self._schedule_render_preview(10, fast=False)
            return
        self.drag["kind"] = None
        self.drag["handle"] = None
        for k in ("base_scale_x", "base_scale_y", "base_x", "base_y", "base_x1", "base_y1"):
            self.drag.pop(k, None)
        self._preview_pan_drag = False
        self._schedule_render_preview(10, fast=False)

    def _preview_wheel(self, ev):
        try:
            if ev.modifiers() & Qt.ControlModifier:
                old_zoom = float(self._preview_zoom)
                delta = int(ev.angleDelta().y())
                if delta == 0:
                    return
                factor = 1.08 if delta > 0 else (1.0 / 1.08)
                new_zoom = max(0.25, min(8.0, old_zoom * factor))
                if abs(new_zoom - old_zoom) < 1e-4:
                    return
                pos = ev.position()
                ix, iy = self._view_to_img(pos.x(), pos.y())
                self._preview_zoom = float(new_zoom)
                pw = max(10, self.preview.width())
                ph = max(10, self.preview.height())
                fit = min(float(pw) / float(self.src.width), float(ph) / float(self.src.height))
                sc = max(0.02, float(fit * float(self._preview_zoom)))
                dw = max(1, int(round(self.src.width * sc)))
                dh = max(1, int(round(self.src.height * sc)))
                ox = int(round((pw - dw) * 0.5 + float(self._preview_pan_x)))
                oy = int(round((ph - dh) * 0.5 + float(self._preview_pan_y)))
                vx2 = int(round(float(ix) * sc + ox))
                vy2 = int(round(float(iy) * sc + oy))
                self._preview_pan_x += float(pos.x() - vx2)
                self._preview_pan_y += float(pos.y() - vy2)
                self._schedule_render_preview(0, fast=True)
                ev.accept()
                return
        except Exception:
            pass
        try:
            return QLabel.wheelEvent(self.preview, ev)
        except Exception:
            pass

    def _draw_guides(self, img):
        d = ImageDraw.Draw(img, "RGBA")
        self._guide_rects = {}
        mode = str(self._active_interaction_mode() or "off")

        def draw_handles(x, y, w, h, base_col):
            hs = max(3, int(round(max(4.0, min(w, h) * 0.018))))
            pts = [
                (x, y), (x + w, y), (x, y + h), (x + w, y + h),
                (x + w // 2, y), (x + w // 2, y + h), (x, y + h // 2), (x + w, y + h // 2),
            ]
            fill = (base_col[0], base_col[1], base_col[2], 220)
            stroke = (255, 255, 255, 220)
            for px, py in pts:
                d.rectangle((px - hs, py - hs, px + hs, py + hs), fill=fill, outline=stroke, width=1)

        if bool(self.state.get("crop_enabled", False)):
            x, y, w, h = self._clamp_rect(self.state.get("crop_x", 0), self.state.get("crop_y", 0), self.state.get("crop_w", img.width), self.state.get("crop_h", img.height))
            d.rectangle((0, 0, img.width, y), fill=(0, 0, 0, 110))
            d.rectangle((0, y + h, img.width, img.height), fill=(0, 0, 0, 110))
            d.rectangle((0, y, x, y + h), fill=(0, 0, 0, 110))
            d.rectangle((x + w, y, img.width, y + h), fill=(0, 0, 0, 110))
            col = (110, 180, 255) if mode == "crop" else (94, 154, 220)
            d.rectangle((x, y, x + w, y + h), outline=(col[0], col[1], col[2], 240), width=2)
            draw_handles(x, y, w, h, col)
            self._guide_rects["crop"] = (x, y, w, h)
        if bool(self.state.get("mask_enabled", False)):
            x, y, w, h = self._clamp_rect(self.state.get("mask_x", 0), self.state.get("mask_y", 0), self.state.get("mask_w", img.width), self.state.get("mask_h", img.height))
            col = (255, 208, 92) if mode == "mask" else (224, 176, 74)
            d.rectangle((x, y, x + w, y + h), outline=(col[0], col[1], col[2], 230), width=2)
            draw_handles(x, y, w, h, col)
            self._guide_rects["mask"] = (x, y, w, h)
        if bool(self.state.get("mask_use_image", False)) and bool(str(self.state.get("mask_image_path", "") or "").strip()):
            d.text((8, max(2, img.height - 18)), "MASK MEDIA", fill=(255, 220, 140, 220))
        layer, _ = self._selected_layer()
        if layer is not None and bool(str(layer.get("text", "") or "").strip()):
            lx, ly = self.host._layer_t_xy(layer, int(self.time_slider.value()))
            try:
                font = self.host._safe_font(layer.get("font", "Arial"), int(layer.get("size", 36)))
                dummy = Image.new("RGB", (8, 8), (0, 0, 0))
                dd = ImageDraw.Draw(dummy)
                bb = dd.textbbox((0, 0), str(layer.get("text", "")), font=font)
                tw = max(1, bb[2] - bb[0]); th = max(1, bb[3] - bb[1])
                tw = int(tw * max(0.1, min(8.0, float(layer.get("scale_x", 1.0)))))
                th = int(th * max(0.1, min(8.0, float(layer.get("scale_y", 1.0)))))
                d.rectangle((lx, ly, lx + tw, ly + th), outline=(128, 255, 182, 220), width=2)
                draw_handles(lx, ly, tw, th, (128, 255, 182))
                self._guide_rects["text"] = (int(lx), int(ly), int(tw), int(th))
            except Exception:
                pass
        med, _ = self._selected_media_layer()
        if med is not None and bool(str(med.get("path", "") or "").strip()):
            try:
                frame = self.host._load_media_layer_frame(med, int(self.time_slider.value()))
                if frame is not None:
                    sx = max(0.05, min(8.0, float(med.get("scale_x", 1.0) or 1.0)))
                    sy = max(0.05, min(8.0, float(med.get("scale_y", 1.0) or 1.0)))
                    mw = max(1, int(frame.width * sx))
                    mh = max(1, int(frame.height * sy))
                    mx, my = self.host._layer_t_xy(med, int(self.time_slider.value()))
                    d.rectangle((mx, my, mx + mw, my + mh), outline=(255, 196, 112, 220), width=2)
                    draw_handles(mx, my, mw, mh, (255, 196, 112))
                    self._guide_rects["media"] = (int(mx), int(my), int(mw), int(mh))
            except Exception:
                pass
        return img

    def _render_preview_now(self):
        if not self.isVisible():
            self._preview_rendering = False
            self._preview_fast_hint = False
            return
        if self._preview_rendering:
            self._preview_render_pending = True
            return
        self._preview_rendering = True
        try:
            t_ms = int(self.time_slider.value())
            fast_mode = bool(
                self._preview_fast_hint
                or self._timeline_playing
                or bool(self.drag.get("kind"))
                or bool(self._preview_pan_drag)
            )
            now_ts = time.time()
            if fast_mode:
                min_dt = 0.080 if self.isFullScreen() else 0.055
                dt = float(now_ts - float(getattr(self, "_last_fast_render_ts", 0.0)))
                if dt < min_dt:
                    self._schedule_render_preview(int(max(1.0, (min_dt - dt) * 1000.0)), fast=True)
                    return
            try:
                if not self._timeline_playing:
                    self._pull_state_from_widgets()
            except Exception:
                pass
            try:
                if self._timeline_playing:
                    state_for_preview = self.state
                else:
                    state_for_preview = self.result_state(include_photo_blob=False)
            except Exception:
                state_for_preview = self.state
            if bool(self.photo_mode):
                try:
                    sf = dict(state_for_preview)
                    sf["photo_paint_enabled"] = False
                    sf["photo_paint_png_b64"] = ""
                    sf["photo_paint_hash"] = ""
                    state_for_preview = sf
                except Exception:
                    pass
            if fast_mode:
                try:
                    # Fast mode keeps visual correctness; only trims the heaviest node branch work.
                    sf = dict(state_for_preview)
                    if bool(sf.get("nodes_enabled", False)):
                        sf["nodes_enabled"] = False
                    state_for_preview = sf
                except Exception:
                    state_for_preview = self.state
            cache_key = ""
            if not fast_mode:
                try:
                    payload = {
                        "t": int(t_ms),
                        "fast": bool(fast_mode),
                        "state": state_for_preview,
                    }
                    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
                    cache_key = hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()
                except Exception:
                    cache_key = ""
            if cache_key and cache_key == str(getattr(self, "_preview_cache_key", "")) and self._preview_cache_img is not None:
                img = self._preview_cache_img.copy()
            else:
                old = self.host.editor_state
                self.host.editor_state = state_for_preview
                try:
                    src_frame = self._source_frame_for_time(t_ms, fast=fast_mode)
                    img = self.host._apply_editor_state(src_frame.copy(), t_ms=t_ms).convert("RGB")
                except Exception:
                    img = self.src.copy()
                finally:
                    self.host.editor_state = old
                if cache_key:
                    try:
                        self._preview_cache_key = cache_key
                        self._preview_cache_img = img.copy()
                    except Exception:
                        pass
            if bool(self.photo_mode):
                img = self._apply_photo_paint_overlay(img, self.state)
            try:
                img = self._apply_ascii_bridge_preview(img)
            except Exception:
                pass
            if not (fast_mode and self.isFullScreen()):
                img = self._draw_guides(img.convert("RGBA")).convert("RGB")
            pw = max(10, self.preview.width())
            ph = max(10, self.preview.height())
            fit = min(float(pw) / float(img.width), float(ph) / float(img.height))
            scale = max(0.02, float(fit * float(self._preview_zoom)))
            dw = max(1, int(round(img.width * scale)))
            dh = max(1, int(round(img.height * scale)))
            base_ox = (pw - dw) * 0.5
            base_oy = (ph - dh) * 0.5
            if dw <= pw:
                ox = int(round(base_ox))
                self._preview_pan_x = 0.0
            else:
                ox = int(round(base_ox + float(self._preview_pan_x)))
                ox = max(int(pw - dw), min(0, ox))
                self._preview_pan_x = float(ox - base_ox)
            if dh <= ph:
                oy = int(round(base_oy))
                self._preview_pan_y = 0.0
            else:
                oy = int(round(base_oy + float(self._preview_pan_y)))
                oy = max(int(ph - dh), min(0, oy))
                self._preview_pan_y = float(oy - base_oy)
            canvas = Image.new("RGB", (pw, ph), (10, 13, 18))
            resample = Image.Resampling.BILINEAR if (fast_mode or self.isFullScreen()) else Image.Resampling.LANCZOS
            canvas.paste(img.resize((dw, dh), resample), (ox, oy))
            self.preview_meta["ox"] = ox
            self.preview_meta["oy"] = oy
            self.preview_meta["scale"] = scale
            self.preview_meta["dw"] = dw
            self.preview_meta["dh"] = dh
            self.preview.setPixmap(pil_to_qpixmap(canvas))
            gate = 0.2 if self.isFullScreen() else 0.12
            if not fast_mode or (time.time() - float(self._last_preview_render_ts)) > gate:
                self._refresh_timeline_view()
            if bool(getattr(self, "node_preview_chk", None) and self.node_preview_chk.isChecked()):
                self._schedule_node_preview(90 if fast_mode else 30)
            self._last_preview_render_ts = now_ts
            if fast_mode:
                self._last_fast_render_ts = now_ts
        finally:
            self._preview_rendering = False
            self._preview_fast_hint = False
            if self._preview_render_pending:
                self._preview_render_pending = False
                self._schedule_render_preview(12, fast=False)

    def _request_accept(self):
        self._explicit_accept = True
        self.accept()

    def _request_reject(self):
        self._explicit_close = True
        self.reject()

    def accept(self):
        if self.embedded and not bool(self._explicit_accept):
            return
        self._explicit_accept = False
        if bool(self.photo_mode) and bool(getattr(self, "_photo_paint_dirty", False)):
            self._commit_photo_paint_state()
        self._pull_state_from_widgets()
        try:
            self._timeline_timer.stop()
        except Exception:
            pass
        try:
            self._preview_render_timer.stop()
        except Exception:
            pass
        try:
            self._node_preview_timer.stop()
        except Exception:
            pass
        return super().accept()

    def reject(self):
        if self.embedded and not bool(self._explicit_close):
            return
        self._explicit_close = False
        try:
            self._timeline_timer.stop()
        except Exception:
            pass
        try:
            self._preview_render_timer.stop()
        except Exception:
            pass
        try:
            self._node_preview_timer.stop()
        except Exception:
            pass
        return super().reject()
