"""Validated, bounded image API inputs. Callers never supply workflow graphs."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FileId = str

class ImageOptions(BaseModel):
    model_config=ConfigDict(extra='forbid', strict=True)
    prompt: str = Field(min_length=1,max_length=4000)
    size: str = '1024x1024'
    seed: int = Field(default=0,ge=0,le=2**53-1)
    quality: Literal['fast','standard','high'] = 'standard'
    image_ids: list[str] = Field(default_factory=list,max_length=3)
    foreground_file_id: str | None = None
    title: str = Field(default='',max_length=60)

    @field_validator('prompt')
    @classmethod
    def nonempty(cls,value):
        if not value.strip(): raise ValueError('Prompt cannot be blank')
        return value

    @field_validator('size')
    @classmethod
    def bounded_size(cls,value):
        if value not in ('1024x1024','1152x896','896x1152','1280x768','768x1280'):
            raise ValueError('Supported sizes: 1024x1024,1152x896,896x1152,1280x768,768x1280')
        return value

    @field_validator('image_ids','foreground_file_id')
    @classmethod
    def local_files(cls,value):
        import re
        for fid in value if isinstance(value,list) else [value] if value else []:
            if not re.fullmatch(r'file-[a-f0-9]{32}',fid): raise ValueError('Use uploaded file IDs')
        return value

    @model_validator(mode='after')
    def distinct_edit_or_composite(self):
        if self.image_ids and self.foreground_file_id:
            raise ValueError('Choose image editing or transparent foreground composition')
        return self

class ImageGenerationBody(ImageOptions):
    model: Literal['spark-image'] = 'spark-image'
    n: Literal[1] = 1
    response_format: Literal['b64_json'] = 'b64_json'
