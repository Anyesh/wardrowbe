from typing import Annotated

from pydantic import AfterValidator

from app.utils.garment_vocabulary import canonical_colors, canonical_primary_color

# A blank name clears the colour rather than storing an empty string no swatch or filter can use.
ColorName = Annotated[str, AfterValidator(canonical_primary_color)]
ColorList = Annotated[list[str], AfterValidator(canonical_colors)]
