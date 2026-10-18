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
if __name__=="__main__":
    unittest.main()
