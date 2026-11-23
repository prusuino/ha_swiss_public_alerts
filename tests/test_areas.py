"""What an alert covers: polygons with zones cut out, circles, the canton the
feed names, usable links and the other fields read since 1.8.0."""
from __future__ import annotations

from custom_components.swiss_public_alerts.api import _ring, _web_link

from .common import HOLE, HOME, SQUARE, circle_item, item, parse


def test_a_circle_area_covers_what_lies_within_its_radius():
    alert = parse(circle_item())
    assert alert.polygons == () and alert.circles == ((46.7697, 8.67591, 0.266602233),)
    assert alert.covers(46.7697, 8.67591) is True  # the centre
    assert alert.covers(46.7715, 8.67591) is True  # 200 m north
    assert alert.covers(46.7733, 8.67591) is False  # 400 m north
    # a circle alone still gives the alert a place on the map and a distance
    assert alert.centroid == (46.7697, 8.67591)
    assert round(alert.distance_km(46.77, 8.70), 1) == 1.8
    assert alert.canton_code == "ur"


def test_broken_circles_are_skipped():
    area = {"circles": [{"centerPosition": ["46.5"], "radius": "1"}, {"radius": "1"}, {"centerPosition": ["a", "b"], "radius": "1"}, None,
                        {"centerPosition": ["46.5", "7.5"], "radius": "2"}]}
    alert = parse(item(areas=[area, "garbage"]))
    assert alert.circles == ((46.5, 7.5, 2.0),)
    assert alert.covers(*HOME) is True


def test_a_zone_cut_out_of_a_polygon_is_not_covered():
    alert = parse(item(areas=[{"polygons": [{"coordinates": SQUARE, "excludes": [{"coordinates": HOLE}, {"coordinates": [["1", "2"]]}, None]}]}]))
    assert len(alert.polygons) == 1 and len(alert.holes[0]) == 1  # the two-point "hole" is dropped
    assert alert.covers(*HOME) is False  # inside the cut-out zone
    assert alert.covers(46.2, 7.2) is True  # inside the area, outside the zone
    assert alert.covers(48.0, 7.2) is False


def test_a_second_area_still_covers_a_point_the_first_one_cuts_out():
    areas = [{"polygons": [{"coordinates": SQUARE, "excludes": [{"coordinates": HOLE}]}, {"coordinates": HOLE}]}]
    assert parse(item(areas=areas)).covers(*HOME) is True
    areas = [{"polygons": [{"coordinates": SQUARE, "excludes": [{"coordinates": HOLE}]}], "circles": [{"centerPosition": ["46.5", "7.5"], "radius": "1"}]}]
    assert parse(item(areas=areas)).covers(*HOME) is True


def test_ring_skips_unreadable_pairs():
    assert _ring([["46.0", "7.0"], ["x", "7"], [46.1], None, [46.2, 7.2]]) == ((46.0, 7.0), (46.2, 7.2))
    assert _ring(None) == ()


def test_the_canton_comes_from_the_feed_regions():
    # the publisher says nothing, the region does
    assert parse(item(publisherName="Führungsstab", areas=[{"regions": [{"region": "VS"}]}])).canton_code == "vs"
    # no publisher at all
    alert = parse({k: v for k, v in item().items() if k != "publisherName"})
    assert alert.canton_code == "be" and alert.cantons == ("be",) and alert.publisher == ""
    # several cantons: the publisher decides, else the first region
    two = [{"regions": [{"region": "UR"}, {"region": "SZ"}, {"region": "UR"}, {"region": "x1"}, None]}]
    assert parse(item(publisherName="Kanton Schwyz", areas=two)).canton_code == "sz"
    several = parse(item(publisherName="Führungsstab", areas=two))
    assert several.canton_code == "ur" and several.cantons == ("ur", "sz")
    assert several.summary["cantons"] == ["ur", "sz"]
    # no region: the publisher's name as before
    assert parse(item(areas=[])).canton_code == "be"
    assert parse(item(publisherName="Unbekannt", areas=[])).canton_code is None
    assert parse(item(nationWide=True)).canton_code == "ch"


def test_links_are_made_usable_or_dropped():
    assert _web_link("https://www.alert.swiss/x?y=1") == "https://www.alert.swiss/x?y=1"
    assert _web_link("HTTP://example.ch") == "HTTP://example.ch"
    assert _web_link(" www.awn.gr.ch ") == "https://www.awn.gr.ch"
    assert _web_link("www.turbenthal.ch/aktuelles/detail.html") == "https://www.turbenthal.ch/aktuelles/detail.html"
    for bad in (None, "", "javascript:alert(1)", "mailto:info@example.ch", "siehe www.example.ch", "www", "example.ch"):
        assert _web_link(bad) is None


def test_the_alert_link_falls_back_to_the_link_list_and_then_to_alertswiss():
    bare = parse(item(link="www.awn.gr.ch", links=[{"href": "https://www.awn.gr.ch", "text": "Amt für Wald"}]))
    assert bare.link == "https://www.awn.gr.ch"
    assert bare.links == (("https://www.awn.gr.ch", "Amt für Wald"),)
    assert bare.summary["links"] == [{"href": "https://www.awn.gr.ch", "text": "Amt für Wald"}]
    from_list = parse(item(link="call us", links=[{"href": "javascript:x"}, "garbage", {"href": "www.ur.ch", "text": ""}]))
    assert from_list.link == "https://www.ur.ch"
    assert from_list.links == (("https://www.ur.ch", "https://www.ur.ch"),)  # no text: the address itself
    nothing = parse(item("POA-9", link=None, links=[]))
    assert nothing.link == "https://www.alert.swiss/content/alertswiss-internet/de/home.html#POA-9"
    assert nothing.links == ()


def test_contact_and_machine_translation():
    alert = parse(item(gtransOrigin="en-x-mtfrom-de"))
    assert alert.contact == "Polizeinotruf: 117"
    assert alert.machine_translated is True and alert.summary["machine_translated"] is True
    plain = parse(item(contact=None))
    assert plain.contact == "" and plain.machine_translated is False
