import time
import threading
from datetime import datetime, timedelta
import pystray
from PIL import Image, ImageDraw, ImageFont
import sys

# PyObjC imports for macOS dialog to set target duration
try:
	from Cocoa import NSAlert, NSButton, NSView, NSPopUpButton, NSMakeRect, NSApplication, NSApp
	PYOBJ_AVAILABLE = True
except Exception:
	PYOBJ_AVAILABLE = False

class PomodoroTimer:
	def __init__(self):
		self.start_time = None
		self.is_running = False
		self.is_paused = False
		self.paused_elapsed = timedelta(0)
		self.timer_thread = None
		self.icon = None

		# Target duration state
		self.target_duration = timedelta(minutes=25)
		self.recent_targets_minutes = [25]
		self.max_recent_targets = 5
		
	def create_icon(self, text="0"):
		# Create an icon with transparent background and centered text
		width = 64
		height = 64
		# Transparent canvas (RGBA), no white background
		image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
		draw = ImageDraw.Draw(image)

		# Draw a simple circle for the icon
		draw.ellipse([2, 2, 62, 62], fill='red', outline='darkred')

		# Add timer text (white, 32px) in bold
		try:
			font = self._get_font(38, bold=True)
			# Center text using textbbox to compute exact size
			bbox = draw.textbbox((0, 0), text, font=font, anchor='lt', stroke_width=0)
			text_w = (bbox[2] - bbox[0]) + 1
			text_h = (bbox[3] - bbox[1]) + 11
			center_x = width // 2
			center_y = height // 2
			draw.text(
				(center_x - text_w // 2, center_y - text_h // 2),
				text,
				fill=(255, 255, 255, 255),
				font=font,
				stroke_width=0,
				stroke_fill=(0, 0, 0, 180),
			)
		except Exception:
			# Fallback if font loading or drawing fails
			pass

		return image
		
	def get_elapsed_time(self):
		if self.start_time and self.is_running:
			return (datetime.now() - self.start_time) + self.paused_elapsed
		return self.paused_elapsed
		
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
			# Resume from pause: keep accumulated paused_elapsed
			self.start_time = datetime.now()
			self.is_running = True
			self.is_paused = False
			self.timer_thread = threading.Thread(target=self.update_icon, daemon=True)
			self.timer_thread.start()
			print("Timer started!")
			# Refresh menu label
			self._rebuild_menu()
		
	def pause_timer(self):
		if self.is_running:
			# Accumulate elapsed into paused_elapsed and stop running
			self.paused_elapsed += datetime.now() - self.start_time
			self.is_running = False
			self.is_paused = True
			self.start_time = None
			# Show paused minutes in braces
			elapsed = self.get_elapsed_time()
			minute_text = self.format_minutes_only(elapsed)
			self.icon.icon = self.create_icon(f":{minute_text}:")
			print("Timer paused!")
			self._rebuild_menu()
		
	def reset_timer(self):
		# Reset all timing state
		self.is_running = False
		self.is_paused = False
		self.start_time = None
		self.paused_elapsed = timedelta(0)
		self.icon.icon = self.create_icon("0")

		print("Timer reset!")
		self._rebuild_menu()
		
	def quit_app(self):
		self.is_running = False
		self.icon.stop()
		sys.exit()
		
	def _rebuild_menu(self):
		if self.icon is not None:
			self.icon.menu = self.create_menu()
			self.icon.update_menu()
		
	def _recent_targets_menu_items(self):
		# Build a list of MenuItems for recent targets (skip duplicates, most recent first)
		items = []
		for minutes in self.recent_targets_minutes[: self.max_recent_targets]:
			label = f"{minutes} Minutes"
			items.append(pystray.MenuItem(label, lambda _, m=minutes: self._select_recent_target(m)))
		return items
		
	def _select_recent_target(self, minutes):
		self.set_target_minutes(minutes)
		print(f"Target set to {minutes} minutes")

	def set_target_minutes(self, minutes):
		# Normalize and update target + recent list
		minutes = max(0, int(minutes))
		self.target_duration = timedelta(minutes=minutes)
		# Update MRU list
		if minutes in self.recent_targets_minutes:
			self.recent_targets_minutes.remove(minutes)
		self.recent_targets_minutes.insert(0, minutes)
		self.recent_targets_minutes = self.recent_targets_minutes[: self.max_recent_targets]
		self._rebuild_menu()

	def divide_target_into_six(self):
		"""Return a list of six timedelta parts that sum to target_duration."""
		total_seconds = int(self.target_duration.total_seconds())
		part = total_seconds // 6
		# Distribute remainder seconds to the first parts
		remainder = total_seconds % 6
		parts = []
		for i in range(6):
			additional = 1 if i < remainder else 0
			parts.append(timedelta(seconds=part + additional))
		return parts
		
	def _show_set_target_dialog(self):
		"""Show a macOS dialog to select two digits (tens and ones) for minutes."""
		if not PYOBJ_AVAILABLE:
			print("PyObjC not available; cannot open selector. Falling back to 25 minutes.")
			self.set_target_minutes(25)
			return

		# Ensure NSApp is initialized
		try:
			app = NSApp()
		except Exception:
			app = None

		alert = NSAlert.alloc().init()
		alert.setMessageText_("Set Target Duration")
		alert.setInformativeText_("Select minutes (two digits)")
		alert.addButtonWithTitle_("Select")
		alert.addButtonWithTitle_("Cancel")

		# Create accessory view ~ 5rem x 5rem (~80px x ~80px)
		container_w = 160
		container_h = 100
		container = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, container_w, container_h))

		# Two popup buttons for digits 0-9
		popup_width = 60
		popup_height = 26
		gap = 20
		top = container_h - popup_height - 20
		left1 = (container_w - (popup_width*2 + gap)) // 2
		left2 = left1 + popup_width + gap

		popup_tens = NSPopUpButton.alloc().initWithFrame_(NSMakeRect(left1, top, popup_width, popup_height))
		popup_ones = NSPopUpButton.alloc().initWithFrame_(NSMakeRect(left2, top, popup_width, popup_height))
		for n in range(10):
			popup_tens.addItemWithTitle_(str(n))
			popup_ones.addItemWithTitle_(str(n))

		# Preselect current target minutes (clamped to two digits)
		current = int(self.target_duration.total_seconds() // 60)
		current = max(0, min(99, current))
		tens = current // 10
		ones = current % 10
		popup_tens.selectItemAtIndex_(tens)
		popup_ones.selectItemAtIndex_(ones)

		container.addSubview_(popup_tens)
		container.addSubview_(popup_ones)

		alert.setAccessoryView_(container)

		response = alert.runModal()
		# NSAlertFirstButtonReturn is typically 1000 for the first button; avoid using constants directly
		if int(response) == 1000:
			selected_minutes = (popup_tens.indexOfSelectedItem() * 10) + popup_ones.indexOfSelectedItem()
			self.set_target_minutes(selected_minutes)
		else:
			print("Set Target canceled")

	def create_menu(self):
		# Timer controls
		start_or_resume_label = "Start Timer" if not (self.is_paused or self.is_running) else ("Resume Timer" if self.is_paused and not self.is_running else "Start Timer")
		pause_label = "Pause Timer"

		# Target Duration submenu
		recent_items = self._recent_targets_menu_items()
		target_menu = pystray.Menu(
			pystray.MenuItem("Set Target", lambda: self._show_set_target_dialog()),
			pystray.MenuItem("Recent Targets:", None, enabled=False),
			*recent_items
		)

		menu = pystray.Menu(
			pystray.MenuItem(start_or_resume_label, self.start_timer),
			pystray.MenuItem(pause_label, self.pause_timer),
			pystray.MenuItem("Reset Timer", self.reset_timer),
			pystray.Menu.SEPARATOR,
			pystray.MenuItem("Target Duration", target_menu),
			pystray.Menu.SEPARATOR,
			pystray.MenuItem("Quit", self.quit_app)
		)
		return menu
		
	def run(self):
		# Create initial icon
		initial_minutes = int(self.target_duration.total_seconds() // 60)
		initial_icon = self.create_icon(str(initial_minutes))
		
		# Create the system tray icon
		self.icon = pystray.Icon("PomodorUP", initial_icon, "PomodorUP Timer", self.create_menu())
		
		# Run the app
		self.icon.run()

	def _get_font(self, size, bold=False):
		"""Try to load a macOS system font at given size; fallback to default.
		If bold requested, try bold faces first.
		"""
		if bold:
			for path in [
				"/System/Library/Fonts/Supplemental/Arial Bold.ttf",
				"/System/Library/Fonts/Supplemental/HelveticaNeue.ttc",
			]:
				try:
					return ImageFont.truetype(path, size)
				except Exception:
					continue
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
