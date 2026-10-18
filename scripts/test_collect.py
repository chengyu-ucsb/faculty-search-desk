"""Offline regression tests for faculty job discovery and fit scoring."""
import unittest
from bs4 import BeautifulSoup
from collect import load_profile, rank_posting, split_title, parse_jsonld, normalize_url, compact_posting_details

class CollectorTests(unittest.TestCase):
    def test_prefixed_institution(self):
        self.assertEqual(split_title("Virginia Tech: Assistant Professor of Communication"),
                         ("Assistant Professor of Communication", "Virginia Tech"))

    def test_ordinary_title(self):
        self.assertEqual(split_title("Assistant Professor of Communication - Northwestern University"),
                         ("Assistant Professor of Communication", "Northwestern University"))

    def test_fit_rewards_actual_area(self):
        p=load_profile()
        relevant={"title":"Assistant Professor of Organizational Communication","institution":"University of Example","snippet":"Research on technology-mediated teams and collaboration"}
        unrelated={"title":"Assistant Professor of Medieval History","institution":"University of Example","snippet":"Research on medieval manuscripts"}
        self.assertGreater(rank_posting(relevant,p)[0],rank_posting(unrelated,p)[0])

    def test_adjunct_penalty(self):
        p=load_profile()
        regular={"title":"Assistant Professor of Communication","snippet":"Organizational communication"}
        adjunct={"title":"Adjunct Instructor of Communication, Part-Time","snippet":"Organizational communication"}
        self.assertLess(rank_posting(adjunct,p)[0],rank_posting(regular,p)[0])

    def test_rank_terms_not_research_fit(self):
        p = load_profile()
        job = {"title": "Tenure-Track Assistant Professor", "snippet": ""}
        self.assertEqual(rank_posting(job, p)[0], 0)

    def test_retains_late_application_instructions(self):
        detail = ("The department offers excellent campus resources. " * 160 +
                  "\nTo apply, submit a cover letter and curriculum vitae." +
                  " Additional information." * 100)
        text = compact_posting_details(detail)
        self.assertIn("To apply, submit a cover letter", text)
        self.assertLessEqual(len(text), 6500)

    def test_jsonld(self):
        html='''<script type="application/ld+json">{"@type":"JobPosting","title":"Assistant Professor of Communication","hiringOrganization":{"name":"Example University"},"jobLocation":{"address":{"addressLocality":"Dayton","addressRegion":"Ohio"}},"validThrough":"2026-11-20","description":"Organizational communication research."}</script>'''
        r=parse_jsonld(BeautifulSoup(html,'html.parser'),'https://jobs.example.edu/position/12345')
        self.assertEqual(r[0]['institution'],'Example University')
        self.assertEqual(r[0]['deadline'],'2026-11-20')
        self.assertIn('Dayton',r[0]['location'])

    def test_url_tracking_removed(self):
        self.assertEqual(normalize_url('https://example.edu/jobs/123?utm_source=mail'),
                         'https://example.edu/jobs/123')

if __name__=='__main__':
    unittest.main()
