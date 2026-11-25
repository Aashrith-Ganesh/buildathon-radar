from buildathon_radar.digest import build_digest, build_html_digest
from buildathon_radar import tracker_store


def make_item(url, title="Source Title", **overrides):
    item = {
        "source": "Devpost",
        "title": title,
        "url": url,
        "summary": "s",
        "published": "2026-01-01",
        "location": "Bengaluru, India",
        "mode": "in-person",
        "host": "Some Host",
        "dates": "Jul 18, 2026",
        "prize": "$1,000",
        "themes": ["Machine Learning/AI"],
    }
    item.update(overrides)
    return item


def make_pick(item, tier="must_see", score=80, why="matters", model_title="Model's Guess"):
    return {
        "url": item["url"],
        "title": model_title,
        "tier": tier,
        "score": score,
        "scoring": {},
        "why": why,
        "item": item,
    }


class TestCardFactsFromSourceItem:
    def test_title_comes_from_source_item_not_model(self):
        item = make_item("https://a.com/1", title="Real Devpost Title")
        pick = make_pick(item, model_title="Something Model Made Up")
        digest = build_digest([pick], [], {"Devpost": {"count": 1, "error": None}}, "note")
        assert "Real Devpost Title" in digest
        assert "Something Model Made Up" not in digest

    def test_host_location_dates_prize_from_item(self):
        item = make_item("https://a.com/1", host="IEEE", location="Bengaluru, India", dates="Jul 18, 2026", prize="Overall Prize")
        pick = make_pick(item)
        digest = build_digest([pick], [], {"Devpost": {"count": 1, "error": None}}, "")
        assert "IEEE" in digest
        assert "Bengaluru, India" in digest
        assert "Jul 18, 2026" in digest
        assert "Overall Prize" in digest


class TestSectionOrderingAndSort:
    def test_sections_appear_in_tier_order(self):
        item1 = make_item("https://a.com/1")
        item2 = make_item("https://b.com/2")
        item3 = make_item("https://c.com/3")
        picks = [
            make_pick(item1, tier="radar", score=40),
            make_pick(item2, tier="must_see", score=90),
            make_pick(item3, tier="worth_a_look", score=60),
        ]
        digest = build_digest(picks, [], {"Devpost": {"count": 3, "error": None}}, "")
        must_pos = digest.find("Must-see")
        worth_pos = digest.find("Worth a look")
        radar_pos = digest.find("On the radar")
        assert must_pos < worth_pos < radar_pos

    def test_within_section_sorted_by_score_descending(self):
        item1 = make_item("https://a.com/1", title="Low Score Event")
        item2 = make_item("https://b.com/2", title="High Score Event")
        picks = [
            make_pick(item1, tier="must_see", score=71),
            make_pick(item2, tier="must_see", score=95),
        ]
        digest = build_digest(picks, [], {"Devpost": {"count": 2, "error": None}}, "")
        assert digest.find("High Score Event") < digest.find("Low Score Event")

    def test_empty_tier_section_omitted(self):
        item1 = make_item("https://a.com/1")
        picks = [make_pick(item1, tier="must_see", score=90)]
        digest = build_digest(picks, [], {"Devpost": {"count": 1, "error": None}}, "")
        assert "Worth a look" not in digest
        assert "On the radar" not in digest


class TestQuietWeekAndDegradation:
    def test_zero_picks_all_healthy_quiet_week(self):
        health = {"Devpost": {"count": 0, "error": None}, "Devfolio": {"count": 0, "error": None}}
        digest = build_digest([], [], health, "")
        assert "Quiet week" in digest

    def test_zero_picks_all_sources_failed(self):
        health = {
            "Devpost": {"count": 0, "error": "Connection timeout"},
            "Devfolio": {"count": 0, "error": "HTTP 503"},
        }
        digest = build_digest([], [], health, "")
        assert "All sources failed" in digest

    def test_failed_source_footer_flagged(self):
        item = make_item("https://a.com/1")
        picks = [make_pick(item)]
        health = {
            "Devpost": {"count": 1, "error": None},
            "Devfolio": {"count": 0, "error": "Connection timeout"},
        }
        digest = build_digest(picks, [], health, "")
        assert "FAILED (Connection timeout)" in digest
        assert "⚠️" in digest

    def test_zero_result_healthy_source_flagged(self):
        health = {"Devpost": {"count": 0, "error": None}, "Devfolio": {"count": 5, "error": None}}
        item = make_item("https://a.com/1")
        picks = [make_pick(item)]
        digest = build_digest(picks, [], health, "")
        assert "Devpost: 0 new events ⚠️" in digest

    def test_healthy_source_never_silently_dropped_from_footer(self):
        health = {"Devpost": {"count": 3, "error": None}, "Devfolio": {"count": 7, "error": None}}
        item = make_item("https://a.com/1")
        picks = [make_pick(item)]
        digest = build_digest(picks, [], health, "")
        assert "Devpost: 3 new events" in digest
        assert "Devfolio: 7 new events" in digest


