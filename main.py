import flet as ft
import obd
import threading
import time

def main(page: ft.Page):
    page.title = "SINDBAD OBD PRO"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0a0f1a"
    page.rtl = True

    # تعريف العدادات
    rpm_text = ft.Text("0", size=30, weight="bold", color="#3b82f6")
    temp_text = ft.Text("0", size=30, weight="bold", color="#3b82f6")
    speed_text = ft.Text("0", size=30, weight="bold", color="#3b82f6")
    status_text = ft.Text("الحالة: جاري البحث عن وصلة OBD...", color="orange", size=12)

    def create_gauge(title, val_obj, icon):
        return ft.Container(
            content=ft.Column([
                ft.Icon(icon, color="#3b82f6"),
                ft.Text(title, size=12, color="white"),
                val_obj
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor="#111827", padding=15, border_radius=12, expand=True
        )

    # زر المساعد الذكي
    ai_btn = ft.Container(
        content=ft.Column([
            ft.Row([ft.Icon(ft.icons.AUTO_AWESOME, color="orange"), ft.Text("اسأل مساعد سندباد (Gemini)", color="white")]),
            ft.ElevatedButton("تحدث مع الذكاء الاصطناعي", on_click=lambda _: page.launch_url("https://gemini.google.com"))
        ]),
        bgcolor="#1e293b", padding=15, border_radius=15
    )

    page.add(
        ft.Text("SINDBAD OBD PRO", size=24, weight="bold"),
        status_text,
        ft.Row([
            create_gauge("دوران المحرك", rpm_text, ft.icons.SPEED),
            create_gauge("الحرارة", temp_text, ft.icons.THERMOSTAT),
            create_gauge("السرعة", speed_text, ft.icons.ELECTRIC_CAR)
        ]),
        ft.Divider(height=30),
        ai_btn
    )

    def obd_thread():
        # محاولة الاتصال بالبلوتوث/WiFi الخاص بالسيارة
        connection = obd.OBD() 
        while True:
            if connection.is_connected():
                status_text.value = "الحالة: متصل بالسيارة ✅"
                status_text.color = "#22c55e"
                
                # قراءة البيانات الحقيقية
                r_rpm = connection.query(obd.commands.RPM)
                r_temp = connection.query(obd.commands.COOLANT_TEMP)
                r_speed = connection.query(obd.commands.SPEED)

                if not r_rpm.is_null(): rpm_text.value = str(r_rpm.value.magnitude)
                if not r_temp.is_null(): temp_text.value = str(r_temp.value.magnitude)
                if not r_speed.is_null(): speed_text.value = str(r_speed.value.magnitude)
            else:
                status_text.value = "الحالة: فصل الاتصال! جاري المحاولة..."
                status_text.color = "red"
                connection = obd.OBD() # إعادة محاولة الاتصال
            
            page.update()
            time.sleep(0.5)

    threading.Thread(target=obd_thread, daemon=True).start()

if __name__ == "__main__":
    ft.app(target=main)
