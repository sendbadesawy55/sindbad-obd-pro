import flet as ft
import math
import random
import time
import threading
from datetime import datetime

# --- الإعدادات والألوان ---
PRIMARY = "#3b82f6"
BG = "#0a0f1a"
CARD_BG = "#111827"
TEXT = "#f1f5f9"
GREEN = "#22c55e"
RED = "#ef4444"

class SensorCard(ft.Container):
    def __init__(self, title, unit, min_val, max_val, icon_name, precision=0):
        super().__init__()
        self.title = title
        self.unit = unit
        self.min_val = min_val
        self.max_val = max_val
        self.icon_name = icon_name
        self.precision = precision
        
        self.bgcolor = CARD_BG
        self.padding = 15
        self.border_radius = 12
        self.border = ft.border.all(1, "#1e2d45")
        
        self.val_text = ft.Text("0", size=24, weight="bold", color=PRIMARY)
        self.progress = ft.ProgressBar(value=0, bgcolor="#1e293b", color=PRIMARY, height=6)
        
        self.content = ft.Column([
            ft.Row([
                ft.Icon(self.icon_name, color=PRIMARY, size=20),
                ft.Text(self.title, size=14, color=TEXT, weight="w600"),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            self.val_text,
            ft.Text(self.unit, size=10, color="#64748b"),
            self.progress
        ], spacing=8)

    def set_value(self, v):
        self.val_text.value = f"{v:.{self.precision}f}"
        pct = max(0.0, min(1.0, (v - self.min_val) / (self.max_val - self.min_val)))
        self.progress.value = pct
        self.update()

def main(page: ft.Page):
    page.title = "SINDBAD OBD PRO"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG
    page.rtl = True
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO

    # الهيدر
    header = ft.Container(
        content=ft.Row([
            ft.Column([
                ft.Text("SINDBAD OBD PRO", size=22, weight="bold", color="white"),
                ft.Text("نظام التشخيص الذكي", size=12, color="#64748b"),
            ]),
            ft.Icon(ft.icons.DIRECTIONS_CAR_FILLED, color=PRIMARY, size=30)
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        margin=ft.margin.only(bottom=20)
    )

    # الكروت
    rpm_card = SensorCard("دوران المحرك", "RPM", 0, 8000, ft.icons.SPEED)
    temp_card = SensorCard("حرارة المحرك", "°C", 0, 120, ft.icons.THERMOSTAT)
    speed_card = SensorCard("سرعة السيارة", "km/h", 0, 220, ft.icons.SHUTTLE_BUS)
    volt_card = SensorCard("جهد البطارية", "Volt", 10, 16, ft.icons.BATTERY_CHARGING_FULL, precision=1)

    page.add(
        header,
        ft.ResponsiveRow([
            ft.Column([rpm_card], col={"xs": 12, "md": 6}),
            ft.Column([speed_card], col={"xs": 12, "md": 6}),
            ft.Column([temp_card], col={"xs": 12, "md": 6}),
            ft.Column([volt_card], col={"xs": 12, "md": 6}),
        ], spacing=15),
    )

    # محاكي للبيانات (عشان تجرب البرنامج فوراً)
    def simulate_data():
        while True:
            rpm_card.set_value(random.uniform(700, 3500))
            temp_card.set_value(random.uniform(85, 95))
            speed_card.set_value(random.uniform(0, 120))
            volt_card.set_value(random.uniform(13.2, 14.4))
            time.sleep(1)

    threading.Thread(target=simulate_data, daemon=True).start()

if __name__ == "__main__":
    ft.app(target=main)