class TestIntegrityLine:
    def test_no_integrity_line_when_no_drops(self):
        item = make_item("https://a.com/1")
        picks = [make_pick(item)]
        digest = build_digest(picks, [], {"Devpost": {"count": 1, "error": None}}, "")
        assert "Integrity guard" not in digest

    def test_integrity_line_renders_when_drops_exist(self):
        item = make_item("https://a.com/1")
        picks = [make_pick(item)]
        dropped = [{"url": "https://fake.com/x", "title": "Fake", "tier": "must_see", "score": 99, "why": "invented"}]
        digest = build_digest(picks, dropped, {"Devpost": {"count": 1, "error": None}}, "")
        assert "Integrity guard:** 1 pick(s) dropped" in digest


class TestHtmlDigestGmailCompatibility:
    def test_table_based_no_flex_or_grid(self):
        item = make_item("https://a.com/1")
        picks = [make_pick(item)]
        html = build_html_digest(picks, [], {"Devpost": {"count": 1, "error": None}}, "note")
        assert "<table" in html
        assert "display:flex" not in html
        assert "display: flex" not in html
        assert "display:grid" not in html

    def test_no_style_block_and_no_external_assets(self):
        item = make_item("https://a.com/1")
        picks = [make_pick(item)]
        html = build_html_digest(picks, [], {"Devpost": {"count": 1, "error": None}}, "note")
        assert "<style" not in html
        assert "<script" not in html
        assert "<link" not in html
        assert "fonts.googleapis" not in html

    def test_system_font_stack_present(self):
        item = make_item("https://a.com/1")
        picks = [make_pick(item)]
        html = build_html_digest(picks, [], {"Devpost": {"count": 1, "error": None}}, "note")
        assert "-apple-system, Roboto, 'Helvetica Neue', Arial, sans-serif" in html

    def test_all_cells_have_explicit_background_color(self):
        item = make_item("https://a.com/1")
        picks = [make_pick(item)]
        html = build_html_digest(picks, [], {"Devpost": {"count": 1, "error": None}}, "note")
        import re
        for td in re.findall(r"<td[^>]*style=\"([^\"]*)\"", html):
            assert "background-color" in td


class TestHtmlDigestTealTheme:
    def test_masthead_teal_and_title(self):
        html = build_html_digest([], [], {"Devpost": {"count": 0, "error": None}}, "")
        assert "#0f4c4c" in html
        assert "Buildathon Radar" in html

    def test_page_background(self):
        html = build_html_digest([], [], {"Devpost": {"count": 0, "error": None}}, "")
        assert "#f6f4ef" in html

    def test_tier_stripe_colors(self):
        item1 = make_item("https://a.com/1")
        item2 = make_item("https://b.com/2")
        item3 = make_item("https://c.com/3")
        picks = [
            make_pick(item1, tier="must_see", score=90),
            make_pick(item2, tier="worth_a_look", score=60),
            make_pick(item3, tier="radar", score=40),
        ]
        html = build_html_digest(picks, [], {"Devpost": {"count": 3, "error": None}}, "")
        assert "#0d9488" in html  # must_see stripe (and score badge)
        assert "#5b8a8a" in html  # worth_a_look stripe
        assert "#8fa6a6" in html  # radar stripe

    def test_date_range_subtitle_rendered(self):
        html = build_html_digest([], [], {"Devpost": {"count": 0, "error": None}}, "", "Jul 1 - 7, 2026")
        assert "Jul 1 - 7, 2026" in html


