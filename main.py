import flet as ft
import threading
import time
import random

# محاولة استيراد مكتبة OBD بأمان لضمان عدم تعليق التطبيق
try:
    import obd
    OBD_AVAILABLE = True
except ImportError:
    OBD_AVAILABLE = False

def main(page: ft.Page):
    page.title = "SINDBAD OBD PRO"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0a0f1a"
    page.rtl = True
    page.padding = 20

    # تعريف النصوص والعدادات
    rpm_text = ft.Text("0", size=30, weight="bold", color="#3b82f6")
    temp_text = ft.Text("0", size=30, weight="bold", color="#3b82f6")
    speed_text = ft.Text("0", size=30, weight="bold", color="#3b82f6")
    
    # حالة المكتبة والاتصال
    lib_status = "مثبتة" if OBD_AVAILABLE else "غير مثبتة (سيتم استخدام المحاكي)"
    status_text = ft.Text(f"المكتبة: {lib_status}", color="#64748b", size=12)

    def create_gauge(title, val_obj, icon):
        return ft.Container(
            content=ft.Column([
                ft.Icon(icon, color="#3b82f6", size=30),
                ft.Text(title, size=14, color="white", weight="bold"),
                val_obj,
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor="#111827", padding=15, border_radius=15, expand=True,
            border=ft.border.all(1, "#1e2d45")
        )

    # قسم المساعد الذكي Gemini
    ai_section = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.icons.AUTO_AWESOME, color="orange"),
                ft.Text("مساعد سندباد الذكي (Gemini)", color="white", weight="bold"),
            ]),
            ft.Text("اسأل الذكاء الاصطناعي عن أعطال سيارتك", size=12, color="#94a3b8"),
            ft.ElevatedButton(
                "فتح محادثة Gemini",
                icon=ft.icons.CHAT,
                on_click=lambda _: page.launch_url("https://gemini.google.com"),
                style=ft.ButtonStyle(bgcolor="#3b82f6", color="white")
            ),
        ], spacing=10),
        bgcolor="#1e293b", padding=20, border_radius=20, margin=ft.margin.only(top=20)
    )

    page.add(
        ft.Text("SINDBAD OBD PRO", size=26, weight="bold", color="white"),
        status_text,
        ft.Row([
            create_gauge("دوران المحرك", rpm_text, ft.icons.SPEED),
            create_gauge("الحرارة", temp_text, ft.icons.THERMOSTAT),
        ], spacing=10),
        ft.Row([
            create_gauge("السرعة", speed_text, ft.icons.ELECTRIC_CAR),
        ]),
        ai_section
    )

    def data_thread():
        # إذا كانت المكتبة موجودة، نحاول الاتصال بالسيارة
        connection = None
        if OBD_AVAILABLE:
            try:
                connection = obd.OBD()
            except:
                connection = None

        while True:
            try:
                # لو متصل بالسيارة فعلياً
                if connection and connection.is_connected():
                    r_rpm = connection.query(obd.commands.RPM)
                    r_temp = connection.query(obd.commands.COOLANT_TEMP)
                    r_speed = connection.query(obd.commands.SPEED)
                    
                    rpm_text.value = str(int(r_rpm.value.magnitude)) if not r_rpm.is_null() else "0"
                    temp_text.value = str(int(r_temp.value.magnitude)) if not r_temp.is_null() else "0"
                    speed_text.value = str(int(r_speed.value.magnitude)) if not r_speed.is_null() else "0"
                else:
                    # نظام المحاكاة (لو مفيش وصلة حالياً عشان البرنامج يفضل "حي")
                    rpm_text.value = str(random.randint(700, 2500))
                    temp_text.value = str(random.randint(85, 100))
                    speed_text.value = str(random.randint(0, 120))
                
                page.update()
                time.sleep(0.5)
            except:
                break

    threading.Thread(target=data_thread, daemon=True).start()

if __name__ == "__main__":
    ft.app(target=main)
