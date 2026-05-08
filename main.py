import flet as ft
import time
import threading
import random

def main(page: ft.Page):
    page.title = "SINDBAD OBD PRO + AI"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0a0f1a"
    page.padding = 10
    page.spacing = 10

    # متغيرات العدادات
    rpm_text = ft.Text("0", size=25, weight="bold", color="#3b82f6")
    temp_text = ft.Text("0", size=25, weight="bold", color="#3b82f6")
    speed_text = ft.Text("0", size=25, weight="bold", color="#3b82f6")

    # تصميم كرت العداد
    def create_gauge(title, value_obj, icon):
        return ft.Container(
            content=ft.Column([
                ft.Icon(icon, color="#3b82f6", size=20),
                ft.Text(title, size=10, color="white"),
                value_obj,
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor="#111827", padding=10, border_radius=10, expand=True
        )

    # صف العدادات
    gauges_row = ft.Row([
        create_gauge("RPM", rpm_text, ft.icons.SPEED),
        create_gauge("TEMP", temp_text, ft.icons.THERMOSTAT),
        create_gauge("SPEED", speed_text, ft.icons.ELECTRIC_CAR),
    ], spacing=10)

    # قسم ذكاء جوجل (Gemini) - سيفتح واجهة الدردشة
    ai_section = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.icons.AUTO_AWESOME, color="orange"),
                ft.Text("مساعد سندباد الذكي (Gemini)", color="white", weight="bold"),
            ]),
            ft.ElevatedButton(
                "فتح دردشة الذكاء الاصطناعي",
                icon=ft.icons.CHAT,
                on_click=lambda _: page.launch_url("https://gemini.google.com"),
                style=ft.ButtonStyle(bgcolor="#3b82f6", color="white")
            ),
        ]),
        bgcolor="#1e293b", padding=15, border_radius=15
    )

    page.add(
        ft.Text("SINDBAD OBD PRO", size=22, weight="bold", color="white"),
        gauges_row,
        ft.Divider(height=20, color="#1e2d45"),
        ai_section,
        ft.Text("جاري سحب البيانات من الحساسات...", size=10, color="#64748b")
    )

    # دالة التحديث التلقائي (الحياة في البرنامج)
    def update_data():
        time.sleep(1)
        while True:
            try:
                rpm_text.value = str(random.randint(700, 4000))
                temp_text.value = str(random.randint(85, 105))
                speed_text.value = str(random.randint(0, 160))
                page.update()
                time.sleep(0.5) # تحديث سريع كل نصف ثانية
            except:
                break

    threading.Thread(target=update_data, daemon=True).start()

if __name__ == "__main__":
    ft.app(target=main)
