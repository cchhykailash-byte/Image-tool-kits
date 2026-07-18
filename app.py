"""
Image Toolkit -- All-in-One Image Utility App
------------------------------------------------
A single Streamlit app bundling the most common everyday image tools:

    1. Background Remover
    2. Resize
    3. Compress
    4. JPG <-> PNG Converter
    5. WebP Converter
    6. Watermark (text or logo)
    7. Crop (interactive, with aspect-ratio presets)
    8. Rotate / Flip
    9. Passport Photo Maker (with print sheet)

Run with:
    streamlit run image_toolkit_app.py

Dependencies:
    pip install streamlit pillow rembg streamlit-cropper numpy

Note: the very first time you use "Background Remover" or "Passport
Photo Maker" (background removal option), rembg downloads a small AI
model file in the background -- this needs an internet connection and
may take a few seconds to a minute depending on your connection.
"""

import io
from datetime import datetime

import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance

try:
    from streamlit_cropper import st_cropper
    CROPPER_AVAILABLE = True
except ImportError:
    CROPPER_AVAILABLE = False

try:
    from rembg import remove as rembg_remove, new_session as rembg_new_session
    REMBG_AVAILABLE = True
except ImportError:
    REMBG_AVAILABLE = False


# ----------------------------------------------------------------------
# Page configuration
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="Image Toolkit",
    page_icon="🛠️",
    layout="wide",
)

BRAND_FOOTER = "Powered by Kailash Chaudhary"

TOOLS = [
    "🏠 Home",
    "✂️ Background Remover",
    "📐 Resize",
    "🗜️ Compress",
    "🔄 JPG ↔ PNG",
    "🌐 WebP Converter",
    "💧 Watermark",
    "✂️ Crop",
    "🔃 Rotate / Flip",
    "🪪 Passport Photo Maker",
]

PASSPORT_SIZES_MM = {
    "Nepal (3.5 x 4.5 cm)": (35, 45),
    "India (3.5 x 4.5 cm)": (35, 45),
    "USA (2 x 2 in)": (50.8, 50.8),
    "UK / Schengen (3.5 x 4.5 cm)": (35, 45),
    "Canada (5 x 7 cm)": (50, 70),
    "Australia (3.5 x 4.5 cm)": (35, 45),
    "China (3.3 x 4.8 cm)": (33, 48),
}

PRINT_SHEET_SIZES_IN = {
    "4 x 6 in (standard photo print)": (4, 6),
    "5 x 7 in": (5, 7),
    "A4 (8.27 x 11.69 in)": (8.27, 11.69),
}


# ----------------------------------------------------------------------
# Font helper (robust across OSes)
# ----------------------------------------------------------------------
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
    "DejaVuSans-Bold.ttf",
]


@st.cache_resource(show_spinner=False)
def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# ----------------------------------------------------------------------
# Generic helpers
# ----------------------------------------------------------------------
def load_uploaded_image(uploaded_file) -> Image.Image:
    img = Image.open(uploaded_file)
    img = ImageOps.exif_transpose(img)  # respect camera orientation
    return img


def image_to_bytes(img: Image.Image, fmt: str, quality: int = 95) -> bytes:
    buf = io.BytesIO()
    fmt = fmt.upper()
    save_img = img
    if fmt in ("JPEG", "JPG"):
        fmt = "JPEG"
        if save_img.mode in ("RGBA", "P", "LA"):
            bg = Image.new("RGB", save_img.size, (255, 255, 255))
            rgba = save_img.convert("RGBA")
            bg.paste(rgba, mask=rgba.split()[-1])
            save_img = bg
        else:
            save_img = save_img.convert("RGB")
        save_img.save(buf, format="JPEG", quality=quality, optimize=True)
    elif fmt == "WEBP":
        save_img.save(buf, format="WEBP", quality=quality)
    elif fmt == "PNG":
        save_img.save(buf, format="PNG", optimize=True)
    else:
        save_img.save(buf, format=fmt)
    return buf.getvalue()


