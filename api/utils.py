from .config import logger
from io import BytesIO  
from PIL import Image, ExifTags   # for metadata
# Helper: extract EXIF metadata
def extract_metadata(file_bytes):
    try:
        img = Image.open(BytesIO(file_bytes))
        exif_data = img._getexif()
        if not exif_data:
            return {}
        metadata = {}
        for tag_id, value in exif_data.items():
            tag = ExifTags.TAGS.get(tag_id, tag_id)
            if isinstance(value, bytes):
                try:
                    value = value.decode()
                except Exception:
                    value = str(value)
            metadata[tag] = value
        return metadata
    except Exception as e:
        logger.warning("No metadata extracted: %s", str(e))
        return {}
