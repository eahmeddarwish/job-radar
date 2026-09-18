"""Stdlib unittest — no pytest, no pip install, runs anywhere Python runs."""

import tempfile
import unittest
from pathlib import Path

from radar.config import load_profile
from radar.knockouts import check
from radar.score import evaluate, score_track
from radar.store import Store

PROFILE = load_profile()


def job(title="", description="", location="", company="Acme", url="https://x/1", uid="t:1"):
    return {"uid": uid, "source": "test", "title": title, "company": company,
            "location": location, "url": url, "description": description, "posted_at": ""}


class TestKnockouts(unittest.TestCase):
    def test_visa_wall_is_rejected(self):
        rejected, why = check(job(title="Python Engineer",
                                  description="You must be authorized to work in the US."), PROFILE)
        self.assertTrue(rejected)
        self.assertIn("work_authorisation", why)

    def test_no_sponsorship_is_rejected(self):
        rejected, _ = check(job(title="Backend Engineer",
                                description="Sorry, we are unable to sponsor visas."), PROFILE)
        self.assertTrue(rejected)

    def test_internship_is_rejected(self):
        rejected, why = check(job(title="Engineering Internship",
                                  description="A 12 week internship."), PROFILE)
        self.assertTrue(rejected)
        self.assertIn("seniority_mismatch", why)

    def test_location_outside_radius_is_rejected(self):
        rejected, why = check(job(title="ML Engineer", location="Berlin, Germany"), PROFILE)
        self.assertTrue(rejected)
        self.assertIn("work radius", why)

    def test_gcc_and_remote_locations_pass(self):
        for loc in ["Remote - Worldwide", "Kuwait City, Kuwait", "Dubai, UAE", "EMEA", ""]:
            with self.subTest(loc=loc):
                rejected, why = check(job(title="ML Engineer", location=loc), PROFILE)
                self.assertFalse(rejected, why)


class TestScoring(unittest.TestCase):
    def test_picks_the_right_cv_track(self):
        ai = evaluate(job(title="Senior Machine Learning Engineer",
                          description="Python, PyTorch, computer vision, OpenCV."), PROFILE)
        self.assertEqual(ai["track"], "ai-software")

        emb = evaluate(job(title="Embedded Firmware Engineer",
                           description="STM32, ESP32, RTOS, embedded C and sensors."), PROFILE)
        self.assertEqual(emb["track"], "embedded-iot")

        tr = evaluate(job(title="Technical Trainer",
                          description="Deliver technical training and build curriculum for workshops."), PROFILE)
        self.assertEqual(tr["track"], "technical-trainer")

    def test_title_match_outweighs_scattered_keywords(self):
        titled, _ = score_track(job(title="AI Engineer", description="python"), PROFILE.tracks[0])
        untitled, _ = score_track(job(title="Office Manager", description="python"), PROFILE.tracks[0])
        self.assertGreater(titled, untitled)

    def test_irrelevant_job_scores_below_the_floor(self):
        v = evaluate(job(title="Restaurant Shift Supervisor",
                         description="Manage the evening shift and the rota."), PROFILE)
        self.assertLess(v["score"], PROFILE.min_score)

    def test_reasons_are_always_returned_for_a_match(self):
        v = evaluate(job(title="AI Engineer", description="Python and machine learning."), PROFILE)
        self.assertTrue(v["reasons"])

    def test_word_boundaries_prevent_false_hits(self):
        # "ai" must not fire inside "maintenance", "chair", "detail"
        v = evaluate(job(title="Facilities Lead",
                         description="Maintenance of chairs and detailed upkeep."), PROFILE)
        self.assertLess(v["score"], PROFILE.min_score)


class TestNoiseFilters(unittest.TestCase):
    """Rules added after the first live run surfaced seven jobs, four of them noise."""

    def test_anti_pattern_in_title_kills_the_track(self):
        v = evaluate(job(title="QA Software Test Automation Engineers (Java)",
                         description="Test automation frameworks in Java, REST API testing."), PROFILE)
        self.assertLess(v["score"], PROFILE.min_score)

    def test_labelling_gig_is_not_a_training_role(self):
        v = evaluate(job(title="AI Trainer Image QA Evaluator",
                         description="Evaluate and label images. Training data quality."), PROFILE)
        self.assertEqual(v["score"], 0)

    def test_generic_title_with_thin_skills_is_penalised(self):
        thin = evaluate(job(title="Software Engineer GO",
                            description="Golang services and API work."), PROFILE)
        deep = evaluate(job(title="Software Engineer",
                            description="Python, PyTorch, OpenCV, machine learning, automation, OpenAI."), PROFILE)
        self.assertLess(thin["score"], PROFILE.min_score)
        self.assertGreaterEqual(deep["score"], PROFILE.min_score)

    def test_genai_titles_are_recognised(self):
        v = evaluate(job(title="Senior GenAI Solution Engineer",
                         description="Python, LLM, OpenAI, machine learning, API, Docker, FastAPI, git."), PROFILE)
        self.assertGreaterEqual(v["score"], PROFILE.min_score)


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_a_job_is_never_shown_twice(self):
        j = job(title="AI Engineer", uid="a:1")
        v = {"score": 80, "track": "ai-software", "reasons": ["x"], "rejected": False}
        self.assertTrue(self.store.add(j, v))
        self.assertFalse(self.store.add(j, v))
        self.assertEqual(len(self.store.unreported_matches(30, 10)), 1)

    def test_reported_jobs_drop_out_of_the_next_report(self):
        v = {"score": 80, "track": "ai-software", "reasons": [], "rejected": False}
        self.store.add(job(uid="a:1", title="AI Engineer"), v)
        self.store.mark_reported(["a:1"])
        self.assertEqual(self.store.unreported_matches(30, 10), [])

    def test_below_floor_jobs_are_not_reported(self):
        self.store.add(job(uid="a:2"), {"score": 10, "track": "ai-software", "reasons": [], "rejected": False})
        self.assertEqual(self.store.unreported_matches(30, 10), [])

    def test_status_transitions_and_bad_status(self):
        v = {"score": 80, "track": "ai-software", "reasons": [], "rejected": False}
        self.store.add(job(uid="a:3", title="AI Engineer"), v)
        self.store.set_status("a:3", "applied")
        self.assertEqual(len(self.store.applied_log()), 1)
        with self.assertRaises(ValueError):
            self.store.set_status("a:3", "hired-obviously")


