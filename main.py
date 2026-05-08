"""
SINDBAD OBD PRO — لوحة تشخيص سيارة احترافية
Production-ready Flet application for Android APK.

Connection guide per adapter type:
  Bluetooth ELM327  → Pair in Android Settings → port = /dev/rfcomm0
  Wi-Fi ELM327      → Connect phone to adapter's hotspot → host = 192.168.0.10, port = 35000
  USB ELM327        → Requires rooted Android or desktop → port = /dev/ttyUSB0 or COM3
  Simulation        → No hardware needed — great for demos and UI testing

Build commands:
  flet run main.py                  (desktop dev)
  flet build apk --product "SINDBAD OBD PRO" --org "com.sindbad.obdpro"
"""

from __future__ import annotations

import json
import math
import os
import random
import threading
import time
from datetime import datetime
from typing import Optional

import flet as ft

try:
    import obd
    OBD_AVAILABLE = True
except ImportError:
    OBD_AVAILABLE = False


# ─── Palette ───────────────────────────────────────────────────────────────────

BG          = "#0a0f1a"
CARD_BG     = "#111827"
CARD_BORDER = "#1e2d45"
PRIMARY     = "#3b82f6"
PRIMARY_DIM = "#1d4ed8"
TEXT        = "#f1f5f9"
TEXT_MUTED  = "#64748b"
RED         = "#ef4444"
YELLOW      = "#eab308"
GREEN       = "#22c55e"


# ─── Default settings ─────────────────────────────────────────────────────────

DEFAULT_SETTINGS: dict = {
    "connection_type": "simulation",   # simulation | bluetooth | wifi | usb
    "bt_port":         "",             # /dev/rfcomm0, COM3 …
    "bt_baud":         "38400",        # 9600 | 38400 | 115200
    "wifi_host":       "192.168.0.10",
    "wifi_port":       "35000",
    "usb_port":        "",             # /dev/ttyUSB0, COM3 …
    "usb_baud":        "38400",
    "auto_connect":    False,
}

STORAGE_KEY = "sindbad_obd_settings"


def build_port_string(s: dict) -> str:
    """Convert settings dict to the portstring expected by python-obd."""
    t = s.get("connection_type", "simulation")
    if t == "bluetooth":
        return s.get("bt_port", "").strip()
    if t == "wifi":
        host = s.get("wifi_host", "192.168.0.10").strip()
        port = s.get("wifi_port", "35000").strip()
        return f"{host}:{port}"
    if t == "usb":
        return s.get("usb_port", "").strip()
    return ""


def get_baud(s: dict) -> int:
    t = s.get("connection_type", "simulation")
    key = "bt_baud" if t == "bluetooth" else "usb_baud"
    try:
        return int(s.get(key, 38400))
    except ValueError:
        return 38400


# ─── DTC Rules ────────────────────────────────────────────────────────────────

class DtcRule:
    def __init__(self, code: str, name_ar: str, desc_ar: str, severity: str):
        self.code     = code
        self.name_ar  = name_ar
        self.desc_ar  = desc_ar
        self.severity = severity

    def triggered(self, rpm, temp, throttle, speed, battery) -> bool:
        return False


class _RpmHigh(DtcRule):
    def triggered(self, rpm, temp, throttle, speed, battery): return rpm > 6500

class _TempHigh(DtcRule):
    def triggered(self, rpm, temp, throttle, speed, battery): return temp > 100

class _BattLow(DtcRule):
    def triggered(self, rpm, temp, throttle, speed, battery): return 0 < battery < 12

class _BattHigh(DtcRule):
    def triggered(self, rpm, temp, throttle, speed, battery): return battery > 14.8

class _ThrottleHigh(DtcRule):
    def triggered(self, rpm, temp, throttle, speed, battery): return throttle > 85

class _TempLow(DtcRule):
    def triggered(self, rpm, temp, throttle, speed, battery): return temp < 70 and rpm > 1000


DTC_RULES: list[DtcRule] = [
    _TempHigh    ("P0217", "ارتفاع حرارة المحرك",         "حرارة سائل التبريد تجاوزت 100°C",           "critical"),
    _RpmHigh     ("P0300", "اشتعال عشوائي في الأسطوانات", "RPM تجاوز 6500 — اشتعال غير منتظم",         "critical"),
    _BattLow     ("P0562", "جهد البطارية منخفض",           "الجهد أقل من 12V — تحقق من المولد",          "warning"),
    _BattHigh    ("P0563", "جهد البطارية مرتفع",           "الجهد تجاوز 14.8V — المنظم قد يكون معطلاً", "warning"),
    _ThrottleHigh("P0121", "حساس الثروتل خارج النطاق",    "قراءة الثروتل تجاوزت 85%",                  "warning"),
    _TempLow     ("P0128", "درجة حرارة التشغيل منخفضة",   "المحرك دون درجة التشغيل المثلى",            "info"),
]

SEV_COLOR = {"critical": RED, "warning": YELLOW, "info": PRIMARY}
SEV_LABEL = {"critical": "حرج", "warning": "تحذير", "info": "معلومة"}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def lerp(current: float, target: float, alpha: float) -> float:
    return current + (target - current) * alpha


# ─── SensorCard (circular gauge) ──────────────────────────────────────────────