class TestHtmlDigestCardStructure:
    def test_card_facts_from_source_item_not_model(self):
        item = make_item("https://a.com/1", title="Real Devpost Title")
        pick = make_pick(item, model_title="Something Model Made Up")
        html = build_html_digest([pick], [], {"Devpost": {"count": 1, "error": None}}, "")
        assert "Real Devpost Title" in html
        assert "Something Model Made Up" not in html

    def test_score_badge_and_source_present(self):
        item = make_item("https://a.com/1")
        pick = make_pick(item, score=87)
        html = build_html_digest([pick], [], {"Devpost": {"count": 1, "error": None}}, "")
        assert ">87<" in html
        assert "via Devpost" in html

    def test_why_row_present_with_tint_when_why_given(self):
        item = make_item("https://a.com/1")
        pick = make_pick(item, why="Matters a lot.")
        html = build_html_digest([pick], [], {"Devpost": {"count": 1, "error": None}}, "")
        assert "Matters a lot." in html
        assert "#eaf3f1" in html

    def test_why_row_absent_when_no_why(self):
        item = make_item("https://a.com/1")
        pick = make_pick(item, why="")
        html = build_html_digest([pick], [], {"Devpost": {"count": 1, "error": None}}, "")
        assert "#eaf3f1" not in html

    def test_dynamic_content_is_html_escaped(self):
        item = make_item("https://a.com/1", title="<script>alert(1)</script> & Co", host="A & B Corp")
        pick = make_pick(item)
        html = build_html_digest([pick], [], {"Devpost": {"count": 1, "error": None}}, "")
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html
        assert "A &amp; B Corp" in html


class TestHtmlDigestFooterAndDegradation:
    def test_source_health_footer_present(self):
        item = make_item("https://a.com/1")
        pick = make_pick(item)
        health = {"Devpost": {"count": 3, "error": None}, "Devfolio": {"count": 7, "error": None}}
        html = build_html_digest([pick], [], health, "")
        assert "Devpost: 3 new events" in html
        assert "Devfolio: 7 new events" in html

    def test_failed_source_shown_in_footer(self):
        item = make_item("https://a.com/1")
        pick = make_pick(item)
        health = {"Devpost": {"count": 1, "error": None}, "Devfolio": {"count": 0, "error": "Connection timeout"}}
        html = build_html_digest([pick], [], health, "")
        assert "FAILED (Connection timeout)" in html

    def test_integrity_line_present_when_dropped(self):
        item = make_item("https://a.com/1")
        pick = make_pick(item)
        dropped = [{"url": "https://fake.com/x", "title": "Fake", "tier": "must_see", "score": 99, "why": "invented"}]
        html = build_html_digest([pick], dropped, {"Devpost": {"count": 1, "error": None}}, "")
        assert "Integrity guard: 1 pick(s) dropped" in html

    def test_quiet_week_body_when_no_picks(self):
        html = build_html_digest([], [], {"Devpost": {"count": 0, "error": None}, "Devfolio": {"count": 0, "error": None}}, "")
        assert "Quiet week" in html

    def test_intro_week_note_preserved(self):
        item = make_item("https://a.com/1")
        pick = make_pick(item)
        html = build_html_digest([pick], [], {"Devpost": {"count": 1, "error": None}}, "A strong week.")
        assert "A strong week." in html


class TestHtmlDigestMobileWrapping:
    def test_outer_container_is_fluid_not_fixed_width(self):
        item = make_item("https://a.com/1")
        pick = make_pick(item)
        html = build_html_digest([pick], [], {"Devpost": {"count": 1, "error": None}}, "")
        assert 'width="600"' not in html
        assert "width:600px; max-width:600px" not in html  # old fixed-width style
        assert 'width="100%"' in html
        assert "width:100%; max-width:600px" in html

    def test_viewport_meta_present(self):
        html = build_html_digest([], [], {"Devpost": {"count": 0, "error": None}}, "")
        assert 'name="viewport"' in html
        assert "width=device-width" in html

    def test_title_meta_dates_why_have_word_break(self):
        item = make_item(
            "https://a.com/1",
            title="Averylongunbrokenhackathontitlewithnospacesatallwhatsoever",
            prize="Most Startup-Ready Product, Best Agentic Payments Product, Best Project, Second Place, Third Place",
        )
        pick = make_pick(item, why="A fairly long why line that could also run wide on a narrow phone screen if unconstrained.")
        html = build_html_digest([pick], [], {"Devpost": {"count": 1, "error": None}}, "")
        assert html.count("word-break:break-word") >= 5
        assert html.count("overflow-wrap:break-word") >= 5

    def test_footer_health_line_has_word_break(self):
        item = make_item("https://a.com/1")
        pick = make_pick(item)
        health = {"Devpost": {"count": 1, "error": None}, "Devfolio": {"count": 0, "error": "Connection timeout while fetching a very long error message"}}
        html = build_html_digest([pick], [], health, "")
        footer_section = html[html.rfind("Source health"):]
        assert "word-break:break-word" in footer_section


