import time
import threading
from datetime import datetime, timedelta
import pystray
from PIL import Image, ImageDraw, ImageFont
import sys

class PomodoroTimer:
    def __init__(self):
        self.start_time = None
        self.is_running = False
        self.timer_thread = None
        self.icon = None
        
    def create_icon(self, text="0"):
        # Create an icon with transparent background and centered text
        width = 64
        height = 64
        # Transparent canvas (RGBA), no white background
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Draw a simple circle for the icon
        draw.ellipse([2, 2, 62, 62], fill='red', outline='darkred')

        # Add timer text (white, 32px)
        try:
            font = self._get_font(36)
            # Center text using textbbox to compute exact size
            bbox = draw.textbbox((0, 0), text, font=font, anchor='lt')
            text_w = (bbox[2] - bbox[0]) + 2
            text_h = (bbox[3] - bbox[1])+ 3
            center_x = width // 2
            center_y = height // 2
            draw.text((center_x - text_w // 2, center_y - text_h // 2), text, fill=(255, 255, 255, 255), font=font)
        except Exception:
            # Fallback if font loading or drawing fails
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

    def format_minutes_only(self, elapsed):
        total_seconds = int(elapsed.total_seconds())
        minutes = total_seconds // 60
        return f"{minutes}"
    
    def update_icon(self):
        while self.is_running:
            if self.start_time:
                elapsed = self.get_elapsed_time()
                # Display minutes only
                minute_text = self.format_minutes_only(elapsed)
                new_icon = self.create_icon(minute_text)
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
            self.icon.icon = self.create_icon("::")
            print("Timer stopped!")
    
    def reset_timer(self):
        self.stop_timer()
        self.icon.icon = self.create_icon("0")

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
        # Create initial icon TK change this back to later
        initial_icon = self.create_icon("66")
        
        # Create the system tray icon
        self.icon = pystray.Icon("PomodorUP", initial_icon, "PomodorUP Timer", self.create_menu())
        
        # Run the app
        self.icon.run()

    def _get_font(self, size):
        """Try to load a macOS system font at given size; fallback to default."""
        try:
            # San Francisco fonts are not directly accessible; use Helvetica as a close default
            return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
        except Exception:
            try:
                return ImageFont.truetype("Helvetica", size)
            except Exception:
                return ImageFont.load_default()

if __name__ == "__main__":
    timer = PomodoroTimer()
    timer.run()