class SensorCard(ft.UserControl):
    def __init__(self, title: str, unit: str, min_val: float, max_val: float,
                 icon: str = ft.Icons.SPEED, warn_threshold: Optional[float] = None,
                 precision: int = 0, unavailable: bool = False):
        super().__init__()
        self.title           = title
        self.unit            = unit
        self.min_val         = min_val
        self.max_val         = max_val
        self.icon_name       = icon
        self.warn_threshold  = warn_threshold
        self.precision       = precision
        self.unavailable     = unavailable
        self._value          = 0.0

    def build(self):
        self._value_text = ft.Text(
            "—" if self.unavailable else "0",
            size=30, weight=ft.FontWeight.BOLD,
            color=PRIMARY, text_align=ft.TextAlign.CENTER,
        )
        self._unit_text = ft.Text(
            self.unit, size=11, color=TEXT_MUTED,
            text_align=ft.TextAlign.CENTER,
        )
        self._na_badge = ft.Container(
            content=ft.Text("غير متاح", size=9, color=TEXT_MUTED),
            bgcolor="#1e2d45", border_radius=8,
            padding=ft.padding.symmetric(4, 6),
            visible=self.unavailable,
        )
        self._gauge = ft.Canvas(shapes=[], width=120, height=120)
        self._draw_gauge(0)
        return ft.Container(
            content=ft.Column([
                ft.Stack([
                    self._gauge,
                    ft.Container(
                        content=ft.Column([self._value_text, self._unit_text],
                                         alignment=ft.MainAxisAlignment.CENTER,
                                         horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                         spacing=0),
                        alignment=ft.alignment.center,
                        width=120, height=120,
                    ),
                ]),
                ft.Text(self.title, size=12, color=TEXT,
                        text_align=ft.TextAlign.CENTER,
                        weight=ft.FontWeight.W_600),
                self._na_badge,
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
            bgcolor=CARD_BG,
            border=ft.border.all(1, CARD_BORDER),
            border_radius=14, padding=16, expand=True,
        )

    def _draw_gauge(self, pct: float):
        cx, cy, r = 60, 60, 48
        start, sweep = 135, 270
        active_end = start + sweep * pct
        is_warn = (self.warn_threshold is not None
                   and self._value >= self.warn_threshold
                   and not self.unavailable)
        arc_color = RED if is_warn else PRIMARY
        self._gauge.shapes = [
            ft.canvas.Arc(x=cx-r, y=cy-r, width=r*2, height=r*2,
                          start_angle=math.radians(start),
                          sweep_angle=math.radians(sweep),
                          paint=ft.Paint(color="#1e293b",
                                         style=ft.PaintingStyle.STROKE,
                                         stroke_width=8,
                                         stroke_cap=ft.StrokeCap.ROUND)),
            ft.canvas.Arc(x=cx-r, y=cy-r, width=r*2, height=r*2,
                          start_angle=math.radians(start),
                          sweep_angle=math.radians(max(0, active_end - start)),
                          paint=ft.Paint(
                              color=arc_color if not self.unavailable else "#1e293b",
                              style=ft.PaintingStyle.STROKE,
                              stroke_width=8,
                              stroke_cap=ft.StrokeCap.ROUND)),
        ]

    def set_value(self, v: float):
        if self.unavailable:
            return
        self._value = v
        pct   = max(0.0, min(1.0, (v - self.min_val) / (self.max_val - self.min_val)))
        color = RED if (self.warn_threshold and v >= self.warn_threshold) else PRIMARY
        self._value_text.value = f"{v:.{self.precision}f}"
        self._value_text.color = color
        self._draw_gauge(pct)
        self.update()


# ─── LinearCard ───────────────────────────────────────────────────────────────

class LinearCard(ft.UserControl):
    def __init__(self, title: str, unit: str, min_val: float, max_val: float,
                 icon: str = ft.Icons.SPEED, precision: int = 0):
        super().__init__()
        self.title     = title
        self.unit      = unit
        self.min_val   = min_val
        self.max_val   = max_val
        self.icon_name = icon
        self.precision = precision

    def build(self):
        self._val_text = ft.Text(
            f"0 {self.unit}", size=22,
            weight=ft.FontWeight.BOLD, color=PRIMARY,
        )
        self._bar = ft.ProgressBar(value=0, bgcolor="#1e293b", color=PRIMARY,
                                   height=8, border_radius=4)
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(self.icon_name, color=PRIMARY, size=20),
                    self._val_text,
                    ft.Container(expand=True),
                    ft.Text(self.title, size=12, color=TEXT,
                            weight=ft.FontWeight.W_600),
                ]),
                self._bar,
            ], spacing=10),
            bgcolor=CARD_BG,
            border=ft.border.all(1, CARD_BORDER),
            border_radius=14, padding=16,
        )

    def set_value(self, v: float):
        pct = max(0.0, min(1.0, (v - self.min_val) / (self.max_val - self.min_val)))
        self._val_text.value = f"{v:.{self.precision}f} {self.unit}"
        self._bar.value = pct
        self.update()


# ─── RpmHeroCard ──────────────────────────────────────────────────────────────

