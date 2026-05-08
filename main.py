import flet as ft
import time
import threading
import random

def main(page: ft.Page):
    # إعدادات الصفحة الأساسية لتجنب التعليق
    page.title = "SINDBAD OBD PRO"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0a0f1a"
    page.window_resizable = False
    page.padding = 20

    # إنشاء العناصر بشكل منفصل لضمان استقرارها
    title = ft.Text("SINDBAD OBD PRO", size=24, weight="bold", color="white")
    
    rpm_val = ft.Text("0", size=30, weight="bold", color="#3b82f6")
    temp_val = ft.Text("0", size=30, weight="bold", color="#3b82f6")

    # تصميم بسيط جداً (بدون كلاسات معقدة حالياً)
    container_rpm = ft.Container(
        content=ft.Column([
            ft.Icon(ft.icons.SPEED, color="#3b82f6"),
            ft.Text("RPM", size=12, color="white"),
            rpm_val
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor="#111827", padding=20, border_radius=10, expand=True
    )

    container_temp = ft.Container(
        content=ft.Column([
            ft.Icon(ft.icons.THERMOSTAT, color="#3b82f6"),
            ft.Text("TEMP", size=12, color="white"),
            temp_val
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor="#111827", padding=20, border_radius=10, expand=True
    )

    # إضافة العناصر للصفحة
    page.add(
        title,
        ft.Row([container_rpm, container_temp], spacing=10)
    )

    # دالة التحديث
    def update_stats():
        time.sleep(2) # انتظار ثانيتين لضمان استقرار الواجهة
        while True:
            try:
                rpm_val.value = str(random.randint(700, 3000))
                temp_val.value = str(random.randint(85, 95))
                page.update()
                time.sleep(1)
            except:
                break

    # تشغيل التحديث في خيط منفصل
    threading.Thread(target=update_stats, daemon=True).start()

if __name__ == "__main__":
    # تشغيل التطبيق مع التأكد من إعدادات الـ Assets
    ft.app(target=main)
