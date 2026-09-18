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
