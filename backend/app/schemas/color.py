from typing import Annotated

from pydantic import AfterValidator

from app.utils.garment_vocabulary import canonical_color, canonical_colors

ColorName = Annotated[str, AfterValidator(canonical_color)]
ColorList = Annotated[list[str], AfterValidator(canonical_colors)]
