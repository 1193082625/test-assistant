from app.config import COVER_IMAGE_HEIGHT, COVER_IMAGE_WIDTH


def cover_canvas() -> tuple[int, int]:
    return COVER_IMAGE_WIDTH, COVER_IMAGE_HEIGHT


def cover_ratio() -> float:
    return COVER_IMAGE_WIDTH / COVER_IMAGE_HEIGHT