def make_tracker_row(event_id, **overrides):
    row = {
        "event_id": event_id,
        "title": "Tracked Hackathon",
        "url": "https://tracked.devpost.com/",
        "event_start": "2026-08-01",
        "event_end": "2026-08-02",
    }
    row.update(overrides)
    return row


class TestActionButtons:
    def test_card_contains_both_signed_hrefs(self, monkeypatch):
        import buildathon_radar.digest
        monkeypatch.setenv("TRACKER_SECRET", "test-secret")
        monkeypatch.setattr(buildathon_radar.digest, "TRACKER_BASE", "https://radar.job-joseph.com")
        item = make_item("https://a.com/1", event_id="ev-1")
        pick = make_pick(item)
        html = build_html_digest([pick], [], {"Devpost": {"count": 1, "error": None}}, "")
        assert "https://radar.job-joseph.com/track?event_id=ev-1&amp;t=" in html
        assert "https://radar.job-joseph.com/applied?event_id=ev-1&amp;t=" in html
        assert "Track" in html
        assert "Applied" in html

    def test_button_token_is_verifiable(self, monkeypatch):
        monkeypatch.setenv("TRACKER_SECRET", "test-secret")
        item = make_item("https://a.com/1", event_id="ev-2")
        pick = make_pick(item)
        html = build_html_digest([pick], [], {"Devpost": {"count": 1, "error": None}}, "")
        import re
        match = re.search(r"/track\?event_id=ev-2&amp;t=([0-9a-f]+)", html)
        assert match is not None
        token = match.group(1)
        assert tracker_store.verify_action("track", "ev-2", token, secret="test-secret")

    def test_event_id_urlencoded_in_href(self, monkeypatch):
        monkeypatch.setenv("TRACKER_SECRET", "test-secret")
        item = make_item("https://a.com/1", event_id="ev with space")
        pick = make_pick(item)
        html = build_html_digest([pick], [], {"Devpost": {"count": 1, "error": None}}, "")
        assert "event_id=ev%20with%20space" in html

    def test_no_button_row_without_event_id(self, monkeypatch):
        monkeypatch.setenv("TRACKER_SECRET", "test-secret")
        item = make_item("https://a.com/1")  # no event_id key
        pick = make_pick(item)
        html = build_html_digest([pick], [], {"Devpost": {"count": 1, "error": None}}, "")
        assert "radar.job-joseph.com" not in html

    def test_no_button_row_when_secret_unset(self, monkeypatch):
        monkeypatch.delenv("TRACKER_SECRET", raising=False)
        item = make_item("https://a.com/1", event_id="ev-3")
        pick = make_pick(item)
        html = build_html_digest([pick], [], {"Devpost": {"count": 1, "error": None}}, "")
        assert "radar.job-joseph.com" not in html


class TestTrackedSection:
    def test_omitted_when_empty(self):
        html = build_html_digest([], [], {"Devpost": {"count": 0, "error": None}}, "", tracked_events=[])
        assert "Tracked" not in html

    def test_renders_title_and_start_date_when_present(self):
        row = make_tracker_row("t1", title="Reminder Hack", event_start="2026-09-15")
        html = build_html_digest([], [], {"Devpost": {"count": 0, "error": None}}, "", tracked_events=[row])
        assert "Reminder Hack" in html
        assert "Sep 15, 2026" in html
        assert "https://tracked.devpost.com/" in html


class TestParticipationLog:
    def test_empty_state_copy_when_no_applied_events(self):
        html = build_html_digest([], [], {"Devpost": {"count": 0, "error": None}}, "", applied_events=[])
        assert "Nothing here yet" in html
        assert "Participation log" in html

    def test_renders_title_and_both_dates(self):
        row = make_tracker_row("a1", title="Applied Hack", event_start="2026-08-01", event_end="2026-08-03")
        html = build_html_digest([], [], {"Devpost": {"count": 0, "error": None}}, "", applied_events=[row])
        assert "Applied Hack" in html
        assert "Aug 01, 2026" in html
        assert "Aug 03, 2026" in html
        assert "https://tracked.devpost.com/" in html

    def test_tbd_fallback_for_missing_dates(self):
        row = make_tracker_row("a2", event_start=None, event_end=None)
        html = build_html_digest([], [], {"Devpost": {"count": 0, "error": None}}, "", applied_events=[row])
        assert "TBD" in html

    def test_section_always_present_even_with_picks(self):
        item = make_item("https://a.com/1")
        pick = make_pick(item)
        html = build_html_digest([pick], [], {"Devpost": {"count": 1, "error": None}}, "")
        assert "Participation log" in html