if __name__ == "__main__":
    unittest.main()


class TestTracks(unittest.TestCase):
    """The decision hierarchy: which route a job belongs to, decided before score."""

    def test_the_three_routes(self):
        from radar.tracks import classify, GCC_SPONSORED, INSTITUTIONAL, REMOTE_FOREIGN
        cases = [
            ({"source": "institution/gust", "company": "GUST", "location": "Kuwait",
              "title": "Lecturer"}, INSTITUTIONAL),
            ({"source": "arbeitnow", "company": "Zain", "location": "Kuwait City, Kuwait",
              "title": "Automation Engineer"}, GCC_SPONSORED),
            ({"source": "remoteok", "company": "Mirantis", "location": "Remote - Worldwide",
              "title": "Software Engineer"}, REMOTE_FOREIGN),
            ({"source": "arbeitnow", "company": "KFUPM", "location": "Dhahran, Saudi Arabia",
              "title": "Instructor"}, INSTITUTIONAL),
        ]
        for job, want in cases:
            with self.subTest(company=job["company"]):
                self.assertEqual(classify(job), want)

    def test_a_long_country_list_is_remote_not_a_gulf_employer(self):
        """The Flex case: a London company listing eighty permitted countries,
        Kuwait among them. That is remote income, not a sponsor."""
        from radar.tracks import classify, REMOTE_FOREIGN
        job = {"source": "ashby/The-Flex", "company": "The Flex",
               "location": "Paris; Albania; Cairo; Kuwait; London; Oman; Qatar",
               "title": "Founding Software Engineer"}
        self.assertEqual(classify(job), REMOTE_FOREIGN)


class TestYield(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _add(self, uid, source, track="GCC_SPONSORED"):
        j = job(uid=uid, title="AI Engineer", url=f"https://x/{uid}")
        j["source"] = source
        j["employment_track"] = track
        self.store.add(j, {"score": 80, "track": "ai-software", "reasons": [], "rejected": False})

    def test_funnel_counts_per_source(self):
        self._add("a:1", "remotive"); self._add("a:2", "remotive"); self._add("b:1", "institution/gust")
        self.store.mark_applied("a:1")
        self.store.mark_applied("b:1")
        self.store.mark_outcome("b:1", "interview")

        by_source = {y["source"]: y for y in self.store.yield_by_source()}
        self.assertEqual(by_source["remotive"]["applied"], 1)
        self.assertEqual(by_source["remotive"]["interviews"], 0)
        self.assertEqual(by_source["institution/gust"]["interviews"], 1)
        self.assertEqual(by_source["institution/gust"]["rate"], 1.0)

    def test_unknown_outcome_is_rejected(self):
        self._add("a:1", "remotive")
        with self.assertRaises(ValueError):
            self.store.mark_outcome("a:1", "maybe")

    def test_grouping_keeps_routes_separate(self):
        self._add("a:1", "remoteok", "REMOTE_FOREIGN")
        self._add("b:1", "arbeitnow", "GCC_SPONSORED")
        grouped = self.store.unreported_matches_by_track(45, 10)
        self.assertEqual(set(grouped), {"REMOTE_FOREIGN", "GCC_SPONSORED"})
        self.assertEqual(len(grouped["GCC_SPONSORED"]), 1)


class TestSourceHealth(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_a_failing_source_is_counted_not_silently_zero(self):
        self.store.record_source("institution/ku", None, "unreachable: HTTPError: 404")
        self.store.record_source("institution/ku", None, "unreachable: HTTPError: 404")
        row = {h["source"]: h for h in self.store.source_health()}["institution/ku"]
        self.assertEqual(row["consecutive_fails"], 2)
        self.assertIsNone(row["last_count"])

    def test_recovery_resets_the_failure_count(self):
        self.store.record_source("remotive", None, "boom")
        self.store.record_source("remotive", 140, "ok")
        row = {h["source"]: h for h in self.store.source_health()}["remotive"]
        self.assertEqual(row["consecutive_fails"], 0)
        self.assertEqual(row["last_count"], 140)

    def test_page_hash_round_trip(self):
        self.store.record_source("institution/bsk", 0, "watching")
        self.assertIsNone(self.store.page_hash("institution/bsk"))
        self.store.set_page_hash("institution/bsk", "deadbeef")
        self.assertEqual(self.store.page_hash("institution/bsk"), "deadbeef")
