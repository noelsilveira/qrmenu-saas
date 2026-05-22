import os
import uuid
import io
from datetime import datetime, timedelta
from typing import Optional

import qrcode
import qrcode.image.svg
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
from PIL import Image, ImageDraw, ImageFont

from app.core.config import settings

QR_STORAGE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static", "qr")
os.makedirs(QR_STORAGE_PATH, exist_ok=True)

BASE_MENU_URL = os.getenv("BASE_MENU_URL", "https://menu.saas.com/go")


def _hex_to_rgb(hex_color: str):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def generate_qr_url(qr_token: str, merchant_slug: str, table_number: str, order_type: str = "dine_in") -> str:
    return (
        f"{BASE_MENU_URL}?t={qr_token}&m={merchant_slug}"
        f"&type={order_type}&table={table_number}"
    )


def _draw_branded_frame(
    img: Image.Image,
    table_number: str,
    merchant_name: str,
    primary_color: str,
    secondary_color: str,
    logo_path: Optional[str] = None,
) -> Image.Image:
    """Overlay branded frame with table number and optional logo."""
    qr_size = img.size[0]
    frame_padding = 40
    top_banner_height = 60
    bottom_banner_height = 50
    new_size = (qr_size + frame_padding * 2, qr_size + frame_padding * 2 + top_banner_height + bottom_banner_height)

    primary_rgb = _hex_to_rgb(primary_color)
    secondary_rgb = _hex_to_rgb(secondary_color)

    canvas = Image.new("RGB", new_size, secondary_rgb)
    draw = ImageDraw.Draw(canvas)

    # Top banner with merchant name
    draw.rectangle([0, 0, new_size[0], top_banner_height], fill=primary_rgb)

    # Try to use a font, fallback to default
    try:
        font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
        font_table = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
    except Exception:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_table = ImageFont.load_default()

    # Merchant name centered
    name_text = merchant_name[:25]
    bbox = draw.textbbox((0, 0), name_text, font=font_large)
    text_w = bbox[2] - bbox[0]
    draw.text(((new_size[0] - text_w) // 2, 16), name_text, fill="white", font=font_large)

    # Place QR code
    canvas.paste(img, (frame_padding, top_banner_height + frame_padding // 2))

    # Bottom banner with table number
    bottom_y = new_size[1] - bottom_banner_height
    draw.rectangle([0, bottom_y, new_size[0], new_size[1]], fill=primary_rgb)

    table_text = f"Table {table_number}"
    bbox = draw.textbbox((0, 0), table_text, font=font_table)
    text_w = bbox[2] - bbox[0]
    draw.text(((new_size[0] - text_w) // 2, bottom_y + 8), table_text, fill="white", font=font_table)

    # Optional logo in center of QR
    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo_size = qr_size // 5
            logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
            logo_pos = (
                frame_padding + (qr_size - logo_size) // 2,
                top_banner_height + frame_padding // 2 + (qr_size - logo_size) // 2,
            )
            # Create white circle background for logo
            mask = Image.new("L", (logo_size, logo_size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse([0, 0, logo_size, logo_size], fill=255)
            canvas.paste(logo, logo_pos, logo)
        except Exception:
            pass

    return canvas


def generate_qr_image(
    qr_token: str,
    merchant_slug: str,
    table_number: str,
    merchant_name: str = "Menu",
    primary_color: str = "#3B82F6",
    secondary_color: str = "#F3F4F6",
    logo_path: Optional[str] = None,
    fmt: str = "png",
) -> tuple[bytes, str]:
    """Generate branded QR image. Returns (bytes, filename)."""
    url = generate_qr_url(qr_token, merchant_slug, table_number)
    filename = f"{qr_token}_{fmt}.{fmt}"

    if fmt.lower() == "svg":
        factory = qrcode.image.svg.SvgImage
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
            image_factory=factory,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color=primary_color, back_color=secondary_color)
        buf = io.BytesIO()
        img.save(buf)
        return buf.getvalue(), filename

    # PNG with branded frame
    qr = qrcode.QRCode(
        version=3,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color=primary_color, back_color="white").convert("RGB")

    branded = _draw_branded_frame(
        qr_img,
        table_number=table_number,
        merchant_name=merchant_name,
        primary_color=primary_color,
        secondary_color=secondary_color,
        logo_path=logo_path,
    )

    buf = io.BytesIO()
    branded.save(buf, format="PNG")
    return buf.getvalue(), filename


def save_qr_file(data: bytes, filename: str) -> str:
    filepath = os.path.join(QR_STORAGE_PATH, filename)
    with open(filepath, "wb") as f:
        f.write(data)
    return f"/static/qr/{filename}"


def get_qr_file_path(filename: str) -> str:
    return os.path.join(QR_STORAGE_PATH, filename)


def rotate_qr_token() -> str:
    return uuid.uuid4().hex
