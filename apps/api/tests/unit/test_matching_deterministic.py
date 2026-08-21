from uuid import uuid4

from procurepilot_api.modules.matching.deterministic import find_deterministic_candidate


def test_deterministic_matching_checks_gtin_before_supplier_code_and_alias() -> None:
    gtin_product_id = uuid4()
    supplier_product_id = uuid4()
    alias_product_id = uuid4()
    candidate = find_deterministic_candidate(
        line={
            "original_text": "alias text",
            "gtin": "5012345678900",
            "supplier_product_code": "SUP-1",
        },
        products=[
            {"id": gtin_product_id, "gtin": "5012345678900"},
            {"id": uuid4(), "gtin": "99999999"},
        ],
        aliases=[
            {
                "id": uuid4(),
                "workspace_product_id": alias_product_id,
                "alias_text": "alias text",
            }
        ],
        supplier_code_aliases=[
            {"id": uuid4(), "workspace_product_id": supplier_product_id, "alias_text": "SUP-1"}
        ],
    )
    assert candidate is not None
    assert candidate.workspace_product_id == gtin_product_id
    assert candidate.match_type == "gtin_match"
    assert candidate.reasons["gtin_match"] is True


def test_deterministic_matching_checks_supplier_code_before_alias() -> None:
    supplier_product_id = uuid4()
    alias_product_id = uuid4()
    candidate = find_deterministic_candidate(
        line={"original_text": "alias text", "supplier_product_code": "SUP-1"},
        products=[],
        aliases=[
            {
                "id": uuid4(),
                "workspace_product_id": alias_product_id,
                "alias_text": "alias text",
            }
        ],
        supplier_code_aliases=[
            {"id": uuid4(), "workspace_product_id": supplier_product_id, "alias_text": "SUP-1"}
        ],
    )
    assert candidate is not None
    assert candidate.workspace_product_id == supplier_product_id
    assert candidate.match_type == "supplier_code_match"
    assert candidate.reasons["supplier_code_match"] is True


def test_deterministic_matching_falls_back_to_case_insensitive_alias_hit() -> None:
    alias_product_id = uuid4()
    candidate = find_deterministic_candidate(
        line={"original_text": "ALIAS TEXT"},
        products=[],
        aliases=[
            {
                "id": uuid4(),
                "workspace_product_id": alias_product_id,
                "alias_text": "alias text",
            }
        ],
        supplier_code_aliases=[],
    )
    assert candidate is not None
    assert candidate.workspace_product_id == alias_product_id
    assert candidate.match_type == "alias_hit"
    assert candidate.reasons["alias_hit"] is True