class RpmHeroCard(ft.UserControl):
    def build(self):
        self._val  = ft.Text("0", size=64, weight=ft.FontWeight.W_900,
                             color=PRIMARY, text_align=ft.TextAlign.CENTER)
        self._bar  = ft.ProgressBar(value=0, bgcolor="#1e293b", color=PRIMARY,
                                    height=10, border_radius=5)
        return ft.Container(
            content=ft.Column([
                ft.Row([ft.Icon(ft.Icons.SPEED, color=PRIMARY, size=32),
                        ft.Text("سرعة المحرك", size=18,
                                weight=ft.FontWeight.BOLD, color=TEXT)],
                       alignment=ft.MainAxisAlignment.END, spacing=10),
                ft.Container(content=ft.Column([
                    self._val,
                    ft.Text("RPM", size=14, color=TEXT_MUTED,
                            text_align=ft.TextAlign.CENTER,
                            weight=ft.FontWeight.W_600),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                    padding=ft.padding.symmetric(20, 0)),
                self._bar,
            ], spacing=8),
            bgcolor=CARD_BG,
            border=ft.border.all(1, PRIMARY_DIM),
            border_radius=16, padding=20,
            shadow=ft.BoxShadow(blur_radius=20, color=f"{PRIMARY}40"),
        )

    def set_value(self, v: float):
        self._val.value = f"{int(v):,}"
        self._bar.value = max(0.0, min(1.0, v / 8000))
        self.update()


# ─── DtcPanel ─────────────────────────────────────────────────────────────────

class DtcPanel(ft.UserControl):
    def __init__(self):
        super().__init__()
        self._active: dict[str, DtcRule] = {}
        self._dismissed: set[str] = set()

    def build(self):
        self._list_col = ft.Column(spacing=8)
        self._no_codes = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=GREEN, size=28),
                ft.Text("لا توجد أكواد أعطال نشطة", size=14, color=GREEN,
                        weight=ft.FontWeight.W_600),
            ], spacing=12, alignment=ft.MainAxisAlignment.CENTER),
            bgcolor="#052e16", border=ft.border.all(1, "#166534"),
            border_radius=12, padding=16, visible=False,
        )
        self._disconnected = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.SHIELD_OUTLINED, color=TEXT_MUTED, size=28),
                ft.Text("قم بتوصيل الجهاز لفحص الأعطال",
                        size=13, color=TEXT_MUTED),
            ], spacing=12, alignment=ft.MainAxisAlignment.CENTER),
            bgcolor=CARD_BG, border=ft.border.all(1, CARD_BORDER),
            border_radius=12, padding=16,
        )
        return ft.Column([
            ft.Row([ft.Icon(ft.Icons.SHIELD_OUTLINED, color=TEXT_MUTED, size=20),
                    ft.Text("أكواد الأعطال (DTC)", size=16,
                            weight=ft.FontWeight.BOLD, color=TEXT)],
                   spacing=10),
            self._disconnected, self._no_codes, self._list_col,
        ], spacing=10)

    def set_connected(self, c: bool):
        self._disconnected.visible = not c
        if not c:
            self._list_col.controls.clear()
            self._active.clear()
            self._dismissed.clear()
        self.update()

    def update_codes(self, active: list[DtcRule]):
        self._active = {r.code: r for r in active}
        visible = [r for r in active if r.code not in self._dismissed]
        self._list_col.controls = [self._make_card(r) for r in visible]
        self._no_codes.visible = not self._disconnected.visible and not visible
        self.update()

    def _make_card(self, rule: DtcRule) -> ft.Container:
        color = SEV_COLOR.get(rule.severity, PRIMARY)

        def dismiss(_e, code=rule.code):
            self._dismissed.add(code)
            self.update_codes(list(self._active.values()))

        return ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=color, size=18),
                ft.Column([
                    ft.Row([
                        ft.Text(rule.code, size=13, weight=ft.FontWeight.BOLD,
                                color=TEXT, font_family="monospace"),
                        ft.Container(content=ft.Text(SEV_LABEL.get(rule.severity,""), size=9, color=color),
                                     border=ft.border.all(1, color),
                                     border_radius=8, padding=ft.padding.symmetric(2, 6)),
                    ], spacing=6),
                    ft.Text(rule.name_ar, size=12, color=TEXT, weight=ft.FontWeight.W_600),
                    ft.Text(rule.desc_ar, size=10, color=TEXT_MUTED),
                ], spacing=3, expand=True),
                ft.IconButton(icon=ft.Icons.CLOSE, icon_color=TEXT_MUTED,
                              icon_size=16, on_click=dismiss),
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.START),
            bgcolor=f"{color}0d", border=ft.border.all(1, f"{color}40"),
            border_radius=12, padding=12,
        )


# ─── LogPanel ─────────────────────────────────────────────────────────────────

