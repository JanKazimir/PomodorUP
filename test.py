import time
import threading
from datetime import datetime, timedelta
import pystray
from PIL import Image, ImageDraw
import sys

class PomodoroTimer:
    def __init__(self):
        self.start_time = None
        self.is_running = False
        self.timer_thread = None
        self.icon = None
        
    def create_icon(self, text="00:00"):
        # Create a simple icon with the timer text
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(image)
        
        # Draw a simple circle for the icon
        draw.ellipse([8, 8, 56, 56], fill='red', outline='darkred')
        
        # Add timer text
        try:
            draw.text((width//2, height//2), text, fill='white', anchor='mm')
        except:
            # Fallback if text drawing fails
            pass
            
        return image
    
    def get_elapsed_time(self):
        if self.start_time:
            elapsed = datetime.now() - self.start_time
            return elapsed
        return timedelta(0)
    
    def format_time(self, elapsed):
        total_seconds = int(elapsed.total_seconds())
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"
    
    def update_icon(self):
        while self.is_running:
            if self.start_time:
                elapsed = self.get_elapsed_time()
                time_text = self.format_time(elapsed)
                new_icon = self.create_icon(time_text)
                self.icon.icon = new_icon
            time.sleep(1)
    
    def start_timer(self):
        if not self.is_running:
            self.start_time = datetime.now()
            self.is_running = True
            self.timer_thread = threading.Thread(target=self.update_icon, daemon=True)
            self.timer_thread.start()
            print("Timer started!")
    
    def stop_timer(self):
        if self.is_running:
            self.is_running = False
            self.start_time = None
            self.icon.icon = self.create_icon("00:00")
            print("Timer stopped!")
    
    def reset_timer(self):
        self.stop_timer()
        print("Timer reset!")
    
    def quit_app(self):
        self.stop_timer()
        self.icon.stop()
        sys.exit()
    
    def create_menu(self):
        menu = pystray.Menu(
            pystray.MenuItem("Start Timer", self.start_timer),
            pystray.MenuItem("Stop Timer", self.stop_timer),
            pystray.MenuItem("Reset Timer", self.reset_timer),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self.quit_app)
        )
        return menu
    
    def run(self):
        # Create initial icon
        initial_icon = self.create_icon("00:00")
        
        # Create the system tray icon
        self.icon = pystray.Icon("PomodorUP", initial_icon, "PomodorUP Timer", self.create_menu())
        
        # Run the app
        self.icon.run()

if __name__ == "__main__":
    timer = PomodoroTimer()
    timer.run()
