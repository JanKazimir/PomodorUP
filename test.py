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
		self.is_paused = False
		self.paused_elapsed = timedelta(0)
		self.timer_thread = None
		self.icon = None

		# Target duration state
		self.target_duration = timedelta(minutes=25)
		self.recent_targets_minutes = [25]
		self.max_recent_targets = 5

		# In-menu input buffer for Set Target (string of digits or empty)
		self._input_buffer = ""
		
	def create_icon(self, text="0"):
		# Create an icon with transparent background and centered text
		width = 64
		height = 64
		image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
		draw = ImageDraw.Draw(image)

		# Circle geometry
		circle_bbox = [2, 2, 62, 62]
		inner_width = circle_bbox[2] - circle_bbox[0]
		inner_height = circle_bbox[3] - circle_bbox[1]

		# Prepare band colors bottom -> top
		band_colors_hex = [
			"#5E46D2FF",  # dark_purple
			"#8130C2FF",  # mauve
			"#A5268CFF",  # fuschia
			"#F22659FF",  # red
			"#FF663FFF",  # orange
			"#F2CC3FFF",  # yellow
		]

		def hex_to_rgba_tuple(h):
			# Expect #RRGGBBAA
			r = int(h[1:3], 16)
			g = int(h[3:5], 16)
			b = int(h[5:7], 16)
			a = int(h[7:9], 16)
			return (r, g, b, a)

		base_colors = [hex_to_rgba_tuple(h) for h in band_colors_hex]

		# Compute elapsed seconds and part size
		elapsed = self.get_elapsed_time()
		elapsed_s = max(0.0, elapsed.total_seconds())
		total_target_s = max(1.0, self.target_duration.total_seconds() or 1.0)
		part_s = total_target_s / 6.0

		# Determine per-band color and opacity
		bands = []  # list of (r,g,b,a_float 0..1)

		steps = int(elapsed_s // part_s)
		step_progress_s = elapsed_s - steps * part_s

		if steps <= 5:
			# Initial fill-in (bottom to top), each band fades in over 1s at its start
			for i in range(6):
				band_start_s = i * part_s
				if elapsed_s < band_start_s:
					opacity = 0.0
					color = base_colors[i]
				elif elapsed_s < band_start_s + 1.0:
					opacity = min(1.0, max(0.0, (elapsed_s - band_start_s) / 1.0))
					color = base_colors[i]
				else:
					opacity = 1.0
					color = base_colors[i]
				bands.append((color[0], color[1], color[2], opacity))
		else:
			# After target: cyclic color transitions per band
			post_steps = steps - 6
			current_band = ((steps - 7) % 6) if steps >= 7 else None
			for i in range(6):
				# How many completed changes this band has undergone
				changes_completed = 0
				if steps >= 7:
					changes_completed = max(0, (post_steps - i) // 6 + 1) if (steps >= (7 + i)) else 0
				old_index = i
				new_index = (i + changes_completed) % 6
				color = base_colors[new_index]
				opacity = 1.0
				# If this is the band currently transitioning in this step, animate 2s window
				if current_band is not None and i == current_band:
					if step_progress_s < 1.0:
						# Fade out old color 1s
						color = base_colors[(old_index + (changes_completed - 1) % 6) % 6] if changes_completed > 0 else base_colors[old_index]
						opacity = max(0.0, 1.0 - step_progress_s)
					elif step_progress_s < 2.0:
						# Fade in new color 1s
						color = base_colors[new_index]
						opacity = max(0.0, min(1.0, step_progress_s - 1.0))
					else:
						color = base_colors[new_index]
						opacity = 1.0
				bands.append((color[0], color[1], color[2], opacity))

		# If timer not running, halve the opacity of all bands
		if not self.is_running:
			bands = [(r, g, b, a * 0.5) for (r, g, b, a) in bands]

		# Draw base circle outline
		draw.ellipse(circle_bbox, fill=None, outline='darkred')

		# Draw bands inside the circle using a mask
		circle_mask = Image.new('L', (width, height), 0)
		mask_draw = ImageDraw.Draw(circle_mask)
		mask_draw.ellipse(circle_bbox, fill=255)

		bands_image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
		b_draw = ImageDraw.Draw(bands_image)
		band_height = inner_height // 6
		for idx, (r, g, b, a_float) in enumerate(bands):
			band_top = circle_bbox[1] + inner_height - (idx + 1) * band_height
			band_bottom = band_top + band_height
			alpha = int(max(0, min(255, round(a_float * 255))))
			b_draw.rectangle(
				[circle_bbox[0], band_top, circle_bbox[2], band_bottom],
				fill=(r, g, b, alpha)
			)

		# Composite bands into the circle area
		image = Image.composite(bands_image, image, circle_mask)
		draw = ImageDraw.Draw(image)

		# Add timer text (white, monospace)
		try:
			font = self._get_font(38, bold=False, monospace=True)
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
			# Show paused minutes using current delimiter preference
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
			items.append(pystray.MenuItem(label, lambda m=minutes: self._select_recent_target(m)))
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

	# In-menu digit input helpers
	def _input_preview(self):
		return self._input_buffer if self._input_buffer != "" else "_"
		
	def _append_digit(self, d):
		d = str(d)
		if d.isdigit() and len(self._input_buffer) < 3:
			self._input_buffer += d
		self._rebuild_menu()
		
	def _backspace_digit(self):
		self._input_buffer = self._input_buffer[:-1]
		self._rebuild_menu()
		
	def _clear_input(self):
		self._input_buffer = ""
		self._rebuild_menu()
		
	def _apply_input(self):
		if self._input_buffer == "":
			return
		try:
			value = int(self._input_buffer)
			value = max(0, value)
			self.set_target_minutes(value)
			print(f"Target set to {value} minutes")
		finally:
			self._input_buffer = ""
			self._rebuild_menu()
		
	def _cancel_input(self):
		self._input_buffer = ""
		self._rebuild_menu()
		
	def _set_target_menu(self):
		current_preview = int(self.target_duration.total_seconds() // 60)
		digits = [
			pystray.MenuItem("0", lambda: self._append_digit(0)),
			pystray.MenuItem("1", lambda: self._append_digit(1)),
			pystray.MenuItem("2", lambda: self._append_digit(2)),
			pystray.MenuItem("3", lambda: self._append_digit(3)),
			pystray.MenuItem("4", lambda: self._append_digit(4)),
			pystray.MenuItem("5", lambda: self._append_digit(5)),
			pystray.MenuItem("6", lambda: self._append_digit(6)),
			pystray.MenuItem("7", lambda: self._append_digit(7)),
			pystray.MenuItem("8", lambda: self._append_digit(8)),
			pystray.MenuItem("9", lambda: self._append_digit(9)),
		]
		return pystray.Menu(
			pystray.MenuItem(f"Current: {current_preview} Minutes", None, enabled=False),
			pystray.MenuItem(f"Type: {self._input_preview()}", None, enabled=False),
			pystray.Menu.SEPARATOR,
			*digits,
			pystray.Menu.SEPARATOR,
			pystray.MenuItem("Backspace", self._backspace_digit),
			pystray.MenuItem("Clear", self._clear_input),
			pystray.Menu.SEPARATOR,
			pystray.MenuItem("Apply", self._apply_input),
			pystray.MenuItem("Cancel", self._cancel_input),
		)
		
	def create_menu(self):
		# Timer controls
		start_or_resume_label = "Start Timer" if not (self.is_paused or self.is_running) else ("Resume Timer" if self.is_paused and not self.is_running else "Start Timer")
		pause_label = "Pause Timer"

		# Target Duration submenu
		recent_items = self._recent_targets_menu_items()
		target_menu = pystray.Menu(
			pystray.MenuItem("Set Target", self._set_target_menu()),
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

	def _get_font(self, size, bold=False, monospace=False):
		"""Try to load a macOS system font at given size; fallback to default.
		If bold requested, try bold faces first. If monospace, try Menlo/Monaco.
		"""
		if monospace:
			# Prefer Menlo on macOS, fallback to Monaco, then SF Mono if available
			for path in [
				"/System/Library/Fonts/Menlo.ttc",
				"/System/Library/Fonts/Monaco.ttf",
				"/System/Applications/Utilities/Terminal.app/Contents/Resources/Fonts/SFMono-Regular.ttf",
			]:
				try:
					return ImageFont.truetype(path, size)
				except Exception:
					continue
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
			return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
		except Exception:
			try:
				return ImageFont.truetype("Helvetica", size)
			except Exception:
				return ImageFont.load_default()

if __name__ == "__main__":
	timer = PomodoroTimer()
	timer.run()
