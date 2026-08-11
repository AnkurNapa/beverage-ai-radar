from radar.capabilities import AI, ALL, BI, CONSULTING, ERP, ESG, IOT, of_company, of_prospect, of_text


def test_a_thing_can_be_several_capabilities_at_once():
    """BarTrack is sensors plus inventory plus dashboards. One label would lie."""
    caps = of_text("inline sensor hardware for kegs with inventory management and dashboards")
    assert {IOT, ERP, BI} <= set(caps)


def test_vendor_keeps_the_ai_label_so_no_row_ends_up_blank():
    """Suppressing AI left 61 of 178 vendors with no label at all. Worse."""
    company = {"ai_use_case": "machine learning demand forecasting",
               "short_description": "Predictive models and dashboards for breweries."}
    assert {AI, BI} <= set(of_company(company))


def test_include_ai_false_is_still_available_for_a_narrower_view():
    assert AI not in of_text("machine learning models", include_ai=False)


def test_prospect_side_keeps_the_ai_label():
    assert AI in of_prospect({"wedge": "Demand forecasting", "pain": "", "segment": ""})


def test_wedges_map_to_capabilities_without_guessing():
    assert of_prospect({"wedge": "Distillery process intelligence"}) == [IOT, AI]
    assert of_prospect({"wedge": "Excise / compliance reporting automation"}) == [ERP]
    assert of_prospect({"wedge": "Taproom / retail analytics"}) == [BI]


def test_esg_is_orthogonal_to_the_wedge():
    """The SWA net-zero mandate is a buying trigger whatever wedge answers it."""
    row = {"wedge": "Distillery process intelligence",
           "pain": "Committed to net zero by 2040 and needs baseline measurement."}
    caps = of_prospect(row)
    assert ESG in caps and IOT in caps


def test_consultancy_is_detected():
    assert CONSULTING in of_text("an advisory and consulting firm for wineries")


def test_capabilities_come_back_in_a_stable_order():
    a = of_text("dashboard sensor consulting carbon erp machine learning")
    assert a == [c for c in ALL if c in a]


def test_unmatched_text_returns_empty_rather_than_a_wrong_label():
    assert of_text("a brewery that makes beer") == []


def test_channel_partner_rows_are_labelled_from_their_name():
    """'Beverage consultancies (First Key, Tulleeho)' has the signal in the name."""
    row = {"company": "Beverage consultancies (First Key, Tulleeho)",
           "wedge": "Subcontract the AI and data scope", "pain": "", "segment": ""}
    assert CONSULTING in of_prospect(row)


def test_a_disclaimer_does_not_mint_an_ai_capability():
    """"Makes no AI claim" is a finding, not evidence of AI.

    ai_maturity got AIMaturity.NONE to express this (see
    test_ai_claim_consistency), but capabilities kept matching the keyword
    inside the denial, so all 174 honestly-written no-AI rows were still
    labelled "AI & ML" - AB InBev, Endress+Hauser and Emerson among them.
    """
    disclaimers = [
        "The company names no AI or machine learning capability; it is spend analysis.",
        "It makes no machine learning claim anywhere on its site.",
        "Sensors and dashboards, but it makes no AI claim.",
        "A system of record with no AI or data-product claim.",
    ]
    for text in disclaimers:
        assert AI not in of_text(text), text

    # The fix must not go so far that it silences a real claim.
    asserted = [
        "Its own site claims AI-based software processing the physiological signal.",
        "uses computer vision to grade malt and a neural network for defect detection",
        "an LLM assistant over brewery batch records",
    ]
    for text in asserted:
        assert AI in of_text(text), text


def test_a_disclaimer_does_not_suppress_other_capabilities():
    """Only the AI rule reads the de-negated text.

    The negated span is blanked for the AI rule alone; a sentence that
    disclaims AI while describing real sensors must still be IoT.
    """
    caps = of_text("Inline sensors and a historian, but it makes no AI or machine learning claim.")
    assert IOT in caps
    assert AI not in caps
