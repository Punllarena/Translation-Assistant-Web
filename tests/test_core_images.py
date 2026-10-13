import io
import os

from PIL import Image

from api.core.images import shrink_image


def encode(img, fmt):
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


def test_small_images_are_returned_as_is():
    data = encode(Image.new("RGB", (10, 10)), "PNG")
    assert shrink_image(data) is data


def test_undecodable_data_is_returned_as_is():
    data = b"not an image" * 40_000
    assert shrink_image(data) is data


def test_a_big_image_becomes_a_smaller_jpeg_within_1600px():
    noise = Image.frombytes("RGB", (2400, 1800), os.urandom(2400 * 1800 * 3))
    data = encode(noise, "PNG")
    out = shrink_image(data)
    assert out[:2] == b"\xff\xd8" and len(out) < len(data)
    assert max(Image.open(io.BytesIO(out)).size) <= 1600


def test_alpha_png_converts_to_jpeg():
    rgba = Image.frombytes("RGBA", (1200, 1200), os.urandom(1200 * 1200 * 4))
    out = shrink_image(encode(rgba, "PNG"))
    assert Image.open(io.BytesIO(out)).mode == "RGB"


def test_a_decompression_bomb_is_returned_as_is(monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)  # anything over 2000 px raises
    data = encode(Image.frombytes("RGB", (800, 800), os.urandom(800 * 800 * 3)), "PNG")
    assert shrink_image(data) is data