class TestPlainTextUnaffectedByButtons:
    def test_build_digest_output_unchanged_with_event_id_present(self):
        item = make_item("https://a.com/1", event_id="ev-1")
        pick = make_pick(item)
        item_no_id = make_item("https://a.com/1")
        pick_no_id = make_pick(item_no_id)
        digest_with = build_digest([pick], [], {"Devpost": {"count": 1, "error": None}}, "note")
        digest_without = build_digest([pick_no_id], [], {"Devpost": {"count": 1, "error": None}}, "note")
        assert digest_with == digest_without
        assert "radar.job-joseph.com" not in digest_with


class TestGenerateDigestData:
    def test_digest_data_structure(self, tmp_path):
        db_path = str(tmp_path / "tracker_test.db")
        conn = tracker_store.connect(db_path)
        tracker_store.upsert_seen(conn, [
            {
                "event_id": "test-ev-1",
                "title": "Bangalore AI Hack Night",
                "url": "https://example.com/ai-night",
                "host": "AI Innovators",
                "source": "Luma",
                "summary": "Hackathon in Bangalore for AI builders",
                "location": "Koramangala, Bangalore",
                "mode": "in-person",
                "event_start": "2026-12-05",
                "event_end": "2026-12-05",
                "registration_deadline": "2026-12-04",
                "team_size": "3-5",
                "eligibility": "ELIGIBLE",
                "prize": "₹50,000",
                "score": 95,
                "priority": "HIGH PRIORITY",
                "why": "Bengaluru venue | Class 11/12 Eligible",
            },
            {
                "event_id": "test-ev-2-conflict",
                "title": "Conflicting Exam Day Hack",
                "url": "https://example.com/exam-conflict",
                "host": "Acme",
                "location": "Online",
                "mode": "online",
                "event_start": "2026-11-26",
                "event_end": "2026-11-27",
                "blackout_conflict": 1,
                "score": 99,
                "priority": "CONFLICT (UNAVAILABLE)",
            }
        ])
        from buildathon_radar.digest import generate_digest_data
        data = generate_digest_data(conn=conn, limit_featured=5)
        conn.close()

        assert data["status"] == "ok"
        assert "meta" in data
        assert "featured_hackathons" in data
        assert "newly_discovered" in data
        assert "upcoming_deadlines" in data
        assert "events_happening_soon" in data
        assert "recommended_opportunities" in data
        assert "important_changes" in data
        assert "blackout_calendar" in data
        assert "tracked_events" in data
        assert "applied_events" in data

        # Conflicted event should NOT be in featured hackathons
        featured_ids = [e["event_id"] for e in data["featured_hackathons"]]
        assert "test-ev-2-conflict" not in featured_ids
        assert "test-ev-1" in featured_ids

        # Check metadata fields of event
        ev = data["featured_hackathons"][0]
        assert ev["title"] == "Bangalore AI Hack Night"
        assert ev["host"] == "AI Innovators"
        assert ev["location"] == "Koramangala, Bangalore"
        assert ev["mode"] == "in-person"
        assert ev["event_start"] == "2026-12-05"
        assert ev["registration_deadline"] == "2026-12-04"
        assert ev["team_size"] == "3-5"
        assert ev["prize"] == "₹50,000"
        assert ev["is_bengaluru"] is True
        assert ev["score"] == 95
        assert ev["priority"] == "HIGH PRIORITY"
        assert "url" in ev
        assert "why" in ev
        assert "track_url" in ev
        assert "applied_url" in ev

    def test_api_digest_endpoint(self, tmp_path, monkeypatch, local_client):
        from buildathon_radar import tracker_service
        db_path = str(tmp_path / "tracker_api.db")
        monkeypatch.setattr(tracker_service, "DB_PATH", db_path)
        conn = tracker_store.connect(db_path)
        tracker_store.upsert_seen(conn, [{
            "event_id": "api-ev-1",
            "title": "API Test Hackathon",
            "url": "https://example.com/api-test",
            "location": "Bengaluru",
            "mode": "in-person",
            "score": 90,
            "priority": "HIGH PRIORITY",
        }])
        conn.close()
        client = local_client(tracker_service.app)
        resp = client.get("/api/digest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["featured_hackathons"]) >= 1
        assert data["featured_hackathons"][0]["title"] == "API Test Hackathon"