class LogPanel(ft.UserControl):
    def __init__(self):
        super().__init__()
        self._session_start: Optional[datetime] = None
        self._dtc_count  = 0
        self._crit_count = 0

    def build(self):
        self._dur_text  = ft.Text("—",  size=18, weight=ft.FontWeight.BOLD, color=TEXT)
        self._dtc_text  = ft.Text("0",  size=18, weight=ft.FontWeight.BOLD, color=TEXT)
        self._crit_text = ft.Text("0",  size=18, weight=ft.FontWeight.BOLD, color=TEXT)
        self._log_col   = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, height=240)
        self._empty     = ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.HISTORY_OUTLINED, color=TEXT_MUTED, size=36),
                ft.Text("قم بتوصيل الجهاز لبدء التسجيل",
                        size=12, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
            alignment=ft.alignment.center, height=180,
        )

        def clear(_e):
            self._log_col.controls.clear()
            self._dtc_count = self._crit_count = 0
            self._dtc_text.value = self._crit_text.value = "0"
            self._crit_text.color = TEXT
            self._empty.visible = True
            self.update()

        return ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.RECEIPT_LONG_OUTLINED, color=TEXT_MUTED, size=20),
                ft.Text("سجل البيانات الحي", size=16,
                        weight=ft.FontWeight.BOLD, color=TEXT),
                ft.Container(expand=True),
                ft.TextButton("مسح السجل", on_click=clear,
                              style=ft.ButtonStyle(color=TEXT_MUTED)),
            ], spacing=10),
            ft.Row([
                self._stat("مدة الجلسة",  self._dur_text),
                self._stat("أحداث DTC",   self._dtc_text),
                self._stat("أعطال حرجة", self._crit_text),
            ], spacing=8),
            ft.Container(
                content=ft.Column([self._empty, self._log_col], spacing=0),
                bgcolor=CARD_BG, border=ft.border.all(1, CARD_BORDER),
                border_radius=14, padding=8,
            ),
        ], spacing=10)

    def _stat(self, label: str, ctrl: ft.Control) -> ft.Container:
        return ft.Container(
            content=ft.Column([ctrl, ft.Text(label, size=10, color=TEXT_MUTED,
                                              text_align=ft.TextAlign.CENTER)],
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2),
            bgcolor=CARD_BG, border=ft.border.all(1, CARD_BORDER),
            border_radius=12, padding=ft.padding.symmetric(10, 16), expand=True,
        )

    def set_session_start(self, dt: Optional[datetime]):
        self._session_start = dt
        if dt is None:
            self._dur_text.value = "—"
        self.update()

    def tick(self):
        if self._session_start:
            s = int((datetime.now() - self._session_start).total_seconds())
            m, s = divmod(s, 60); h, m = divmod(m, 60)
            self._dur_text.value = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
            self.update()

    def push(self, event_type: str, code: Optional[str] = None,
             name_ar: Optional[str] = None, severity: Optional[str] = None):
        COLOR  = {"connected": PRIMARY, "disconnected": TEXT_MUTED,
                  "dtc_trigger": RED,   "dtc_clear": GREEN}
        ICON   = {"connected": ft.Icons.WIFI, "disconnected": ft.Icons.WIFI_OFF,
                  "dtc_trigger": ft.Icons.ARROW_UPWARD,
                  "dtc_clear": ft.Icons.ARROW_DOWNWARD}
        LABEL  = {"connected": "اتصال", "disconnected": "قطع اتصال",
                  "dtc_trigger": "ظهر", "dtc_clear": "اختفى"}

        if event_type == "dtc_trigger":
            self._dtc_count += 1
            self._dtc_text.value = str(self._dtc_count)
            if severity == "critical":
                self._crit_count += 1
                self._crit_text.value = str(self._crit_count)
                self._crit_text.color = RED

        c = COLOR.get(event_type, TEXT_MUTED)
        ts = datetime.now().strftime("%H:%M:%S")
        right: list[ft.Control] = ([
            ft.Text(code or "", size=12, weight=ft.FontWeight.BOLD,
                    color=TEXT, font_family="monospace"),
            ft.Text(LABEL.get(event_type, ""), size=11, color=c),
            ft.Text(name_ar or "", size=10, color=TEXT_MUTED),
        ] if code else [ft.Text(LABEL.get(event_type, event_type),
                                size=12, color=c, weight=ft.FontWeight.W_600)])

        self._log_col.controls.insert(0, ft.Container(
            content=ft.Row([
                ft.Icon(ICON.get(event_type, ft.Icons.CIRCLE), color=c, size=14),
                ft.Text(ts, size=10, color=TEXT_MUTED,
                        font_family="monospace", width=70),
                ft.Row(right, spacing=6, expand=True),
            ], spacing=8),
            padding=ft.padding.symmetric(8, 4),
        ))
        self._log_col.controls = self._log_col.controls[:200]
        self._empty.visible = False
        self.update()


# ─── SettingsPage ─────────────────────────────────────────────────────────────

