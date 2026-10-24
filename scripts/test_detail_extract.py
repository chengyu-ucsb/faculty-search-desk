"""Offline regression cases for source-backed application extraction."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from detail_extract import date_value, text_lines, evidence_from_lines, application_links, merge_evidence

class DetailTests(unittest.TestCase):
    def test_priority_deadline_and_required_items(self):
        html = """<html><main><h2>Assistant Professor, Strategic Communication</h2>
        <p>How To Apply</p><p>Please attach a cover letter and resume or CV.</p>
        <p>Priority will be given to completed applications received by Oct. 21, 2026
        but applications will be reviewed until the position is filled.</p>
        </main></html>"""
        e=evidence_from_lines(text_lines(html),"https://hubbardschool.umn.edu/work-hubbard-school")
        self.assertEqual(e["deadlineEvidence"][0]["date"],"2026-10-21")
        self.assertEqual(e["deadlineEvidence"][0]["type"],"priority")
        self.assertEqual({x["category"] for x in e["materialEvidence"]},{"cover_letter","cv"})
        self.assertNotIn("research_statement",{x["category"] for x in e["materialEvidence"]})

    def test_other_dates_are_not_application_deadlines(self):
        html="<main><p>Our program began January 3, 2026.</p><p>Fall term starts August 30, 2027.</p></main>"
        e=evidence_from_lines(text_lines(html),"https://example.edu/job/3")
        self.assertEqual(e["deadlineEvidence"],[])

    def test_links_follow_apply_not_policy(self):
        html="""<main><a href="/privacy">Privacy</a>
        <a href="https://hr.myu.umn.edu/jobs/ext/376189">UMN Careers: full job description</a>
        <a href="/jobs">Browse jobs</a></main>"""
        matches=application_links(html,"https://hubbardschool.umn.edu/work-hubbard-school")
        self.assertEqual(matches[0]["url"],"https://hr.myu.umn.edu/jobs/ext/376189")
        self.assertEqual(len(matches),1)

    def test_ambiguous_dates_not_fabricated(self):
        self.assertEqual(date_value("Priority review begins Oct 21"),"")
        self.assertEqual(date_value("Review starts November 25, 2026"),"2026-11-25")

    def test_no_material_inference_from_job_description(self):
        html="""<main><p>Successful applicants will teach curriculum development.</p>
        <p>The position involves research and teaching philosophy.</p></main>"""
        e=evidence_from_lines(text_lines(html),"https://example.edu")
        self.assertEqual(e["materialEvidence"],[])
    def test_board_listing_expiry_is_not_employer_deadline(self):
        e=evidence_from_lines([
            "Assistant Professor of Organizational Communication",
            "Posted: Jul 29, 2026 Apply By: Open until filled",
            "Screening of applicants will begin September 15, 2026.",
            "Applications will continue until the position is filled."],
            "https://jobs.chronicle.com/job/38051792/role")
        self.assertEqual([(x["date"],x["type"]) for x in e["deadlineEvidence"]],
                         [("2026-09-15","review")])

class DeadlineRegressionTests(unittest.TestCase):
    def evidence(self,text):
        return evidence_from_lines(text.splitlines(),"https://example.edu/jobs/123", "official-job-call")["deadlineEvidence"]

    def test_invalid_dates_and_missing_year_stay_unknown(self):
        for value in ("2026-02-30", "Deadline November 31, 2026", "Deadline October 26"):
            self.assertEqual(date_value(value), "")

    def test_full_consideration_is_not_hard_close(self):
        item=self.evidence("Applications must be received by October 26, 2026 for full consideration.")[0]
        self.assertEqual((item["date"], item["type"]),("2026-10-26","full_consideration"))
        self.assertIn("full consideration",item["evidence"])

    def test_review_start_distinct(self):
        item=self.evidence("Review of applications will begin November 2, 2026. Open until filled.")[0]
        self.assertEqual(item["type"],"review")

    def test_priority_and_closing_retained_together(self):
        from detail_extract import resolve_deadlines
        items=self.evidence("Deadline: October 31, 2026 23:59:59 EDT. Priority consideration October 6, 2026.")
        self.assertEqual({(x["date"],x["type"]) for x in items},
                         {("2026-10-31","closing"),("2026-10-06","priority")})
        result=resolve_deadlines(items)
        self.assertEqual(result["status"],"resolved")
        self.assertEqual(result["selected"]["timeText"],"23:59:59")
        self.assertEqual(result["selected"]["timezoneText"],"EDT")

    def test_time_before_date_preserved_without_timezone_invention(self):
        item=self.evidence("Applications must be received by 6:00 pm (Central Time) on November 1, 2026.")[0]
        self.assertEqual(item["timeText"],"6:00 pm")
        self.assertEqual(item["timezoneText"],"Central Time")
        self.assertNotIn("timezoneText",self.evidence("Deadline November 1, 2026")[0])

    def test_submission_instruction_with_portal_before_date(self):
        item=self.evidence("All materials should be submitted via Interfolio by September 1, 2026.")[0]
        self.assertEqual((item["date"],item["type"]),("2026-09-01","closing"))

    def test_start_date_and_posted_date_not_inherited(self):
        items=self.evidence("Posted July 1, 2026; expected start date August 16, 2027. Application Deadline Information. Applications must be received by November 1, 2026.")
        self.assertEqual([x["date"] for x in items],["2026-11-01"])

    def test_deadline_does_not_spill_into_later_unrelated_date(self):
        from detail_extract import resolve_deadlines
        for label in ("appointment beginning", "start date", "posted", "published", "listing expires", "valid through"):
            with self.subTest(label=label):
                items=self.evidence(f"Application deadline November 1, 2026, with {label} August 16, 2027.")
                self.assertEqual([(x["date"],x["type"]) for x in items],[("2026-11-01","closing")])
                self.assertEqual(resolve_deadlines(items)["status"],"resolved")

    def test_date_heading_on_previous_line(self):
        self.assertEqual(self.evidence("Application Deadline\nOctober 31, 2026 23:59:59 EDT")[0]["date"],"2026-10-31")

    def test_conflicting_closing_dates_not_arbitrarily_selected(self):
        from detail_extract import resolve_deadlines
        result=resolve_deadlines(self.evidence("Deadline October 24, 2026. Deadline October 31, 2026."))
        self.assertEqual(result["status"],"conflict")
        self.assertIsNone(result["selected"])

    def test_metadata_expiry_cannot_become_application_deadline(self):
        from detail_extract import resolve_deadlines
        self.assertEqual(resolve_deadlines([{"date":"2026-10-24","type":"closing","source":"structured-data"}])["status"],"unverified")

    def test_conflicting_cutoff_times_not_silently_dropped(self):
        from detail_extract import resolve_deadlines
        items=self.evidence("Deadline October 31, 2026 at 5:00 pm EDT. Deadline October 31, 2026 at 11:59 pm EDT.")
        self.assertEqual(resolve_deadlines(items)["status"],"conflict")

    def test_application_close_phrase(self):
        self.assertEqual(self.evidence("Applications will close November 30, 2026.")[0]["type"],"closing")

    def test_authoritative_conflict_retained(self):
        from detail_extract import resolve_deadlines
        board={"date":"2026-10-24","type":"closing","source":"job-board","url":"https://board.example/job"}
        official=self.evidence("Deadline October 31, 2026.")[0]
        result=resolve_deadlines([board,official])
        self.assertEqual(result["status"],"resolved_with_conflict")
        self.assertEqual(result["selected"]["date"],"2026-10-31")
        self.assertEqual(result["conflicts"],[board])

if __name__=="__main__":
    unittest.main()
