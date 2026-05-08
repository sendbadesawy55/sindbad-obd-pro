import flet as ft
import time
import threading
import random

# كلاس الحساسات بتصميم بسيط يمنع تجمد الشاشة
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
        
        self.val_text = ft.Text("0", size=20, weight="bold", color="#3b82f6")
        
        self.content = ft.Column([
            ft.Icon(self.icon_name, color="#3b82f6", size=25),
            ft.Text(self.title, size=12, color="white"),
            self.val_text,
            ft.Text(self.unit, size=9, color="#64748b"),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def update_val(self, v):
        self.val_text.value = str(v)
        self.update()

def main(page: ft.Page):
    page.title = "SINDBAD OBD"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0a0f1a"
    page.window_resizable = False
    
    # تأكد من استخدام ft.icons بحروف صغيرة
    rpm = SensorCard("دوران المحرك", "RPM", ft.icons.SPEED)
    temp = SensorCard("الحرارة", "°C", ft.icons.THERMOSTAT)
    
    page.add(
        ft.Text("SINDBAD OBD PRO", size=20, weight="bold", color="white"),
        ft.Row([rpm, temp], spacing=10)
    )

    def run_sim():
        # انتظر ثانية واحدة للتأكد من تحميل الواجهة تماماً
        time.sleep(1)
        while True:
            try:
                # تحديث القيم بشكل عشوائي للتبسيط
                rpm.update_val(random.randint(700, 3000))
                temp.update_val(random.randint(80, 95))
                time.sleep(1)
            except:
                break

    # تشغيل التحديث في الخلفية
    t = threading.Thread(target=run_sim, daemon=True)
    t.start()

if __name__ == "__main__":
    ft.app(target=main)