class SettingsPage(ft.UserControl):
    """
    Full settings screen:
      • Connection type selector (Simulation / Bluetooth / Wi-Fi / USB)
      • Dynamic connection detail fields per type
      • Baud rate selector for serial connections
      • Auto-connect on startup toggle
      • Save / Test Connection buttons
    """

    def __init__(self, settings: dict, on_save, on_test):
        super().__init__()
        self._s       = dict(settings)   # local copy — written back on Save
        self.on_save  = on_save
        self.on_test  = on_test

    # ── build ──────────────────────────────────────────────────────────────────

    def build(self):
        # ── Connection type radio group ────────────────────────────────────────
        TYPE_OPTS = [
            ("simulation", "محاكاة",   ft.Icons.MONITOR,              "لا يلزم جهاز — مثالي للاختبار"),
            ("bluetooth",  "بلوتوث",  ft.Icons.BLUETOOTH,             "ELM327 بلوتوث — قرن الجهاز أولاً"),
            ("wifi",       "Wi-Fi",    ft.Icons.WIFI,                  "ELM327 واي فاي — اتصل بشبكة المحول"),
            ("usb",        "USB",      ft.Icons.USB,                   "كابل USB — يتطلب روت أو الكمبيوتر"),
        ]

        self._type_buttons: dict[str, ft.ElevatedButton] = {}

        def make_type_btn(key, label, icon, hint):
            is_active = self._s["connection_type"] == key
            btn = ft.ElevatedButton(
                label,
                icon=icon,
                bgcolor=PRIMARY if is_active else CARD_BG,
                color="white" if is_active else TEXT_MUTED,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                height=44,
                data=key,
                on_click=self._on_type_change,
                tooltip=hint,
            )
            self._type_buttons[key] = btn
            return btn

        type_row = ft.Column([
            ft.Text("نوع الاتصال", size=13, color=TEXT_MUTED,
                    weight=ft.FontWeight.W_600),
            ft.ResponsiveRow([
                ft.Column([make_type_btn(*o)], col={"xs": 6, "md": 3})
                for o in TYPE_OPTS
            ], spacing=8, run_spacing=8),
        ], spacing=10)

        # ── Bluetooth fields ───────────────────────────────────────────────────
        self._bt_port = ft.TextField(
            label="منفذ البلوتوث",
            hint_text="/dev/rfcomm0  أو  COM3",
            value=self._s["bt_port"],
            bgcolor=BG, color=TEXT,
            border_color=CARD_BORDER, focused_border_color=PRIMARY,
            label_style=ft.TextStyle(color=TEXT_MUTED),
        )
        self._bt_baud = ft.Dropdown(
            label="سرعة الاتصال (Baud)",
            value=self._s["bt_baud"],
            options=[ft.dropdown.Option("9600"), ft.dropdown.Option("38400"),
                     ft.dropdown.Option("115200")],
            bgcolor=BG, color=TEXT,
            border_color=CARD_BORDER, focused_border_color=PRIMARY,
        )
        self._bt_hint = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.INFO_OUTLINE, color=PRIMARY, size=16),
                ft.Text(
                    "اذهب إلى إعدادات Android ← البلوتوث ← قرن الجهاز أولاً.\n"
                    "بعد الاقتران يظهر تلقائياً كـ /dev/rfcomm0",
                    size=11, color=TEXT_MUTED,
                ),
            ], spacing=8),
            bgcolor=f"{PRIMARY}0d", border=ft.border.all(1, f"{PRIMARY}25"),
            border_radius=10, padding=12,
        )
        self._bt_section = ft.Column(
            [self._bt_hint, self._bt_port, self._bt_baud], spacing=10,
            visible=self._s["connection_type"] == "bluetooth",
        )

        # ── Wi-Fi fields ───────────────────────────────────────────────────────
        self._wifi_host = ft.TextField(
            label="عنوان IP للمحول",
            hint_text="192.168.0.10",
            value=self._s["wifi_host"],
            bgcolor=BG, color=TEXT,
            border_color=CARD_BORDER, focused_border_color=PRIMARY,
            label_style=ft.TextStyle(color=TEXT_MUTED),
        )
        self._wifi_port = ft.TextField(
            label="رقم المنفذ (Port)",
            hint_text="35000",
            value=self._s["wifi_port"],
            bgcolor=BG, color=TEXT,
            border_color=CARD_BORDER, focused_border_color=PRIMARY,
            label_style=ft.TextStyle(color=TEXT_MUTED),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self._wifi_hint = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.INFO_OUTLINE, color=PRIMARY, size=16),
                ft.Text(
                    "وصّل الهاتف بشبكة Wi-Fi الخاصة بمحول ELM327.\n"
                    "عادةً IP: 192.168.0.10 ومنفذ: 35000",
                    size=11, color=TEXT_MUTED,
                ),
            ], spacing=8),
            bgcolor=f"{PRIMARY}0d", border=ft.border.all(1, f"{PRIMARY}25"),
            border_radius=10, padding=12,
        )
        self._wifi_section = ft.Column(
            [self._wifi_hint, self._wifi_host, self._wifi_port], spacing=10,
            visible=self._s["connection_type"] == "wifi",
        )

        # ── USB fields ─────────────────────────────────────────────────────────
        self._usb_port = ft.TextField(
            label="منفذ USB",
            hint_text="/dev/ttyUSB0  أو  COM3",
            value=self._s["usb_port"],
            bgcolor=BG, color=TEXT,
            border_color=CARD_BORDER, focused_border_color=PRIMARY,
            label_style=ft.TextStyle(color=TEXT_MUTED),
        )
        self._usb_baud = ft.Dropdown(
            label="سرعة الاتصال (Baud)",
            value=self._s["usb_baud"],
            options=[ft.dropdown.Option("9600"), ft.dropdown.Option("38400"),
                     ft.dropdown.Option("115200")],
            bgcolor=BG, color=TEXT,
            border_color=CARD_BORDER, focused_border_color=PRIMARY,
        )
        self._usb_hint = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=YELLOW, size=16),
                ft.Text(
                    "USB المباشر يتطلب روت على Android.\n"
                    "على الكمبيوتر: /dev/ttyUSB0 (Linux) أو COM3 (Windows).",
                    size=11, color=TEXT_MUTED,
                ),
            ], spacing=8),
            bgcolor=f"{YELLOW}0d", border=ft.border.all(1, f"{YELLOW}25"),
            border_radius=10, padding=12,
        )
        self._usb_section = ft.Column(
            [self._usb_hint, self._usb_port, self._usb_baud], spacing=10,
            visible=self._s["connection_type"] == "usb",
        )

        # ── Auto-connect toggle ────────────────────────────────────────────────
        self._auto_sw = ft.Switch(
            label="اتصال تلقائي عند بدء التشغيل",
            value=self._s["auto_connect"],
            active_color=PRIMARY,
            label_style=ft.TextStyle(color=TEXT, size=13),
            on_change=lambda e: self._set("auto_connect", e.control.value),
        )

        # ── Save / Test buttons ────────────────────────────────────────────────
        self._status_text = ft.Text("", size=12, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER)

        save_btn = ft.ElevatedButton(
            "حفظ الإعدادات",
            icon=ft.Icons.SAVE_OUTLINED,
            bgcolor=PRIMARY, color="white",
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
            on_click=self._save,
            height=48, expand=True,
        )
        test_btn = ft.OutlinedButton(
            "اختبار الاتصال",
            icon=ft.Icons.CABLE,
            style=ft.ButtonStyle(
                color=TEXT_MUTED,
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            on_click=self._test,
            height=48, expand=True,
        )

        # ── Layout ─────────────────────────────────────────────────────────────
        def card(title: str, icon: str, content: ft.Control) -> ft.Container:
            return ft.Container(
                content=ft.Column([
                    ft.Row([ft.Icon(icon, color=PRIMARY, size=18),
                            ft.Text(title, size=14, weight=ft.FontWeight.BOLD,
                                    color=TEXT)], spacing=10),
                    ft.Divider(height=1, color=CARD_BORDER),
                    content,
                ], spacing=14),
                bgcolor=CARD_BG,
                border=ft.border.all(1, CARD_BORDER),
                border_radius=16, padding=18,
            )

        return ft.Column([
            ft.Text("الإعدادات", size=22, weight=ft.FontWeight.BOLD,
                    color=TEXT, text_align=ft.TextAlign.RIGHT),
            card("نوع الاتصال", ft.Icons.SETTINGS_INPUT_COMPONENT_OUTLINED, type_row),
            card("إعدادات الاتصال", ft.Icons.CABLE, ft.Column([
                self._bt_section,
                self._wifi_section,
                self._usb_section,
            ], spacing=0)),
            card("السلوك", ft.Icons.TUNE, self._auto_sw),
            ft.Row([save_btn, test_btn], spacing=12),
            self._status_text,
            # ── About ──────────────────────────────────────────────────────────
            ft.Container(
                content=ft.Column([
                    ft.Text("SINDBAD OBD PRO", size=14,
                            weight=ft.FontWeight.BOLD, color=TEXT,
                            text_align=ft.TextAlign.CENTER),
                    ft.Text("v1.0 — Python + Flet + python-obd",
                            size=11, color=TEXT_MUTED,
                            text_align=ft.TextAlign.CENTER),
                    ft.Text("مدعوم: ELM327 v1.5+ (بلوتوث / واي فاي / USB)",
                            size=11, color=TEXT_MUTED,
                            text_align=ft.TextAlign.CENTER),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                bgcolor=CARD_BG, border=ft.border.all(1, CARD_BORDER),
                border_radius=14, padding=16,
            ),
        ], spacing=16, scroll=ft.ScrollMode.AUTO)

    # ── Event handlers ─────────────────────────────────────────────────────────

    def _set(self, key: str, value):
        self._s[key] = value

    def _on_type_change(self, e: ft.ControlEvent):
        t = e.control.data
        self._s["connection_type"] = t
        for k, btn in self._type_buttons.items():
            btn.bgcolor = PRIMARY if k == t else CARD_BG
            btn.color   = "white" if k == t else TEXT_MUTED
        self._bt_section.visible   = t == "bluetooth"
        self._wifi_section.visible = t == "wifi"
        self._usb_section.visible  = t == "usb"
        self._status_text.value = ""
        self.update()

    def _collect(self):
        """Read all field values back into self._s."""
        self._s["bt_port"]   = self._bt_port.value.strip()
        self._s["bt_baud"]   = self._bt_baud.value or "38400"
        self._s["wifi_host"] = self._wifi_host.value.strip()
        self._s["wifi_port"] = self._wifi_port.value.strip()
        self._s["usb_port"]  = self._usb_port.value.strip()
        self._s["usb_baud"]  = self._usb_baud.value or "38400"

    def _save(self, _e):
        self._collect()
        self.on_save(dict(self._s))
        self._status_text.value = "✓ تم حفظ الإعدادات بنجاح"
        self._status_text.color = GREEN
        self.update()

    def _test(self, _e):
        self._collect()
        self._status_text.value = "جارٍ اختبار الاتصال…"
        self._status_text.color = TEXT_MUTED
        self.update()
        self.on_test(dict(self._s), self._on_test_result)

    def _on_test_result(self, success: bool, message: str):
        self._status_text.value = message
        self._status_text.color = GREEN if success else RED
        self.update()

    def refresh(self, settings: dict):
        """Called by parent when external settings change."""
        self._s = dict(settings)


# ─── OBD2Worker ───────────────────────────────────────────────────────────────

class OBD2Worker:
    """Reads sensor data in a background daemon thread."""

    def __init__(self, on_data, on_dtcs, on_disconnect):
        self._on_data       = on_data
        self._on_dtcs       = on_dtcs
        self._on_disconnect = on_disconnect
        self._thread: Optional[threading.Thread] = None
        self._running       = False
        self._conn          = None
        self._sim = {"rpm": 850, "temp": 88, "throttle": 5,
                     "speed": 0, "battery": 13.8}

    def start(self, settings: dict):
        self._settings = settings
        self._running  = True
        self._thread   = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._conn:
            try: self._conn.close()
            except Exception: pass
            self._conn = None

    def test_connection(self, settings: dict, callback):
        """One-shot test in a daemon thread."""
        def _test():
            if settings["connection_type"] == "simulation":
                callback(True, "✓ وضع المحاكاة يعمل دائماً")
                return
            if not OBD_AVAILABLE:
                callback(False, "✗ مكتبة obd غير مثبتة")
                return
            try:
                port = build_port_string(settings)
                conn = obd.OBD(portstr=port or None, fast=False, timeout=5)
                if conn.is_connected():
                    callback(True, f"✓ اتصال ناجح: {conn.port_name()}")
                else:
                    callback(False, "✗ تعذّر الاتصال — تحقق من الإعدادات")
                conn.close()
            except Exception as exc:
                callback(False, f"✗ خطأ: {exc}")
        threading.Thread(target=_test, daemon=True).start()

    def _run(self):
        if self._settings.get("connection_type") == "simulation":
            self._run_simulation()
        else:
            self._run_device()

    def _run_simulation(self):
        targets = dict(self._sim)
        while self._running:
            targets.update({"rpm": random.uniform(600, 7200),
                            "temp": random.uniform(75, 108),
                            "throttle": random.uniform(0, 90),
                            "speed": random.uniform(0, 180),
                            "battery": random.uniform(11.5, 15.0)})
            for _ in range(8):
                if not self._running: break
                for k in self._sim:
                    self._sim[k] = lerp(self._sim[k], targets[k], 0.15)
                self._on_data(dict(self._sim))
                time.sleep(0.2)

    def _run_device(self):
        if not OBD_AVAILABLE:
            self._on_disconnect("مكتبة obd غير متوفرة — شغّل: pip install obd")
            return
        try:
            port = build_port_string(self._settings)
            self._conn = obd.OBD(portstr=port or None, fast=False, timeout=5)
            if not self._conn.is_connected():
                self._on_disconnect("تعذّر الاتصال — تحقق من توصيل الجهاز وتشغيل المحرك")
                return
            dtc_resp = self._conn.query(obd.commands.GET_DTC)
            if not dtc_resp.is_null():
                self._on_dtcs([e[0] for e in (dtc_resp.value or [])])
            CMDS = {"rpm": obd.commands.RPM, "speed": obd.commands.SPEED,
                    "temp": obd.commands.COOLANT_TEMP,
                    "throttle": obd.commands.THROTTLE_POS}
            while self._running and self._conn.is_connected():
                data: dict = {}
                for k, cmd in CMDS.items():
                    try:
                        r = self._conn.query(cmd)
                        if not r.is_null() and r.value is not None:
                            data[k] = float(r.value.magnitude)
                    except Exception:
                        pass
                if data:
                    self._on_data(data)
                time.sleep(0.5)
            if self._running:
                self._on_disconnect("انقطع الاتصال بالجهاز")
        except Exception as exc:
            self._on_disconnect(f"خطأ في الاتصال: {exc}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(page: ft.Page):
    page.title       = "SINDBAD OBD PRO"
    page.bgcolor     = BG
    page.padding     = 0
    page.rtl         = True
    page.theme_mode  = ft.ThemeMode.DARK
    page.window_min_width = 360

    # ── Load / save settings via Flet client storage (persists on device) ─────
    def load_settings() -> dict:
        s = dict(DEFAULT_SETTINGS)
        for k, v in DEFAULT_SETTINGS.items():
            stored = page.client_storage.get(f"{STORAGE_KEY}.{k}")
            if stored is not None:
                s[k] = stored
        return s

    def save_settings(s: dict):
        nonlocal current_settings
        current_settings = s
        for k, v in s.items():
            page.client_storage.set(f"{STORAGE_KEY}.{k}", v)
        # Sync dashboard mode toggle text
        _update_conn_mode_ui()

    current_settings: dict = load_settings()

    # ── State ──────────────────────────────────────────────────────────────────
    connected    = False
    prev_codes: set[str] = set()

    worker = OBD2Worker(
        on_data=lambda d: _on_data(d),
        on_dtcs=lambda c: _on_dtcs(c),
        on_disconnect=lambda m: _on_disconnect(m),
    )

    # ── Sensor widgets ─────────────────────────────────────────────────────────
    rpm_card = RpmHeroCard()
    spd_card = SensorCard("سرعة السيارة", "km/h", 0, 200,
                          icon=ft.Icons.DIRECTIONS_CAR_OUTLINED)
    tmp_card = SensorCard("حرارة المحرك", "°C", 60, 120,
                          icon=ft.Icons.THERMOSTAT_OUTLINED, warn_threshold=95)
    thr_card = LinearCard("بوابة الثروتل", "%", 0, 100, icon=ft.Icons.SPEED)
    oil_card = SensorCard("ضغط الزيت", "bar", 0, 6,
                          icon=ft.Icons.OIL_BARREL_OUTLINED,
                          unavailable=(current_settings["connection_type"] != "simulation"))
    bat_card = LinearCard("جهد البطارية", "V", 10, 16,
                          icon=ft.Icons.BATTERY_CHARGING_FULL_OUTLINED, precision=1)
    dtc_panel = DtcPanel()
    log_panel = LogPanel()

    # ── Header widgets ─────────────────────────────────────────────────────────
    status_dot  = ft.Container(width=10, height=10, border_radius=5, bgcolor=RED)
    status_txt  = ft.Text("غير متصل", size=12, color=TEXT_MUTED)
    mode_badge  = ft.Container(
        content=ft.Text("محاكاة", size=10, color=TEXT_MUTED),
        border=ft.border.all(1, CARD_BORDER), border_radius=8,
        padding=ft.padding.symmetric(2, 8),
    )
    connect_btn = ft.ElevatedButton(
        "اتصال",
        icon=ft.Icons.POWER_SETTINGS_NEW_ROUNDED,
        bgcolor=PRIMARY, color="white",
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
        on_click=lambda e: (on_connect_btn(e)),
        height=44,
    )

    stored_dtc_col = ft.Column(spacing=8, visible=False)

    # ── Callbacks ──────────────────────────────────────────────────────────────

    def _update_conn_mode_ui():
        labels = {"simulation": "محاكاة", "bluetooth": "بلوتوث",
                  "wifi": "Wi-Fi", "usb": "USB"}
        mode_badge.content.value = labels.get(current_settings["connection_type"], "")
        oil_card.unavailable = current_settings["connection_type"] != "simulation"
        try:
            mode_badge.update()
        except Exception:
            pass

    def _on_data(data: dict):
        nonlocal prev_codes
        if "rpm"      in data: rpm_card.set_value(data["rpm"])
        if "speed"    in data: spd_card.set_value(data["speed"])
        if "temp"     in data: tmp_card.set_value(data["temp"])
        if "throttle" in data: thr_card.set_value(data["throttle"])
        if "battery"  in data: bat_card.set_value(data["battery"])

        v = {k: data.get(k, 0) for k in ("rpm","temp","throttle","speed","battery")}
        active = [r for r in DTC_RULES
                  if r.triggered(v["rpm"],v["temp"],v["throttle"],v["speed"],v["battery"])]
        dtc_panel.update_codes(active)
        cur = {r.code for r in active}
        for r in active:
            if r.code not in prev_codes:
                log_panel.push("dtc_trigger", r.code, r.name_ar, r.severity)
        for code in prev_codes - cur:
            rule = next((r for r in DTC_RULES if r.code == code), None)
            log_panel.push("dtc_clear", code,
                           rule.name_ar if rule else None,
                           rule.severity if rule else None)
        prev_codes = cur

    def _on_dtcs(codes: list[str]):
        stored_dtc_col.visible = True
        stored_dtc_col.controls = ([
            ft.Row([ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=YELLOW, size=16),
                    ft.Text(c, size=13, weight=ft.FontWeight.BOLD,
                            color=TEXT, font_family="monospace")], spacing=8)
            for c in codes
        ] or [ft.Text("لا توجد أكواد مخزنة في ECU", size=12, color=GREEN)])
        stored_dtc_col.update()

    def _on_disconnect(message: str = ""):
        nonlocal connected
        connected = False
        worker.stop()
        status_dot.bgcolor     = RED
        status_txt.value       = message or "انقطع الاتصال"
        connect_btn.text       = "اتصال"
        connect_btn.icon       = ft.Icons.POWER_SETTINGS_NEW_ROUNDED
        connect_btn.bgcolor    = PRIMARY
        stored_dtc_col.visible = False
        dtc_panel.set_connected(False)
        log_panel.set_session_start(None)
        log_panel.push("disconnected")
        page.update()

    def _do_connect():
        nonlocal connected, prev_codes
        connected  = True
        prev_codes = set()
        status_dot.bgcolor  = GREEN
        status_txt.value    = "متصل بنجاح (OBD2)"
        connect_btn.text    = "قطع الاتصال"
        connect_btn.icon    = ft.Icons.STOP_CIRCLE_OUTLINED
        connect_btn.bgcolor = RED
        dtc_panel.set_connected(True)
        log_panel.set_session_start(datetime.now())
        log_panel.push("connected")
        _update_conn_mode_ui()
        page.update()
        worker.start(settings=current_settings)

    def on_connect_btn(_e):
        if connected:
            _on_disconnect()
        else:
            _do_connect()

    def on_settings_save(s: dict):
        save_settings(s)
        page.update()

    def on_settings_test(s: dict, callback):
        worker.test_connection(s, callback)

    # ── Session timer ──────────────────────────────────────────────────────────
    def _tick():
        while True:
            time.sleep(1)
            try: log_panel.tick()
            except Exception: pass
    threading.Thread(target=_tick, daemon=True).start()

    # ── Auto-connect on startup ────────────────────────────────────────────────
    if current_settings.get("auto_connect") and current_settings["connection_type"] != "simulation":
        threading.Timer(1.5, _do_connect).start()

    # ── Pages ──────────────────────────────────────────────────────────────────

    _update_conn_mode_ui()

    def _make_header() -> ft.Container:
        return ft.Container(
            content=ft.Row([
                ft.Row([
                    ft.Container(
                        content=ft.Icon(ft.Icons.MONITOR_HEART, color=PRIMARY, size=28),
                        bgcolor=f"{PRIMARY}1a",
                        border=ft.border.all(1, f"{PRIMARY}33"),
                        border_radius=12, padding=10,
                        shadow=ft.BoxShadow(blur_radius=16, color=f"{PRIMARY}33"),
                    ),
                    ft.Column([
                        ft.Text("SINDBAD OBD PRO", size=18,
                                weight=ft.FontWeight.BOLD, color="white"),
                        ft.Row([status_dot, status_txt, mode_badge], spacing=8),
                    ], spacing=4),
                ], spacing=12),
                ft.Container(expand=True),
                connect_btn,
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.only(left=16, right=16, top=16, bottom=12),
            border=ft.border.only(bottom=ft.BorderSide(1, CARD_BORDER)),
        )

    dashboard_page = ft.Column([
        ft.ResponsiveRow([
            ft.Column([rpm_card], col={"xs": 12, "md": 8}),
            ft.Column([spd_card], col={"xs": 12, "md": 4}),
            ft.Column([tmp_card], col={"xs": 12, "md": 4}),
            ft.Column([thr_card], col={"xs": 12, "md": 8}),
            ft.Column([oil_card], col={"xs": 12, "md": 4}),
            ft.Column([bat_card], col={"xs": 12, "md": 8}),
        ], spacing=12, run_spacing=12),
        ft.Container(content=dtc_panel,
                     bgcolor=CARD_BG, border=ft.border.all(1, CARD_BORDER),
                     border_radius=14, padding=16),
        ft.Container(
            content=ft.Column([
                ft.Row([ft.Icon(ft.Icons.ELECTRICAL_SERVICES, color=TEXT_MUTED, size=18),
                        ft.Text("أكواد ECU المخزنة", size=15,
                                weight=ft.FontWeight.BOLD, color=TEXT),
                        ft.Container(content=ft.Text("جهاز حقيقي", size=9, color=TEXT_MUTED),
                                     border=ft.border.all(1, CARD_BORDER),
                                     border_radius=8,
                                     padding=ft.padding.symmetric(2, 6))],
                       spacing=10),
                stored_dtc_col,
            ], spacing=10),
            bgcolor=CARD_BG, border=ft.border.all(1, CARD_BORDER),
            border_radius=14, padding=16,
        ),
        ft.Container(content=log_panel,
                     bgcolor=CARD_BG, border=ft.border.all(1, CARD_BORDER),
                     border_radius=14, padding=16),
    ], spacing=16, scroll=ft.ScrollMode.AUTO)

    settings_ctrl = SettingsPage(
        settings=current_settings,
        on_save=on_settings_save,
        on_test=on_settings_test,
    )

    # ── Navigation ─────────────────────────────────────────────────────────────
    body = ft.Container(content=dashboard_page, padding=16, expand=True)

    def on_nav(e: ft.ControlEvent):
        idx = e.control.selected_index
        body.content = dashboard_page if idx == 0 else settings_ctrl
        page.update()

    nav_bar = ft.NavigationBar(
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.DASHBOARD_OUTLINED,
                                        selected_icon=ft.Icons.DASHBOARD,
                                        label="لوحة التحكم"),
            ft.NavigationBarDestination(icon=ft.Icons.SETTINGS_OUTLINED,
                                        selected_icon=ft.Icons.SETTINGS,
                                        label="الإعدادات"),
        ],
        bgcolor=CARD_BG,
        selected_index=0,
        on_change=on_nav,
        indicator_color=f"{PRIMARY}33",
        surface_tint_color=BG,
    )

    page.add(_make_header(), body, nav_bar)


if __name__ == "__main__":
    ft.app(target=main)