def kb_size(data: bytes) -> float:
    return len(data) / 1024


def mm_to_px(mm: float, dpi: int = 300) -> int:
    return round(mm / 25.4 * dpi)


def in_to_px(inches: float, dpi: int = 300) -> int:
    return round(inches * dpi)


def cover_resize_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Resize to fill the target box (like CSS 'object-fit: cover'),
    then center-crop any overflow -- used for passport photos."""
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = round(src_w * scale), round(src_h * scale)
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def compress_to_target(img: Image.Image, target_kb: int, fmt: str = "JPEG"):
    """Step quality (then resolution) down until under target_kb.
    Returns (bytes, quality_used, was_downscaled)."""
    target_bytes = target_kb * 1024
    best = None
    best_q = None
    for quality in (95, 90, 85, 80, 75, 70, 65, 60, 50, 40, 30):
        data = image_to_bytes(img, fmt, quality=quality)
        if best is None or len(data) < len(best):
            best, best_q = data, quality
        if len(data) <= target_bytes:
            return data, quality, False

    working = img
    for scale in (0.85, 0.7, 0.55, 0.4):
        w, h = int(img.width * scale), int(img.height * scale)
        working = img.resize((w, h), Image.LANCZOS)
        for quality in (80, 65, 50, 35):
            data = image_to_bytes(working, fmt, quality=quality)
            if best is None or len(data) < len(best):
                best, best_q = data, quality
            if len(data) <= target_bytes:
                return data, quality, True

    return best, best_q, True


@st.cache_resource(show_spinner=False)
def get_rembg_session(model_name: str):
    return rembg_new_session(model_name)


def remove_background(img: Image.Image, model_name: str = "u2netp") -> Image.Image:
    session = get_rembg_session(model_name)
    buf = io.BytesIO()
    img.convert("RGBA").save(buf, format="PNG")
    result_bytes = rembg_remove(buf.getvalue(), session=session)
    return Image.open(io.BytesIO(result_bytes)).convert("RGBA")


def flatten_on_white(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return img.convert("RGB")


POSITIONS = ["Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right", "Center"]


def _position_xy(canvas_w, canvas_h, elem_w, elem_h, position, pad):
    if position == "Top-Left":
        return pad, pad
    if position == "Top-Right":
        return canvas_w - elem_w - pad, pad
    if position == "Bottom-Left":
        return pad, canvas_h - elem_h - pad
    if position == "Bottom-Right":
        return canvas_w - elem_w - pad, canvas_h - elem_h - pad
    return (canvas_w - elem_w) // 2, (canvas_h - elem_h) // 2


def add_text_watermark(img, text, font_size, color_hex, opacity, position):
    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = load_font(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = max(16, font_size // 2)
    x, y = _position_xy(base.width, base.height, tw, th, position, pad)
    r = int(color_hex.lstrip("#")[0:2], 16)
    g = int(color_hex.lstrip("#")[2:4], 16)
    b = int(color_hex.lstrip("#")[4:6], 16)
    alpha = int(255 * opacity)
    draw.text((x - bbox[0], y - bbox[1]), text, font=font, fill=(r, g, b, alpha))
    return Image.alpha_composite(base, overlay)


def add_logo_watermark(img, logo_img, scale_pct, opacity, position):
    base = img.convert("RGBA")
    logo = logo_img.convert("RGBA")
    target_w = max(20, int(base.width * scale_pct / 100))
    ratio = target_w / logo.width
    logo = logo.resize((target_w, max(1, int(logo.height * ratio))), Image.LANCZOS)

    if opacity < 1.0:
        alpha = logo.split()[-1].point(lambda a: int(a * opacity))
        logo.putalpha(alpha)

    pad = max(16, base.width // 40)
    x, y = _position_xy(base.width, base.height, logo.width, logo.height, position, pad)
    base.paste(logo, (x, y), logo)
    return base


def rotate_image(img, angle, fill_hex="#FFFFFF"):
    fill = tuple(int(fill_hex.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    if img.mode in ("RGBA", "LA"):
        return img.rotate(angle, expand=True, resample=Image.BICUBIC)
    return img.rotate(angle, expand=True, resample=Image.BICUBIC, fillcolor=fill)


def build_print_sheet(photo: Image.Image, sheet_in, dpi, gap_mm=3, margin_mm=8):
    sheet_w = in_to_px(sheet_in[0], dpi)
    sheet_h = in_to_px(sheet_in[1], dpi)
    gap = mm_to_px(gap_mm, dpi)
    margin = mm_to_px(margin_mm, dpi)

    pw, ph = photo.size
    cols = max(1, (sheet_w - 2 * margin + gap) // (pw + gap))
    rows = max(1, (sheet_h - 2 * margin + gap) // (ph + gap))

    sheet = Image.new("RGB", (sheet_w, sheet_h), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)

    count = 0
    for r in range(rows):
        for c in range(cols):
            x = margin + c * (pw + gap)
            y = margin + r * (ph + gap)
            if x + pw > sheet_w - margin or y + ph > sheet_h - margin:
                continue
            sheet.paste(photo.convert("RGB"), (x, y))
            draw.rectangle([x, y, x + pw - 1, y + ph - 1], outline=(180, 180, 180), width=1)
            count += 1
    return sheet, count


# ----------------------------------------------------------------------
# Shared UI bits
# ----------------------------------------------------------------------
def show_footer():
    st.markdown(
        f"<p style='text-align:center; color:gray; font-size:0.8rem; margin-top:2rem;'>{BRAND_FOOTER}</p>",
        unsafe_allow_html=True,
    )


def download_row(items):
    """items: list of (label, data_bytes, filename, mime)"""
    cols = st.columns(len(items))
    for col, (label, data, fname, mime) in zip(cols, items):
        with col:
            st.download_button(label, data=data, file_name=fname, mime=mime, use_container_width=True)


def uploader(label="Upload an image", key=None):
    file = st.file_uploader(label, type=["png", "jpg", "jpeg", "webp", "bmp"], key=key)
    if file is None:
        st.info("⬆️ Upload an image to get started.")
        return None
    try:
        return load_uploaded_image(file)
    except Exception as e:
        st.error(f"Couldn't read that file: {e}")
        return None


def timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ----------------------------------------------------------------------
# Sidebar navigation
# ----------------------------------------------------------------------
st.sidebar.title("🛠️ Image Toolkit")
st.sidebar.caption("Everything related to images, in one place.")
tool = st.sidebar.radio("Choose a tool", TOOLS, label_visibility="collapsed")
st.sidebar.markdown("---")
st.sidebar.markdown(
    f"<p style='color:gray; font-size:0.75rem;'>{BRAND_FOOTER}</p>", unsafe_allow_html=True
)


# ----------------------------------------------------------------------
# HOME
# ----------------------------------------------------------------------
if tool == "🏠 Home":
    st.title("🛠️ Image Toolkit")
    st.write(
        "A complete, all-in-one image utility app. Pick a tool from the "
        "sidebar to get started:"
    )
    cols = st.columns(3)
    descriptions = [
        ("✂️ Background Remover", "Cut out the background from any photo automatically."),
        ("📐 Resize", "Change image dimensions by pixels or percentage."),
        ("🗜️ Compress", "Shrink file size to a target KB with minimal quality loss."),
        ("🔄 JPG ↔ PNG", "Convert freely between JPG and PNG."),
        ("🌐 WebP Converter", "Convert to/from the modern WebP format."),
        ("💧 Watermark", "Stamp a text or logo watermark onto your images."),
        ("✂️ Crop", "Interactively crop with free or fixed aspect ratios."),
        ("🔃 Rotate / Flip", "Rotate by any angle or flip horizontally/vertically."),
        ("🪪 Passport Photo Maker", "Generate correctly-sized passport photos + a printable sheet."),
    ]
    for i, (name, desc) in enumerate(descriptions):
        with cols[i % 3]:
            st.markdown(f"**{name}**")
            st.caption(desc)
    show_footer()


# ----------------------------------------------------------------------
# BACKGROUND REMOVER
# ----------------------------------------------------------------------
elif tool == "✂️ Background Remover":
    st.title("✂️ Background Remover")
    st.caption("Automatically cuts the background out of a photo, leaving it transparent.")

    if not REMBG_AVAILABLE:
        st.error("This feature needs the `rembg` package. Install it with:\n\n`pip install rembg`")
    else:
        img = uploader("Upload a photo")
        if img:
            quality_choice = st.radio(
                "Model", ["Fast (u2netp)", "Accurate (u2net)"], horizontal=True,
                help="Fast is smaller/quicker; Accurate gives cleaner edges but downloads a larger model on first use.",
            )
            model_name = "u2netp" if "Fast" in quality_choice else "u2net"

            replace_bg = st.checkbox("Replace transparent background with a solid color")
            bg_color = st.color_picker("Background color", "#FFFFFF") if replace_bg else None

            if st.button("Remove Background", type="primary", use_container_width=True):
                with st.spinner("Removing background... (first run may download a model file)"):
                    result = remove_background(img, model_name)
                    if replace_bg:
                        solid = Image.new("RGBA", result.size, tuple(
                            int(bg_color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)
                        ) + (255,))
                        solid.paste(result, (0, 0), result)
                        result = solid

                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Original**")
                        st.image(img, use_container_width=True)
                    with col2:
                        st.markdown("**Background removed**")
                        st.image(result, use_container_width=True)

                    png_bytes = image_to_bytes(result, "PNG")
                    download_row([
                        ("⬇️ Download PNG", png_bytes, f"no_bg_{timestamp()}.png", "image/png"),
                    ])
    show_footer()


# ----------------------------------------------------------------------
# RESIZE
# ----------------------------------------------------------------------
elif tool == "📐 Resize":
    st.title("📐 Resize")
    st.caption("Change image dimensions by exact pixels or by percentage.")

    img = uploader("Upload an image")
    if img:
        st.write(f"Original size: **{img.width} × {img.height} px**")
        mode = st.radio("Resize by", ["Pixels", "Percentage"], horizontal=True)
        keep_ratio = st.checkbox("Maintain aspect ratio", value=True)

        if mode == "Pixels":
            c1, c2 = st.columns(2)
            with c1:
                new_w = st.number_input("Width (px)", min_value=1, value=img.width, step=1)
            with c2:
                if keep_ratio:
                    new_h = round(new_w * img.height / img.width)
                    st.number_input("Height (px)", value=new_h, disabled=True, step=1)
                else:
                    new_h = st.number_input("Height (px)", min_value=1, value=img.height, step=1)
        else:
            pct = st.slider("Scale (%)", min_value=1, max_value=400, value=100)
            new_w = max(1, round(img.width * pct / 100))
            new_h = max(1, round(img.height * pct / 100))
            st.write(f"New size: **{new_w} × {new_h} px**")

        if st.button("Resize", type="primary", use_container_width=True):
            resized = img.resize((int(new_w), int(new_h)), Image.LANCZOS)
            st.image(resized, caption=f"{new_w} × {new_h} px", use_container_width=False)

            out_fmt = "PNG" if img.mode in ("RGBA", "P", "LA") else "JPEG"
            data = image_to_bytes(resized, out_fmt, quality=95)
            ext = "png" if out_fmt == "PNG" else "jpg"
            download_row([
                (f"⬇️ Download {out_fmt}", data, f"resized_{timestamp()}.{ext}", f"image/{ext}"),
            ])
    show_footer()


# ----------------------------------------------------------------------
# COMPRESS
# ----------------------------------------------------------------------
elif tool == "🗜️ Compress":
    st.title("🗜️ Compress")
    st.caption("Shrink file size to a target KB, automatically balancing quality.")

    img = uploader("Upload an image")
    if img:
        original_bytes = image_to_bytes(img, "JPEG", quality=95)
        st.write(f"Original approx. size: **{kb_size(original_bytes):.1f} KB**")

        target_kb = st.slider("Target size (KB)", min_value=10, max_value=2000, value=150, step=10)
        fmt = st.radio("Output format", ["JPEG", "PNG", "WEBP"], horizontal=True)

        if st.button("Compress", type="primary", use_container_width=True):
            with st.spinner("Compressing..."):
                data, quality_used, downscaled = compress_to_target(img, target_kb, fmt)
            st.success(
                f"✅ Compressed to **{kb_size(data):.1f} KB** "
                f"(quality {quality_used}{', image was also downscaled' if downscaled else ''})"
            )
            st.image(data, use_container_width=False, width=350)
            ext = fmt.lower().replace("jpeg", "jpg")
            download_row([
                (f"⬇️ Download {fmt}", data, f"compressed_{timestamp()}.{ext}", f"image/{fmt.lower()}"),
            ])
    show_footer()


# ----------------------------------------------------------------------
# JPG <-> PNG
# ----------------------------------------------------------------------
elif tool == "🔄 JPG ↔ PNG":
    st.title("🔄 JPG ↔ PNG Converter")
    st.caption("Convert freely between JPG and PNG formats.")

    img = uploader("Upload a JPG or PNG image")
    if img:
        target = st.radio("Convert to", ["PNG", "JPG"], horizontal=True)
        if target == "JPG" and img.mode in ("RGBA", "LA", "P"):
            st.info("This image has transparency -- it will be flattened onto a white background for JPG.")

        if st.button("Convert", type="primary", use_container_width=True):
            data = image_to_bytes(img, "JPEG" if target == "JPG" else "PNG", quality=95)
            st.image(data, use_container_width=False, width=350)
            ext = "jpg" if target == "JPG" else "png"
            download_row([
                (f"⬇️ Download {target}", data, f"converted_{timestamp()}.{ext}", f"image/{ext}"),
            ])
    show_footer()


# ----------------------------------------------------------------------
# WEBP CONVERTER
# ----------------------------------------------------------------------
elif tool == "🌐 WebP Converter":
    st.title("🌐 WebP Converter")
    st.caption("Convert any image to WebP, or convert a WebP image to JPG/PNG.")

    img = uploader("Upload an image (any format, including WebP)")
    if img:
        is_webp = getattr(img, "format", "") == "WEBP"
        if is_webp:
            target = st.radio("Convert to", ["JPG", "PNG"], horizontal=True)
        else:
            target = "WEBP"
            quality = st.slider("WebP quality", min_value=10, max_value=100, value=85)

        if st.button("Convert", type="primary", use_container_width=True):
            if target == "WEBP":
                data = image_to_bytes(img, "WEBP", quality=quality)
                ext, mime = "webp", "image/webp"
            else:
                data = image_to_bytes(img, "JPEG" if target == "JPG" else "PNG", quality=95)
                ext, mime = ("jpg", "image/jpeg") if target == "JPG" else ("png", "image/png")

            st.image(data, use_container_width=False, width=350)
            st.write(f"Output size: **{kb_size(data):.1f} KB**")
            download_row([(f"⬇️ Download {target}", data, f"converted_{timestamp()}.{ext}", mime)])
    show_footer()


# ----------------------------------------------------------------------
# WATERMARK
# ----------------------------------------------------------------------
elif tool == "💧 Watermark":
    st.title("💧 Watermark")
    st.caption("Stamp a text or logo watermark onto your image.")

    img = uploader("Upload an image")
    if img:
        wtype = st.radio("Watermark type", ["Text", "Logo image"], horizontal=True)
        position = st.selectbox("Position", POSITIONS, index=3)
        opacity = st.slider("Opacity", min_value=0.1, max_value=1.0, value=0.6, step=0.05)

        result = None
        if wtype == "Text":
            text = st.text_input("Watermark text", value="© Your Name")
            c1, c2 = st.columns(2)
            with c1:
                font_size = st.slider("Font size", min_value=12, max_value=120, value=36)
            with c2:
                color = st.color_picker("Text color", "#FFFFFF")

            if st.button("Apply Watermark", type="primary", use_container_width=True) and text.strip():
                result = add_text_watermark(img, text, font_size, color, opacity, position)
        else:
            logo_file = st.file_uploader("Upload logo (PNG with transparency recommended)", type=["png", "jpg", "jpeg"])
            scale_pct = st.slider("Logo size (% of image width)", min_value=5, max_value=50, value=15)
            if st.button("Apply Watermark", type="primary", use_container_width=True) and logo_file:
                logo_img = Image.open(logo_file)
                result = add_logo_watermark(img, logo_img, scale_pct, opacity, position)

        if result is not None:
            st.image(result, use_container_width=True)
            out_fmt = "PNG" if img.mode in ("RGBA", "P") else "JPEG"
            data = image_to_bytes(result, out_fmt, quality=95)
            ext = "png" if out_fmt == "PNG" else "jpg"
            download_row([
                (f"⬇️ Download {out_fmt}", data, f"watermarked_{timestamp()}.{ext}", f"image/{ext}"),
            ])
    show_footer()


# ----------------------------------------------------------------------
# CROP
# ----------------------------------------------------------------------
elif tool == "✂️ Crop":
    st.title("✂️ Crop")
    st.caption("Drag to select the area you want, then crop.")

    img = uploader("Upload an image")
    if img:
        if not CROPPER_AVAILABLE:
            st.error("This feature needs `streamlit-cropper`. Install it with:\n\n`pip install streamlit-cropper`")
        else:
            ratio_choice = st.selectbox(
                "Aspect ratio", ["Free", "1:1 (Square)", "4:3", "3:4", "16:9", "3:2"]
            )
            ratio_map = {
                "Free": None, "1:1 (Square)": (1, 1), "4:3": (4, 3),
                "3:4": (3, 4), "16:9": (16, 9), "3:2": (3, 2),
            }
            display_img = img.convert("RGB") if img.mode not in ("RGB", "RGBA") else img
            cropped = st_cropper(
                display_img,
                realtime_update=True,
                box_color="#0B5FFF",
                aspect_ratio=ratio_map[ratio_choice],
                return_type="image",
            )
            st.markdown("**Preview**")
            st.image(cropped, use_container_width=False, width=350)

            out_fmt = "PNG" if img.mode in ("RGBA", "P") else "JPEG"
            data = image_to_bytes(cropped, out_fmt, quality=95)
            ext = "png" if out_fmt == "PNG" else "jpg"
            download_row([
                (f"⬇️ Download {out_fmt}", data, f"cropped_{timestamp()}.{ext}", f"image/{ext}"),
            ])
    show_footer()


# ----------------------------------------------------------------------
# ROTATE / FLIP
# ----------------------------------------------------------------------
elif tool == "🔃 Rotate / Flip":
    st.title("🔃 Rotate / Flip")
    st.caption("Rotate by 90° steps or a custom angle, or flip horizontally/vertically.")

    img = uploader("Upload an image")
    if img:
        st.markdown("**Quick actions**")
        qc1, qc2, qc3, qc4 = st.columns(4)
        quick_result = None
        if qc1.button("↩️ Rotate 90° Left", use_container_width=True):
            quick_result = img.rotate(90, expand=True)
        if qc2.button("↪️ Rotate 90° Right", use_container_width=True):
            quick_result = img.rotate(-90, expand=True)
        if qc3.button("↔️ Flip Horizontal", use_container_width=True):
            quick_result = ImageOps.mirror(img)
        if qc4.button("↕️ Flip Vertical", use_container_width=True):
            quick_result = ImageOps.flip(img)

        st.markdown("**Custom angle**")
        angle = st.slider("Angle (degrees)", min_value=-180, max_value=180, value=0)
        fill_color = st.color_picker("Background fill (for non-90° angles)", "#FFFFFF")
        custom_result = None
        if st.button("Apply Custom Rotation", use_container_width=True):
            custom_result = rotate_image(img, angle, fill_color)

        result = quick_result if quick_result is not None else custom_result
        if result is not None:
            st.image(result, use_container_width=False, width=400)
            out_fmt = "PNG" if img.mode in ("RGBA", "P") else "JPEG"
            data = image_to_bytes(result, out_fmt, quality=95)
            ext = "png" if out_fmt == "PNG" else "jpg"
            download_row([
                (f"⬇️ Download {out_fmt}", data, f"rotated_{timestamp()}.{ext}", f"image/{ext}"),
            ])
    show_footer()


# ----------------------------------------------------------------------
# PASSPORT PHOTO MAKER
# ----------------------------------------------------------------------
elif tool == "🪪 Passport Photo Maker":
    st.title("🪪 Passport Photo Maker")
    st.caption("Crop and resize your photo to an official passport size, then generate a printable sheet.")

    img = uploader("Upload a portrait photo (front-facing, plain background works best)")
    if img:
        size_choice = st.selectbox("Country / size preset", list(PASSPORT_SIZES_MM.keys()))
        w_mm, h_mm = PASSPORT_SIZES_MM[size_choice]
        dpi = st.select_slider("Print quality (DPI)", options=[150, 200, 300, 600], value=300)

        white_bg = False
        if REMBG_AVAILABLE:
            white_bg = st.checkbox("Remove & replace background with white", value=False)
        else:
            st.caption("ℹ️ Install `rembg` to enable automatic white-background replacement.")

        if not CROPPER_AVAILABLE:
            st.warning("Install `streamlit-cropper` for manual face framing. Using auto center-crop instead.")

        target_w, target_h = mm_to_px(w_mm, dpi), mm_to_px(h_mm, dpi)
        st.write(f"Target size: **{w_mm}×{h_mm} mm** → **{target_w}×{target_h} px** at {dpi} DPI")

        working_img = img
        if white_bg and REMBG_AVAILABLE:
            with st.spinner("Removing background..."):
                cutout = remove_background(img, "u2netp")
                solid = Image.new("RGBA", cutout.size, (255, 255, 255, 255))
                solid.paste(cutout, (0, 0), cutout)
                working_img = solid.convert("RGB")

        if CROPPER_AVAILABLE:
            st.markdown("**Frame your face inside the box** (matches the passport aspect ratio)")
            display_img = working_img.convert("RGB")
            face_crop = st_cropper(
                display_img,
                realtime_update=True,
                box_color="#0B5FFF",
                aspect_ratio=(w_mm, h_mm),
                return_type="image",
            )
            final_photo = face_crop.resize((target_w, target_h), Image.LANCZOS)
        else:
            final_photo = cover_resize_crop(working_img.convert("RGB"), target_w, target_h)

        st.markdown("**Passport photo preview**")
        st.image(final_photo, width=180)

        single_data = image_to_bytes(final_photo, "JPEG", quality=95)
        download_row([
            ("⬇️ Download Single Photo", single_data, f"passport_photo_{timestamp()}.jpg", "image/jpeg"),
        ])

        st.markdown("---")
        st.markdown("**Printable sheet (multiple copies on one page)**")
        sheet_choice = st.selectbox("Sheet size", list(PRINT_SHEET_SIZES_IN.keys()))
        if st.button("Generate Print Sheet", type="primary", use_container_width=True):
            sheet, count = build_print_sheet(final_photo, PRINT_SHEET_SIZES_IN[sheet_choice], dpi)
            st.success(f"✅ Fit {count} copies on the sheet.")
            st.image(sheet, use_container_width=True)
            sheet_data = image_to_bytes(sheet, "JPEG", quality=95)
            download_row([
                ("⬇️ Download Print Sheet", sheet_data, f"passport_sheet_{timestamp()}.jpg", "image/jpeg"),
            ])
    show_footer()