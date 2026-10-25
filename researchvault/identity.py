"""Publication matching preserves explicit keys and stops ambiguous selection."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import unquote

KEY = re.compile(r'[A-Z0-9]{8}\Z')


def doi(value):
    if value is None:
        return ''
    if not isinstance(value, str):
        raise ValueError('DOI must be text or null')
    text = unicodedata.normalize('NFKC', unquote(value)).strip().casefold()
    text = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)', '', text).strip()
    if text and not re.fullmatch(r'10\.\d{4,9}/[^\s]+', text):
        raise ValueError('DOI has an invalid form')
    return text


def arxiv(value):
    if value is None:
        return ''
    if not isinstance(value, str):
        raise ValueError('arXiv identifier must be text or null')
    text = re.sub(r'^(?:https?://arxiv\.org/(?:abs|pdf)/|arxiv:)', '', value.strip(), flags=re.I).removesuffix('.pdf')
    if text and not re.fullmatch(r'(?:\d{4}\.\d{4,5}|[a-zA-Z-]+(?:\.[A-Z]{2})?/\d{7})(?:v[1-9]\d*)?', text):
        raise ValueError('arXiv identifier has an invalid form')
    return text


def title(value):
    if value is None:
        return ''
    if not isinstance(value, str):
        raise ValueError('Title must be text')
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def check_records(records):
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError('Canonical metadata must be a list of mappings')
    parents, attachments, publications = {}, {}, {}
    for row in records:
        parent, child, namespace = row.get('zotero_key'), row.get('pdf_key'), row.get('library_id')
        if not isinstance(parent, str) or not KEY.fullmatch(parent):
            raise ValueError('Canonical record needs a real Zotero parent key')
        if namespace is not None and (type(namespace) is not int or namespace < 1):
            raise ValueError('Invalid library namespace')
        if child is not None and (not isinstance(child, str) or not KEY.fullmatch(child) or child == parent):
            raise ValueError('Attachment key is invalid or equals its parent')
        token = (namespace, parent)
        publication = doi(row.get('doi'))
        preprint = arxiv(row.get('arxiv_id'))
        name = title(row.get('title'))
        if token in parents:
            prior = parents[token]
            if (publication and prior[0] and publication != prior[0]) or (name and prior[1] and name != prior[1]) or (preprint and prior[2] and preprint != prior[2]):
                raise ValueError('Parent identity conflicts across supplied records')
        prior = parents.get(token, ('', '', ''))
        parents[token] = (publication or prior[0], name or prior[1], preprint or prior[2])
        if child:
            attachment = (namespace, child)
            if attachment in attachments and attachments[attachment] != token:
                raise ValueError('Attachment is associated with different parents')
            attachments[attachment] = token
        for external in filter(None, (publication, preprint)):
            address = (namespace, external)
            if address in publications and publications[address] != token:
                raise ValueError('Publication DOI maps to multiple parent items; reconcile duplicates')
            publications[address] = token
    if set(parents) & set(attachments):
        raise ValueError('A key is used as both parent and attachment')


def select(records, *, zotero_key=None, pdf_key=None, publication_doi=None, arxiv_id=None, name=None, library_id=None):
    check_records(records)
    rows = [dict(row) for row in records if row.get('library_id') == library_id]
    for key in (zotero_key, pdf_key):
        if key is not None and (not isinstance(key, str) or not KEY.fullmatch(key)):
            raise ValueError('Supplied Zotero key has an invalid form')
    if zotero_key:
        rows = [row for row in rows if row['zotero_key'] == zotero_key]
    elif publication_doi:
        rows = [row for row in rows if doi(row.get('doi')) == doi(publication_doi)]
    elif arxiv_id:
        rows = [row for row in rows if arxiv(row.get('arxiv_id')) == arxiv(arxiv_id)]
    elif pdf_key:
        rows = [row for row in rows if row.get('pdf_key') == pdf_key]
    elif name:
        rows = [row for row in rows if title(row.get('title')) == title(name)]
    else:
        raise ValueError('Supply a parent key, verified DOI or title lookup hint')
    if not rows:
        raise ValueError('MANUAL_REVIEW_REQUIRED: requested identity not found in this library')
    if len({row['zotero_key'] for row in rows}) != 1:
        raise ValueError('MANUAL_REVIEW_REQUIRED: lookup is ambiguous')
    if publication_doi and any(doi(row.get('doi')) != doi(publication_doi) for row in rows):
        raise ValueError('MANUAL_REVIEW_REQUIRED: supplied DOI conflicts with selected parent')
    if arxiv_id and any(arxiv(row.get('arxiv_id')) != arxiv(arxiv_id) for row in rows):
        raise ValueError('MANUAL_REVIEW_REQUIRED: supplied arXiv version conflicts with selected parent')
    if name and any(title(row.get('title')) != title(name) for row in rows):
        raise ValueError('MANUAL_REVIEW_REQUIRED: supplied title conflicts with selected parent')
    if pdf_key:
        rows = [row for row in rows if row.get('pdf_key') == pdf_key]
    if len({row.get('pdf_key') for row in rows}) != 1 or not rows:
        raise ValueError('MANUAL_REVIEW_REQUIRED: choose one existing attachment')
    return rows[0]
