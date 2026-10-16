from procurepilot_api.modules.tenants.service import _candidate_slugs, slugify_business_name


def test_arabic_slug_is_meaningfully_transliterated() -> None:
    assert slugify_business_name("مطاعم سند") == "mtaam-snd"


def test_mixed_arabic_latin_and_accented_latin() -> None:
    assert slugify_business_name("Sanad مطاعم 2") == "sanad-mtaam-2"
    assert slugify_business_name("Café Déjà Vu") == "cafe-deja-vu"


def test_latin_compatibility_and_unusable_names() -> None:
    assert slugify_business_name("Acme Foods") == "acme-foods"
    assert _candidate_slugs("漢字 😀")[0].startswith("ws-")
    assert all(3 <= len(slug) <= 63 for slug in _candidate_slugs("漢字 😀"))
