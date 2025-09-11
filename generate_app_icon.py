import os
import subprocess
from PIL import Image, ImageDraw, ImageFont


def hex_to_rgba_tuple(h: str):
	r = int(h[1:3], 16)
	g = int(h[3:5], 16)
	b = int(h[5:7], 16)
	a = int(h[7:9], 16)
	return (r, g, b, a)


def render_icon_base(size: int = 1024) -> Image.Image:
	"""Render the circular banded icon in the 'end of first loop' state.

	This mirrors the visual style used by the tray icon bands but at high resolution.
	The state is the end of the first loop: six horizontal bands bottom->top with the
	palette colors, full opacity, and a thin dark red outline.
	"""
	image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
	draw = ImageDraw.Draw(image)

	margin = int(size * 0.03)
	circle_bbox = [margin, margin, size - margin, size - margin]
	inner_width = circle_bbox[2] - circle_bbox[0]
	inner_height = circle_bbox[3] - circle_bbox[1]

	band_colors_hex = [
		"#5E46D2FF",  # dark_purple
		"#8130C2FF",  # mauve
		"#A5268CFF",  # fuschia
		"#F22659FF",  # red
		"#FF663FFF",  # orange
		"#F2CC3FFF",  # yellow
	]
	base_colors = [hex_to_rgba_tuple(h) for h in band_colors_hex]

	# Mask for the circle
	circle_mask = Image.new("L", (size, size), 0)
	mask_draw = ImageDraw.Draw(circle_mask)
	mask_draw.ellipse(circle_bbox, fill=255)

	# Draw six bands from bottom to top
	bands_image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
	b_draw = ImageDraw.Draw(bands_image)
	band_height = inner_height // 6
	for idx, (r, g, b, a) in enumerate(base_colors):
		band_top = circle_bbox[1] + inner_height - (idx + 1) * band_height
		band_bottom = band_top + band_height
		b_draw.rectangle([circle_bbox[0], band_top, circle_bbox[2], band_bottom], fill=(r, g, b, a))

	# Composite into circle
	image = Image.composite(bands_image, image, circle_mask)
	draw = ImageDraw.Draw(image)

	# Outline
	draw.ellipse(circle_bbox, outline=(139, 0, 0, 0), width=max(0, size // 256))

	return image


def draw_infinity(image: Image.Image):
	"""Draw a centered infinity symbol in white with subtle shadow, monospace/bold style."""
	draw = ImageDraw.Draw(image)
	w, h = image.size

	# Choose font
	def try_fonts(paths):
		for p in paths:
			try:
				return ImageFont.truetype(p, size)
			except Exception:
				continue
		return ImageFont.load_default()

	# Scale font size relative to image size to match tray feel
	size = int(w * 1.1)
	font = None
	# Prefer SF Mono or Menlo for consistent aesthetics
	for path in [
		"/System/Applications/Utilities/Terminal.app/Contents/Resources/Fonts/SFMono-Bold.ttf",
		"/System/Library/Fonts/Menlo.ttc",
		"/System/Library/Fonts/Monaco.ttf",
		"/System/Library/Fonts/Supplemental/Arial Bold.ttf",
	]:
		try:
			font = ImageFont.truetype(path, size)
			break
		except Exception:
			continue
	if font is None:
		font = ImageFont.load_default()

	text = "∞"
	bbox = draw.textbbox((0, 0), text, font=font, anchor="lt")
	text_w = (bbox[2] - bbox[0])
	text_h = (bbox[3] - bbox[1])
	cx = w // 2
	cy = h // 2
	x = cx - text_w // 2
	y = (cy - text_h // 2) - 415

	# Shadow
	#shadow_offset = max(2, w // 256)
	#draw.text((x + shadow_offset, y + shadow_offset), text, fill=(0, 0, 0, 180), font=font)
	# Foreground
	draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)

	return image


def ensure_iconset_dir(iconset_path: str):
	os.makedirs(iconset_path, exist_ok=True)


def save_iconset_images(base_image: Image.Image, iconset_path: str):
	# Apple recommended sizes
	sizes = [
		(16, 1), (16, 2),
		(32, 1), (32, 2),
		(64, 1), (64, 2),
		(128, 1), (128, 2),
		(256, 1), (256, 2),
		(512, 1), (512, 2),
	]
	for pts, scale in sizes:
		px = pts * scale
		resized = base_image.resize((px, px), Image.Resampling.LANCZOS)
		filename = f"icon_{pts}x{pts}{'@2x' if scale == 2 else ''}.png"
		resized.save(os.path.join(iconset_path, filename), format="PNG")


def compile_icns(iconset_path: str, icns_path: str):
	# Use iconutil if available
	try:
		subprocess.run([
			"iconutil", "-c", "icns", iconset_path, "-o", icns_path
		], check=True)
	except Exception as e:
		raise RuntimeError("Failed to run iconutil. Is Xcode command line tools installed?") from e


def main():
	project_root = os.path.dirname(os.path.abspath(__file__))
	output_dir = os.path.join(project_root, "assets")
	os.makedirs(output_dir, exist_ok=True)

	# Render base and glyph
	base = render_icon_base(1024)
	final_img = draw_infinity(base)

	# Save source PNG for reference
	source_png = os.path.join(output_dir, "PomodorUP_1024.png")
	final_img.save(source_png, format="PNG")

	# Build iconset
	iconset_path = os.path.join(output_dir, "PomodorUP.iconset")
	ensure_iconset_dir(iconset_path)
	save_iconset_images(final_img, iconset_path)

	# Compile .icns
	icns_path = os.path.join(output_dir, "PomodorUP.icns")
	compile_icns(iconset_path, icns_path)
	print(f"Wrote {icns_path}")


if __name__ == "__main__":
	main()


