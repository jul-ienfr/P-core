from __future__ import annotations

import re

CANONICAL_PERSON = "Person"
CANONICAL_ORGANIZATION = "Organization"
CANONICAL_PRODUCT = "Product"
CANONICAL_LOCATION = "Location"
CANONICAL_ENTITY = "Entity"

_CANONICAL_TYPES = {
    CANONICAL_PERSON,
    CANONICAL_ORGANIZATION,
    CANONICAL_PRODUCT,
    CANONICAL_LOCATION,
}

_PERSON_TOKENS = {
    "person",
    "people",
    "individual",
    "actor",
    "leader",
    "celebrity",
    "expert",
    "scholar",
    "journalist",
    "student",
    "citizen",
    "witness",
    "victim",
    "perpetrator",
    "influencer",
    "opinionleader",
    "kol",
    "kols",
}

_ORGANIZATION_TOKENS = {
    "organization",
    "org",
    "company",
    "enterprise",
    "brand",
    "agency",
    "department",
    "government",
    "regulator",
    "university",
    "school",
    "institute",
    "ngo",
    "union",
    "association",
    "foundation",
    "media",
    "newspaper",
    "tv",
    "platform",
    "committee",
    "community",
    "account",
}

_PRODUCT_TOKENS = {
    "product",
    "app",
    "application",
    "service",
    "tool",
    "model",
    "software",
    "system",
    "api",
    "framework",
    "device",
    "game",
}

_LOCATION_TOKENS = {
    "location",
    "place",
    "city",
    "country",
    "province",
    "region",
    "state",
    "county",
    "district",
    "area",
}


def _tokens(value: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9]+", value.lower()) if part}


def canonicalize_entity_type(raw_type: str | None) -> str:
    value = (raw_type or "").strip()
    if not value:
        return CANONICAL_ENTITY
    if value in _CANONICAL_TYPES:
        return value

    lowered = value.lower()

    if any(hint in value for hint in ("人物", "个人", "人", "当事人")):
        return CANONICAL_PERSON
    if any(hint in value for hint in ("组织", "机构", "公司", "企业", "政府", "部门", "媒体", "平台", "账号", "协会", "大学")):
        return CANONICAL_ORGANIZATION
    if any(hint in value for hint in ("产品", "应用", "软件", "系统", "品牌", "模型")):
        return CANONICAL_PRODUCT
    if any(hint in value for hint in ("地点", "位置", "城市", "国家", "地区", "省", "市", "县", "区")):
        return CANONICAL_LOCATION

    tokens = _tokens(lowered)
    if tokens & _PERSON_TOKENS:
        return CANONICAL_PERSON
    if tokens & _LOCATION_TOKENS:
        return CANONICAL_LOCATION
    if tokens & _PRODUCT_TOKENS:
        return CANONICAL_PRODUCT
    if tokens & _ORGANIZATION_TOKENS:
        return CANONICAL_ORGANIZATION

    if any(hint in lowered for hint in ("account", "agency", "company", "org", "platform", "media", "university", "school")):
        return CANONICAL_ORGANIZATION
    if any(hint in lowered for hint in ("product", "app", "model", "service", "system", "software")):
        return CANONICAL_PRODUCT
    if any(hint in lowered for hint in ("location", "place", "city", "country", "province", "region", "district")):
        return CANONICAL_LOCATION
    if any(hint in lowered for hint in ("person", "individual", "actor", "leader", "expert", "student", "journalist")):
        return CANONICAL_PERSON

    return value
