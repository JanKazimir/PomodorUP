import time
import threading
from datetime import datetime, timedelta
import pystray
from PIL import Image, ImageDraw, ImageFont
import sys
import csv
from Cocoa import NSSavePanel
import os
import json
import subprocess

class PomodoroTimer:
	def __init__(self):
		self.start_time = None
		self.is_running = False
		self.is_paused = False
		self.paused_elapsed = timedelta(0)
		self.timer_thread = None
		self.icon = None

		# Statistics/session tracking
		self.sessions = []  # list of dicts with keys: id, date, start, end, target_minutes, elapsed
		self._session_counter = 0
		self._current_session_start = None
		self._current_session_target_minutes = None

		# Target duration state
		self.target_duration = timedelta(minutes=30)
		self.recent_targets_minutes = [30]
		self.max_recent_targets = 5
		
		# Predefined durations in minutes
		self.predefined_durations = [1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 75, 90, 120, 150, 180, 210, 240]

		# Text display mode: 'none' | 'minutes_elapsed' | 'minutes_from_target' | 'minutes_to_target' | 'minutes_past_target'
		self.text_display_mode = "minutes_elapsed"

		# In-menu input buffer for Set Target (string of digits or empty)
		self._input_buffer = ""
		# Load persisted state (sessions, recent targets, target duration)
		self._load_state()
		
	def create_icon(self, text="0", text_color=(255, 255, 255, 255)):
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
		
		# Middle grey color for initial background
		grey_color = (128, 128, 128, 255)  # middle grey

		steps = int(elapsed_s // part_s)
		step_progress_s = elapsed_s - steps * part_s

		if steps <= 5:
			# Initial fill-in (bottom to top), each band appears directly in its target color
			for i in range(6):
				band_start_s = i * part_s
				if elapsed_s < band_start_s:
					# Show transparent background when timer is running but not yet filled
					if self.is_running:
						opacity = 0.0
						color = grey_color
					else:
						# Show grey background when timer is not running
						opacity = 1.0
						color = grey_color
				else:
					# Show target color directly when band should be filled
					opacity = 1.0
					color = base_colors[i]
				bands.append((color[0], color[1], color[2], opacity))
		else:
			# After the first loop: convert bands bottom->top toward a single target color per loop.
			# Loop 0 (post-target): target = dark_purple (index 0), then mauve (1), fuschia (2), red (3), orange (4), yellow (5), then repeat.
			# During each loop, bands transition one-by-one from bottom to top to the loop's target color.
			post_target_steps = steps - 6
			loop_index = post_target_steps // 6  # 0-based index of which solid-color loop we're in
			pos_in_loop = post_target_steps % 6  # 0..5 number of bands (from bottom) already converted this loop
			current_target_color = base_colors[loop_index % 6]

			# Determine the "previous" color for bands not yet converted this loop
			if loop_index == 0:
				# First post-target loop starts from the rainbow state produced by the initial loop
				def previous_color_for_band(band_index):
					return base_colors[band_index]
			else:
				# Subsequent loops start from a solid color from the previous loop
				previous_target_color = base_colors[(loop_index - 1) % 6]
				def previous_color_for_band(band_index):
					return previous_target_color

			for i in range(6):
				if i <= pos_in_loop:
					color = current_target_color
				else:
					color = previous_color_for_band(i)
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

		# Add timer text (color specified by parameter, monospace and bold) ## text center, height etc... here
		try:
			font = self._get_font(38, bold=True, monospace=True)
			bbox = draw.textbbox((0, 0), text, font=font, anchor='lt', stroke_width=0)
			text_w = (bbox[2] - bbox[0]) - 2
			text_h = (bbox[3] - bbox[1])  + 16
			center_x = width // 2
			center_y = height // 2
			draw.text(
				(center_x - text_w // 2, center_y - text_h // 2),
				text,
				fill=text_color,
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
				# Compute display per current text display mode
				text, color = self._compute_text_and_color(elapsed)
				new_icon = self.create_icon(text, color)
				self.icon.icon = new_icon
			time.sleep(1)
		
	def start_timer(self):
		if not self.is_running:
			# If this is a fresh start (not resume), begin a new session for stats
			if not self.is_paused and self.paused_elapsed.total_seconds() == 0 and self._current_session_start is None:
				self._session_counter += 1
				self._current_session_start = datetime.now()
				self._current_session_target_minutes = int(self.target_duration.total_seconds() // 60)
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
			# Show paused text per current text display mode
			elapsed = self.get_elapsed_time()
			text, color = self._compute_text_and_color(elapsed)
			self.icon.icon = self.create_icon(text, color)
			print("Timer paused!")
			self._rebuild_menu()
		
	def reset_timer(self):
		# Finalize current session for statistics before resetting
		elapsed_before_reset = self.get_elapsed_time()
		if self._current_session_start is not None and elapsed_before_reset.total_seconds() > 0:
			self._append_session_record(end_dt=datetime.now(), elapsed_td=elapsed_before_reset)

		# Reset all timing state
		self.is_running = False
		self.is_paused = False
		self.start_time = None
		self.paused_elapsed = timedelta(0)
		
		# Show target duration in red when reset changing to dark grey #(33, 37, 43, 0)
		target_minutes = int(self.target_duration.total_seconds() // 60)
		red_color = (33, 37, 43, 200)  # Red from color palette, nope redufined to dark grey
		self.icon.icon = self.create_icon(str(target_minutes), red_color)

		print("Timer reset!")
		# Persist state after reset
		self._save_state()
		self._rebuild_menu()
		
	def quit_app(self):
		# Finalize current session for statistics on quit
		elapsed_now = self.get_elapsed_time()
		if self._current_session_start is not None and elapsed_now.total_seconds() > 0:
			self._append_session_record(end_dt=datetime.now(), elapsed_td=elapsed_now)
		# Persist before exit
		self._save_state()
		self.is_running = False
		self.icon.stop()
		sys.exit()

	def _append_session_record(self, end_dt, elapsed_td):
		# Build and store a session record, then clear current session state
		record = {
			"id": self._session_counter,
			"date": self._current_session_start.date().isoformat(),
			"start": self._current_session_start.strftime("%H:%M:%S"),
			"end": end_dt.strftime("%H:%M:%S"),
			"target_minutes": self._current_session_target_minutes if self._current_session_target_minutes is not None else int(self.target_duration.total_seconds() // 60),
			"elapsed_hms": self._format_timedelta_hms(elapsed_td),
		}
		self.sessions.append(record)
		self._current_session_start = None
		self._current_session_target_minutes = None
		self.paused_elapsed = timedelta(0)
		# Persist after recording a session
		self._save_state()

	def _format_timedelta_hms(self, td):
		total_seconds = int(td.total_seconds())
		hours = total_seconds // 3600
		minutes = (total_seconds % 3600) // 60
		seconds = total_seconds % 60
		return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

	def _get_data_dir(self):
		base = os.path.expanduser("~/Library/Application Support/PomodorUP")
		return base

	def _get_data_path(self):
		return os.path.join(self._get_data_dir(), "pomodorup.json")

	def _load_state(self):
		try:
			data_path = self._get_data_path()
			if not os.path.exists(data_path):
				return
			with open(data_path, "r", encoding="utf-8") as f:
				data = json.load(f)
			# Restore sessions
			sessions = data.get("sessions", [])
			if isinstance(sessions, list):
				self.sessions = sessions
			# Restore recent targets
			recent = data.get("recent_targets_minutes")
			if isinstance(recent, list) and all(isinstance(x, int) for x in recent):
				self.recent_targets_minutes = [max(1, min(99, int(x))) for x in recent][: self.max_recent_targets]
			# Restore target duration
			target_minutes = data.get("target_minutes")
			if isinstance(target_minutes, int):
				target_minutes = max(1, min(99, target_minutes))
				self.target_duration = timedelta(minutes=target_minutes)
			# Restore text display mode
			mode = data.get("text_display_mode")
			valid_modes = {"none", "minutes_elapsed", "minutes_from_target", "minutes_to_target", "minutes_past_target"}
			if isinstance(mode, str) and mode in valid_modes:
				self.text_display_mode = mode
			# Session counter resumes from max existing id
			if self.sessions:
				try:
					self._session_counter = max(int(s.get("id", 0)) for s in self.sessions)
				except Exception:
					self._session_counter = len(self.sessions)
		except Exception:
			# On any error, start fresh without crashing
			pass

	def _save_state(self):
		try:
			data_dir = self._get_data_dir()
			os.makedirs(data_dir, exist_ok=True)
			data_path = self._get_data_path()
			tmp_path = data_path + ".tmp"
			payload = {
				"sessions": self.sessions,
				"recent_targets_minutes": self.recent_targets_minutes,
				"target_minutes": int(self.target_duration.total_seconds() // 60),
				"text_display_mode": self.text_display_mode,
			}
			with open(tmp_path, "w", encoding="utf-8") as f:
				json.dump(payload, f, ensure_ascii=False, indent=2)
			os.replace(tmp_path, data_path)
		except Exception:
			# Best-effort persistence
			pass

	def _compute_text_and_color(self, elapsed):
		"""Return (text, color_rgba_tuple) based on current text display mode and elapsed time."""
		white = (255, 255, 255, 255)
		blue = (0, 122, 255, 255)   # macOS system blue
		green = (52, 199, 89, 255)  # macOS system green
		elapsed_minutes = int(max(0, int(elapsed.total_seconds())) // 60)
		target_minutes = int(self.target_duration.total_seconds() // 60)
		delta = elapsed_minutes - target_minutes
		mode = self.text_display_mode
		if mode == "none":
			return "", white
		if mode == "minutes_elapsed":
			return f"{elapsed_minutes}", white
		if mode == "minutes_from_target":
			abs_delta = abs(delta)
			if delta < 0:
				return f"{abs_delta}", (250, 250, 250, 200) #(196, 183, 255, 255)# blue
			elif delta == 0:
				return f"", (250, 250, 250, 200) # (33, 37, 43, 150) cool dark grey
			else:
				return f"{abs_delta}", (33, 37, 43, 0) #this is dark grey #(100, 253, 179, 255) # green
		if mode == "minutes_to_target":
			if delta >= 0:
				return "", (250, 250, 250, 200) # white
			return f"{abs(-delta)}", white
		if mode == "minutes_past_target":
			if delta <= 0:
				return "",  white
			return f"{delta}", (33, 37, 43, 0) # white
		# Fallback
		return f"{elapsed_minutes}", (250, 250, 250, 200) # white

	def set_text_display_mode(self, mode):
		valid_modes = {"none", "minutes_elapsed", "minutes_from_target", "minutes_to_target", "minutes_past_target"}
		if mode not in valid_modes:
			return
		self.text_display_mode = mode
		self._save_state()
		# Refresh icon immediately
		elapsed = self.get_elapsed_time()
		text, color = self._compute_text_and_color(elapsed)
		self.icon.icon = self.create_icon(text, color)
		self._rebuild_menu()

	def export_statistics(self):
		# Open macOS save dialog and export collected sessions to CSV
		panel = NSSavePanel.savePanel()
		panel.setAllowedFileTypes_(["csv"])
		panel.setCanCreateDirectories_(True)
		panel.setNameFieldStringValue_("pomodorup_stats.csv")
		if panel.runModal() == 1:
			url = panel.URL()
			if url is not None:
				path = url.path()
				try:
					with open(path, "w", newline="", encoding="utf-8") as f:
						writer = csv.writer(f)
						writer.writerow(["Id", "date", "start time", "end time", "target time", "elapsed time"])
						for rec in self.sessions:
							writer.writerow([
								rec["id"],
								rec["date"],
								rec["start"],
								rec["end"],
								rec["target_minutes"],
								rec["elapsed_hms"],
							])
					print(f"Statistics exported to {path}")
				except Exception as e:
					print(f"Failed to export statistics: {e}")
		# Persist after export is optional; we keep state unchanged

	def clear_statistics(self):
		# Clear in-memory sessions and persisted sessions
		self.sessions = []
		self._session_counter = 0
		self._save_state()
		print("Statistics cleared!")
		self._rebuild_menu()

	def show_data_file(self):
		# Open the data directory in Finder
		try:
			data_dir = self._get_data_dir()
			os.makedirs(data_dir, exist_ok=True)
			subprocess.Popen(["open", data_dir])
		except Exception as e:
			print(f"Failed to open data folder: {e}")
		
	def _rebuild_menu(self):
		if self.icon is not None:
			self.icon.menu = self.create_menu()
			self.icon.update_menu()
		
	def _recent_targets_menu_items(self):
		# Build a list of MenuItems for recent targets (skip duplicates, most recent first)
		items = []
		for minutes in self.recent_targets_minutes[: self.max_recent_targets]:
			label = f"{minutes} Minutes"
			# Create a proper closure to capture the minutes value
			def make_handler(m):
				return lambda: self._select_recent_target(m)
			items.append(pystray.MenuItem(label, make_handler(minutes)))
		return items
		
	def _predefined_durations_menu_items(self):
		# Build a list of MenuItems for predefined durations
		items = []
		for minutes in self.predefined_durations:
			label = f"{minutes} Minutes"
			# Create a proper closure to capture the minutes value
			def make_handler(m):
				return lambda: self._select_recent_target(m)
			items.append(pystray.MenuItem(label, make_handler(minutes)))
		return items
		
	def _select_recent_target(self, minutes):
		self.set_target_minutes(minutes)
		print(f"Target set to {minutes} minutes")

	def set_target_minutes(self, minutes):
		# Normalize and update target + recent list
		minutes = max(1, min(99, int(minutes)))
		self.target_duration = timedelta(minutes=minutes)
		# Update MRU list
		if minutes in self.recent_targets_minutes:
			self.recent_targets_minutes.remove(minutes)
		self.recent_targets_minutes.insert(0, minutes)
		self.recent_targets_minutes = self.recent_targets_minutes[: self.max_recent_targets]
		
		# Update icon to show target duration in red if timer is not running
		if not self.is_running:
			red_color = (242, 38, 89, 255)  # Red from color palette
			self.icon.icon = self.create_icon(str(minutes), red_color)
		# Persist new target and recent list
		self._save_state()
		
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
		if not d.isdigit():
			self._rebuild_menu()
			return
		# Prevent leading zero; allow two digits only
		if len(self._input_buffer) == 0:
			if d == "0":
				self._rebuild_menu()
				return
			self._input_buffer = d
		elif len(self._input_buffer) == 1:
			# Allow second digit (0-9)
			self._input_buffer += d
		# If already two digits, ignore
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
			value = max(1, min(99, value))
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

		# Get current timer information
		elapsed = self.get_elapsed_time()
		elapsed_formatted = self.format_time(elapsed)
		target_minutes = int(self.target_duration.total_seconds() // 60)

		# Target Duration submenu
		recent_items = self._recent_targets_menu_items()
		predefined_items = self._predefined_durations_menu_items()
		target_menu = pystray.Menu(
			pystray.MenuItem("Set Target", self._set_target_menu()),
			pystray.MenuItem("Recent Targets:", None, enabled=False),
			*recent_items,
			pystray.Menu.SEPARATOR,
			pystray.MenuItem("Predefined Durations:", None, enabled=False),
			*predefined_items
		)

		# Text display submenu
		mode = self.text_display_mode
		def checked_factory(name):
			return lambda item: mode == name
		text_display_menu = pystray.Menu(
			pystray.MenuItem("None", lambda: self.set_text_display_mode("none"), checked=checked_factory("none")),
			pystray.MenuItem("Minutes Elapsed", lambda: self.set_text_display_mode("minutes_elapsed"), checked=checked_factory("minutes_elapsed")),
			pystray.MenuItem("Minutes From Target", lambda: self.set_text_display_mode("minutes_from_target"), checked=checked_factory("minutes_from_target")),
			pystray.MenuItem("Minutes To Target", lambda: self.set_text_display_mode("minutes_to_target"), checked=checked_factory("minutes_to_target")),
			pystray.MenuItem("Minutes Past Target", lambda: self.set_text_display_mode("minutes_past_target"), checked=checked_factory("minutes_past_target")),
		)

		# Statistics submenu
		stats_menu = pystray.Menu(
			pystray.MenuItem("Export Statistics", self.export_statistics),
			pystray.MenuItem("Clear Statistics", self.clear_statistics),
			pystray.MenuItem("Show Data File", self.show_data_file),
		)

		menu = pystray.Menu(
			pystray.MenuItem(start_or_resume_label, self.start_timer),
			pystray.MenuItem(pause_label, self.pause_timer),
			pystray.MenuItem("Reset Timer", self.reset_timer),
			pystray.Menu.SEPARATOR,
			pystray.MenuItem("Target Duration", target_menu),
			pystray.MenuItem("Text Display", text_display_menu),
			pystray.MenuItem("Statistics", stats_menu),
			pystray.Menu.SEPARATOR,
			pystray.MenuItem(f"Target: {target_minutes} min", None, enabled=False),
			pystray.MenuItem(f"Elapsed: {elapsed_formatted}", None, enabled=False),
			pystray.Menu.SEPARATOR,
			pystray.MenuItem("Quit", self.quit_app)
		)
		return menu
		
	def run(self):
		# Create initial icon showing target duration in red
		initial_minutes = int(self.target_duration.total_seconds() // 60)
		red_color = (242, 38, 89, 255)  # Red from color palette
		initial_icon = self.create_icon(str(initial_minutes), red_color)
		
		# Create the system tray icon
		self.icon = pystray.Icon("PomodorUP", initial_icon, "PomodorUP Timer", self.create_menu())
		
		# Run the app
		self.icon.run()

	def _get_font(self, size, bold=False, monospace=False):
		"""Try to load the Roadrage font first, then fallback to system fonts.
		Priority: Roadrage > monospace+bold > monospace > bold > default
		"""
		# First, try to load the Custom font from assets
		try:
			# Handle both development and PyInstaller bundled scenarios
			if getattr(sys, 'frozen', False):
				# Running from PyInstaller bundle
				bundle_dir = sys._MEIPASS
				font_path = os.path.join(bundle_dir, "assets/fonts", "Doto-VariableFont_ROND,wght.ttf")
			else:
				# Running from source
				script_dir = os.path.dirname(os.path.abspath(__file__))
				font_path = os.path.join(script_dir, "assets/fonts/Doto/static", "Doto_Rounded-ExtraBold.ttf")
			
			if os.path.exists(font_path):
				return ImageFont.truetype(font_path, size)
		except Exception:
			pass
		
		# Fallback to system fonts if Roadrage is not available
		if monospace and bold:
			# Try monospace bold fonts first
			for path in [
				"/System/Library/Fonts/Menlo.ttc",  # Menlo Bold
				"/System/Library/Fonts/Monaco.ttf",  # Monaco Bold
				"/System/Applications/Utilities/Terminal.app/Contents/Resources/Fonts/SFMono-Bold.ttf",
			]:
				try:
					return ImageFont.truetype(path, size)
				except Exception:
					continue
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
