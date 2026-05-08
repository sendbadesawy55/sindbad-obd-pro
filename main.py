import flet as ft
import time
import threading
import random

class SensorCard(ft.Container):
    def __init__(self, title, unit, icon_name):
        super().__init__()
        self.title = title
        self.unit = unit
        self.icon_name = icon_name
        self.bgcolor = "#111827"
        self.padding = 15
        self.border_radius = 12
        self.expand = True
        self.val_text = ft.Text("0", size=24, weight="bold", color="#3b82f6")
        
        self.content = ft.Column([
            ft.Icon(self.icon_name, color="#3b82f6", size=30),
            ft.Text(self.title, size=14, color="white", weight="bold"),
            self.val_text,
            ft.Text(self.unit, size=10, color="#64748b"),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=5)

    def update_val(self, v):
        self.val_text.value = str(v)
        self.update()

def main(page: ft.Page):
    page.title = "SINDBAD OBD PRO"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0a0f1a"
    page.rtl = True
    page.padding = 20

    # العدادات
    rpm = SensorCard("دوران المحرك", "RPM", ft.icons.SPEED)
    temp = SensorCard("حرارة المحرك", "°C", ft.icons.THERMOSTAT)
    speed = SensorCard("السرعة الحالية", "km/h", ft.icons.SHUTTLE_BUS)
    volt = SensorCard("جهد البطارية", "Volt", ft.icons.BATTERY_CHARGING_FULL)

    # حالة الاتصال
    status_text = ft.Text("الحالة: جاهز للاتصال", color="#64748b", size=12)
    
    def start_connection(e):
        conn_btn.text = "جاري الاتصال..."
        conn_btn.disabled = True
        page.update()
        time.sleep(2) # محاكاة وقت الاتصال
        status_text.value = "الحالة: متصل عبر المحاكي"
        status_text.color = "#22c55e"
        conn_btn.text = "قطع الاتصال"
        conn_btn.bgcolor = "#ef4444"
        conn_btn.disabled = False
        page.update()

    conn_btn = ft.ElevatedButton(
        "بدء فحص السيارة",
        icon=ft.icons.POWER_SETTINGS_NEW,
        bgcolor="#3b82f6",
        color="white",
        on_click=start_connection,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
    )

    page.add(
        ft.Container(
            content=ft.Column([
                ft.Text("SINDBAD OBD PRO", size=24, weight="bold", color="white"),
                status_text,
            ], spacing=5),
            margin=ft.margin.only(bottom=20)
        ),
        ft.Column([
            ft.Row([rpm, temp], spacing=10),
            ft.Row([speed, volt], spacing=10),
        ], spacing=10),
        ft.Container(height=20),
        conn_btn
    )

    def run_simulation():
        while True:
            if "متصل" in status_text.value:
                rpm.update_val(random.randint(750, 4500))
                temp.update_val(random.randint(88, 98))
                speed.update_val(random.randint(0, 140))
                volt.update_val(round(random.uniform(13.5, 14.2), 1))
            time.sleep(0.5) # تحديث سريع للاستجابة

    threading.Thread(target=run_simulation, daemon=True).start()

if __name__ == "__main__":
    ft.app(target=main)
