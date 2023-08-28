# -*- coding: utf-8 -*-
"""
Created on Fri May 13 13:17:30 2022

@author: kaf
"""
import re
import os

from typing import List, Dict, Any
from enum import Enum
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import spacy
from spacy.tokens import Doc, Span
from spacy import displacy


class ModelName(str, Enum):
    """Enum of the available models. This allows the API to raise a more specific
    error if an invalid model is provided.
    """
    ner_french = r"socsec_ner_fr"  # pylint: disable=invalid-name
    ner_dutch = r"socsec_ner_nl"  # pylint: disable=invalid-name

__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__), 'models'))

# TODO: Move following in __init__ of ModelName
print(__location__)
DEFAULT_MODEL = ModelName.ner_dutch
MODEL_NAMES = [model.value for model in ModelName]
MODELS = {name: spacy.load(os.path.join(__location__, name)) for name in MODEL_NAMES}

print(f"Loaded {len(MODEL_NAMES)} models: {MODEL_NAMES}")

class Text(BaseModel):
    """Schema for a single text in a batch of texts to process
    """
    content: str

class InputModel(BaseModel):
    """Schema for the text to process
    """
    texts: List[Text]
    model: ModelName = DEFAULT_MODEL

class Entity(BaseModel):
    """Schema for a single entity
    """
    text: str
    label: str
    start: int
    end: int
    person_title: str
    company_legal_form: str

class ResponseModel(BaseModel):
    """Schema of the expected response for a batch of processed texts
    """
    class Batch(BaseModel):
        """SSchema of the response for a single processed text
        """
        text: str
        entities: List[Entity] = []
        html: str
    result: List[Batch]


# Disambiguate entity "PERSON": actual person or company?
# Check for person title and company legal form abbreviation
def get_person_title(span: Span) -> Any:
    """Check for a person title in the extracted entity 
    or in the previous token.
    """
    # cSpell:disable #
    title_list = ["mr", "mr.", "monsieur", "messieurs", "m", "m.",
                  "madame", "mme", "mmes", "mesdames", "me", "maître", "meester"
                  "mevrouw", "meneer", "mevr.", "mw.", "heer", "heren", "dhr.", "dr." ]
    person_title = ""
    if span.label_ == "PERSON":
        # Check if the person title is in the entity span
        search_obj = re.search( f'^({"|".join(title_list)})\s', span.text, re.I)
        if search_obj:
            person_title = search_obj[0].lower()
        # Check if the person title is at the left of the entity span
        elif span.start != 0:
            prev_token = span.doc[span.start - 1]
            person_title = prev_token.lower_ if prev_token.lower_ in (title_list) else ""
    return person_title

Span.set_extension("person_title", getter=get_person_title, force=True)

def get_legal_form(span: Span) -> Any:
    """Check for a company legal form abbreviation in the extracted entity
    or in the vicinity of the entity.
    """
    legal_form_list = ["bvba", "b.v.b.a.", "sprl", "s.p.r.l.", "sa", "s.a.",
                       "nv", "n.v.", "asbl", "a.s.b.l.", "vzw", "v.z.w.", 
                       "srl", "s.r.l.", "sprlu", "s.p.r.l.u.", "bv", "b.v."]
    company_legal_form = ""
    if span.label_ == "PERSON":
        # Check if the legal form is in the entity span
        search_obj = re.search( f'^({"|".join(legal_form_list)})$', span.text, re.I)
        if search_obj:
            company_legal_form = search_obj[0]
        # Check if the legal_form is at the right of the entity span
        elif span.end < len(span.doc):
            next_token = span.doc[span.end]
            company_legal_form = next_token.lower_ if next_token.lower_ in (legal_form_list) else ""
        # Check if the legal_form is at the left of the entity span
        elif span.start != 0:
            prev_token = span.doc[span.start - 1]
            company_legal_form = prev_token.lower_ if prev_token.lower_ in (legal_form_list) else ""
    return company_legal_form

Span.set_extension("company_legal_form", getter=get_legal_form, force=True)

# Format the entities
def extract_digits(string: str):
    """Extract digits from a string (KBO, NISS, ...)"""
    num = re.sub(r'\D', '', string)
    return str(num)

def format_entity(span: Span):
    """Format entities"""
    if span.label_ in ['KBO', 'NISS']:
        return extract_digits(span.text)
    else:
        return span.text

# Validate the entities
def validate_zipcode(span: Span):
    """ZIP_CODE validation, the zipcode should be follow
    by an entity type GPE.
    """
    if span.end < len(span.doc):
        next_token = span.doc[span.end]
        if next_token.ent_type_ == "GPE":
            return True
        else:
            return False
    else:
        return False

def valide_kbo(span: Span):
    """KBO and NISS validation, verify the checksum."""
    num = re.sub(r'[^\d]', '', span.text)
    check_digits = int(num[-2:])
    checksum = 97 - int(num[:-2])%97
    if checksum == check_digits:
        return True
    else:
        return False

def valide_niss(span: Span):
    """NISS validation, verify the checksum."""
    num = re.sub(r'\D', '', span.text)
    check_digits = int(num[-2:])
    # checksum for people before the year 2000
    checksum = 97 - int(num[:-2])%97
    if checksum == check_digits:
        return True
    else:
        #checksum for people born after the year 2000
        checksum = 97 - int("2" + num[:-2])%97
        return checksum == check_digits

def validate_entity(span: Span):
    """Validate entities."""
    if span.label_ == "ZIP_CODE":
        return validate_zipcode(span)
    elif span.label_ in ['KBO']:
        return valide_kbo(span)
    elif span.label_ in ['NISS']:
        return valide_niss(span)
    elif span.label_ == "REF":
        # Not used
        return False
    else:
        return True

Span.set_extension("is_valid_entity", getter=validate_entity, force=True)

# Get data
def get_data(doc: Doc) -> Dict[str, Any]:
    """Extract the data to return from the REST API given a Doc object."""
    entities = [
        {
            "text": format_entity(ent),
            "label": ent.label_,
            "start": ent.start_char,
            "end": ent.end_char,
            "person_title": ent._.person_title,
            "company_legal_form": ent._.company_legal_form
        }
        for ent in doc.ents if ent._.is_valid_entity
    ]
    # Generate a html file for entities visualisation
    if len(entities) > 0:
        html = displacy.render(doc, style="ent", jupyter=False, page=True)
    else:
        print("No entities extracted")
        html = ""
    return {"text": doc.text, "entities": entities, "html": html}

# Set up the FastAPI app and define the endpoints
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"])

@app.get("/models", summary="List all loaded models")
def get_models() -> List[str]:
    """Return a list of all available loaded models."""
    return MODEL_NAMES

@app.post("/process/", summary="Process batches of text", response_model=ResponseModel)
def process_texts(query: InputModel):
    """Process a batch of texts and return the entities predicted by the
    given model. Each record in the data should have a key "text".
    """
    nlp = MODELS[query.model]
    response_body = []
    texts = (text.content for text in query.texts)
    for doc in nlp.pipe(texts):
        response_body.append(get_data(doc))
    print(response_body)
    return {"result": response_body}
