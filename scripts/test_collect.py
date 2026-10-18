"""Offline regression tests for faculty job discovery and fit scoring."""
import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup
from collect import load_profile, rank_posting, split_title, parse_jsonld, normalize_url, compact_posting_details, apply_scores, now_iso

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


    def test_follow_official_job_detail_for_requirements(self):
        j={"id":"123","title":"Assistant Professor of Organizational Communication",
           "institution":"Example University","url":"https://example.edu/news/communication-role",
           "firstSeen":now_iso(),"detailTries":0}
        first='<main><h1>Assistant Professor of Organizational Communication</h1><p>Opportunity at Example University.</p><a href="/jobs/123">Full job description</a></main>'
        full='<main><h1>Assistant Professor of Organizational Communication</h1><h2>How to Apply</h2><p>Submit a cover letter and CV.</p><p>Review of applications begins November 20, 2026.</p></main>'
        def resp(url):
            return {"text":full if url.endswith("/jobs/123") else first,
                    "content_type":"text/html","final_url":url,"blocked":False,"error":None}
        with patch("collect.robots_allowed",return_value=True), patch("collect.fetch",side_effect=resp), patch("collect.time.sleep"):
            apply_scores({"123":j},load_profile(),now_iso())
        self.assertEqual(j["deadline"],"2026-11-20")
        self.assertEqual(j["verifiedApplicationUrl"],"https://example.edu/jobs/123")
        self.assertEqual({x["category"] for x in j["applicationEvidence"]["materialEvidence"]},{"cover_letter","cv"})

    def test_wiki_entry_reads_linked_pdf_call_not_wiki_page(self):
        j={"id":"wiki123","title":"Assistant Professor of Organizational Communication",
           "institution":"Example University","url":"https://academicjobswiki.org/wiki/2026#Example",
           "adUrl":"https://example.edu/positions/2026-call.pdf",
           "statuses":["Applications open"],"firstSeen":now_iso()}
        pdf=("Example University Assistant Professor of Organizational Communication\n"
             "How to Apply\n"
             "Please submit a cover letter and curriculum vitae.\n"
             "Priority review begins October 21, 2026.")
        def resp(url):
            if url!=j["adUrl"]: raise AssertionError("Fetched wiki instead of the linked call")
            return {"text":pdf,"content_type":"application/pdf","final_url":url,"blocked":False,"error":None}
        with patch("collect.robots_allowed",return_value=True), patch("collect.fetch",side_effect=resp), patch("collect.time.sleep"):
            apply_scores({"wiki123":j},load_profile(),now_iso())
        self.assertEqual(j["applicationCoverage"],"deadline_and_materials")
        self.assertEqual(j["deadline"],"2026-10-21")
        self.assertEqual(j["verifiedApplicationUrl"],j["adUrl"])

    def test_ut_austin_wiki_heading_update_is_one_position(self):
        from collect import collapse_wiki_duplicates
        headline=("Assistant Professor in Organizational Communication & Technology, "
                  "Department of Communication, Moody College of Communication "
                  "(Deadline: 09/15/2026)")
        base={"sourceId":"academic-jobs-wiki","institution":"University of Texas, Austin (Austin, Texas)",
              "adUrl":"https://faculty.utexas.edu/career/188439"}
        old={"id":"4db9e22f2195","title":headline,
             "url":"https://academicjobs.fandom.com/wiki/Communication_and_Media_Studies_2026-2027#old",
             "firstSeen":"2026-09-07T17:20:46Z","lastSeen":"2026-10-08T17:54:55Z",
             "statuses":[],**base}
        update={"id":"91dffc54aeaf","title":headline+" ZOOM INTERVIEW INVITATIONS SENT OUT",
                "url":"https://academicjobs.fandom.com/wiki/Communication_and_Media_Studies_2026-2027#new",
                "firstSeen":"2026-10-09T17:28:48Z","lastSeen":"2026-10-18T15:11:34Z",
                "statuses":[],**base}
        # Chronicle's December posting is potentially distinct and must survive.
        chronicle={"id":"4291024f17f0","sourceId":"chronicle-communications",
                   "title":"Assistant Professor, Tenure-Track Faculty Position in Organizational Communication",
                   "institution":"University of Texas at Austin",
                   "jobNumber":"38051792","deadline":"2026-12-13",
                   "url":"https://jobs.chronicle.com/job/38051792/role",
                   "firstSeen":"2026-10-15T15:38:55Z"}
        jobs={j["id"]:j for j in (old,update,chronicle)}
        self.assertEqual(collapse_wiki_duplicates(jobs),1)
        self.assertEqual(set(jobs),{"4db9e22f2195","4291024f17f0"})
        survivor=jobs["4db9e22f2195"]
        self.assertEqual(survivor["deadline"],"2026-09-15")
        self.assertEqual(survivor["firstSeen"],"2026-09-07T17:20:46Z")
        self.assertEqual(survivor["lastSeen"],"2026-10-18T15:11:34Z")
        self.assertTrue(any("ZOOM INTERVIEW" in s for s in survivor["statuses"]))
        self.assertTrue(any("ZOOM INTERVIEW" in s for s in survivor["newStatuses"]))
        self.assertNotIn("ZOOM INTERVIEW",survivor["title"])
        self.assertNotIn("Deadline:",survivor["title"])
        self.assertEqual(collapse_wiki_duplicates(jobs),0)

    def test_generic_departmental_link_is_not_dedupe_proof(self):
        from collect import collapse_wiki_duplicates
        base={"sourceId":"academic-jobs-wiki",
              "adUrl":"https://faculty.utexas.edu/",
              "institution":"University of Texas at Austin",
              "firstSeen":"2026-09-07T12:00:00Z"}
        jobs={"a":{"id":"a","title":"Assistant Professor in Organizational Communication",**base},
              "b":{"id":"b","title":"Assistant Professor in Strategic Communication",**base}}
        self.assertEqual(collapse_wiki_duplicates(jobs),0)
        self.assertEqual(len(jobs),2)

    def test_wiki_parser_captures_heading_deadline_and_activity(self):
        from collect import parse_wikitext
        wiki="""== Tenure Track ==
=== University of Texas, Austin (Austin, Texas) - Assistant Professor in Organizational Communication & Technology (Deadline: 09/15/2026) ZOOM INTERVIEW INVITATIONS SENT OUT ===
* [https://faculty.utexas.edu/career/188439 Apply]
"""
        parsed=parse_wikitext(wiki,"https://academicjobs.fandom.com/wiki/Communication_and_Media_Studies_2026-2027","Communication and Media Studies 2026-2027")
        self.assertEqual(len(parsed),1)
        self.assertEqual(parsed[0]["deadline"],"2026-09-15")
        self.assertEqual(parsed[0]["title"],"Assistant Professor in Organizational Communication & Technology")
        self.assertIn("ZOOM INTERVIEW INVITATIONS SENT OUT",parsed[0]["statuses"])
        self.assertEqual(parsed[0]["adUrl"],"https://faculty.utexas.edu/career/188439")

if __name__=='__main__':
    unittest.main()
