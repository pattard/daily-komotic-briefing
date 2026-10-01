"""Editorial regression fixtures are fictional and require no external services."""
from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

from briefing.common import settings
from briefing.editor import edit
from briefing.sources import article, collect, score_article
from briefing.state import MemoryStore
from test_briefing import FakeAPI, FakePublic, NOW, SOURCE, item, report


ALIASES = ['WEBTOON', 'GlobalComix', 'IDW', 'Madefire']


class RelevanceTests(unittest.TestCase):
    def check(self, title, text, qualifies, signal=None, **source_fields):
        a = article(dict(SOURCE, **source_fields), title, 'https://news.example/story',
                    '2026-09-29T10:00:00Z', text)
        score = score_article(a, ALIASES)
        self.assertEqual(score >= settings()['candidate_min_score'], qualifies, a.relevance)
        self.assertEqual(a.relevance['business_materiality'], qualifies, a.relevance)
        if signal:
            self.assertIn(signal, a.relevance['positive_signals'] if qualifies else a.relevance['negative_signals'])
        return a

    def test_comic_review(self):
        self.check('Review: A new comic from Image Comics',
                   'The publisher launches a new series with striking art and familiar characters.', False, 'review_recap')

    def test_bestseller_list(self):
        self.check('Bestseller roundup: WEBTOON tops the charts',
                   'The list ranks popular titles available on the digital comics platform.', False, 'bestseller_roundup')

    def test_creator_interview(self):
        self.check('Interview: A creator discusses a new graphic novel',
                   'The artist talks about drawing panels, lettering and publishing the new title.', False, 'interview_profile')

    def test_interview_about_creator_publishing_a_title_is_excluded(self):
        self.check('Interview: a creator discusses publishing a new comic',
                   'The creator talks about publishing a new graphic novel and drawing its characters.', False)

    def test_crowdfunding_spotlight(self):
        self.check('Crowdfunding spotlight: A new comic launches on Kickstarter',
                   'The campaign offers a graphic novel, signed rewards and a digital edition.', False, 'crowdfunding_spotlight')

    def test_title_promo_announcement(self):
        self.check('IDW announces a new comic series',
                   'The publisher launches a new graphic novel featuring a popular hero.', False, 'title_issue_promo')

    def test_adaptation_announcement(self):
        self.check('WEBTOON announces a Netflix adaptation',
                   'A licensing partnership with the studio brings a comic to television.', False, 'adaptation')

    def test_preview_convention_and_promotional_roundup(self):
        for title in ['Preview: issue #2', 'Convention roundup: publisher signings',
                      'Promotional roundup: things to read this weekend', 'Recap: new comic book day']:
            with self.subTest(title=title):
                self.check(title, 'A selection of comic titles and appearances by their creators.', False)

    def test_comic_social_style_app_launch(self):
        self.check('Comic Social Announces Launch of a Dedicated App Built exclusively for Comic Readers',
                   'Comic Social launches a dedicated app for comic readers with a digital reading catalogue.',
                   True, 'platform_launch_change')

    def test_platform_shutdown(self):
        self.check('Madefire shuts down', 'The platform is closing and the reading service will cease operations.',
                   True, 'closure_restructuring')

    def test_acquisition(self):
        self.check('Comics publisher acquires a rival company',
                   'The company has acquired the rival publisher and its publishing operations.', True, 'acquisition_merger')

    def test_creator_revenue_share_change(self):
        self.check('WEBTOON changes creator revenue share',
                   'The company is revising creator revenue-sharing terms for digital comic sales.', True, 'creator_economics')

    def test_paid_download_and_ownership(self):
        self.check('GlobalComix introduces paid downloads with permanent ownership',
                   'The platform now offers DRM-free downloads that readers can keep permanently.', True, 'ownership_download_drm')

    def test_creator_publishing_tool(self):
        self.check('New creator publishing tool simplifies comic uploads',
                   'The company introduces a new creator dashboard and publishing tools for digital comics.', True, 'creator_tools')

    def test_distribution_partnership(self):
        self.check('Comics distributor signs a distribution partnership',
                   'The agreement brings the publisher catalogue to digital libraries.', True, 'distribution_licensing_partnership')

    def test_localisation_and_accessibility(self):
        self.check('Comics app adds localisation and accessibility features',
                   'The service introduces screen reader support and new localisation tools.', True, 'accessibility_localisation')

    def test_market_expansion(self):
        self.check('Comics platform expands into Canada and the UK',
                   'The service is entering English-language markets with local payment support.', True, 'market_expansion')

    def test_watchlist_major_change(self):
        self.check('WEBTOON acquires PanelPort',
                   'WEBTOON acquires PanelPort in a deal covering its entire business.', True, 'acquisition_merger')

    def test_funding_round(self):
        self.check('Comics platform raises Series A funding',
                   'The company has secured a funding round to build digital comics tools.', True, 'funding')

    def test_merger_and_restructuring(self):
        self.check('Comic publishers merge their businesses',
                   'The companies announce a merger of their publishing operations.', True, 'acquisition_merger')
        self.check('Comics publisher announces restructuring and layoffs',
                   'The company is restructuring its distribution operations.', True, 'closure_restructuring')

    def test_subscription_and_commission_changes(self):
        self.check('Reader subscription pricing changes',
                   'The platform raises subscription pricing and removes a payment option.', True, 'monetisation_pricing')
        self.check('Marketplace cuts creator sales commission',
                   'The company reduces its sales commission on creator purchases.', True, 'creator_economics')

    def test_responsive_and_adaptive_reading_features(self):
        self.check('New adaptive comics reading engine',
                   'The service introduces responsive panel layouts and guided-view navigation.', True, 'reading_technology')

    def test_licensing_partnership(self):
        self.check('Publisher signs a comics licensing partnership',
                   'The agreement licences the publisher catalogue to a digital comics platform.',
                   True, 'distribution_licensing_partnership')

    def test_crowdfunding_funding_for_a_title_is_excluded(self):
        self.check('Kickstarter raises funding for a new graphic novel',
                   'The artist secures funding for a comic with signed rewards for backers.', False)

    def test_platform_crowdfunding_with_material_product_details_qualifies(self):
        self.check('Crowdfunding spotlight: new comics platform',
                   'The platform launches a new reading app with permanent downloads and creator publishing tools.',
                   True, 'platform_launch_change')

    def test_title_licensing_for_tv_is_excluded(self):
        self.check('A comic gets a new screen rights deal',
                   'The studio signs a licensing agreement to turn the comic into a television series.', False)

    def test_adaptation_report_with_real_comics_distribution_deal_qualifies(self):
        self.check('Adaptation news and a new comics distribution deal',
                   'The company signs a distribution partnership covering its digital comics catalogue. '
                   'An unrelated adaptation will also reach television.', True, 'distribution_licensing_partnership')

    def test_watchlist_leadership_and_contract_changes(self):
        self.check('WEBTOON appoints a new CEO',
                   'WEBTOON appoints a new chief executive after a strategic review.', True, 'watchlist_business_change')
        self.check('GlobalComix revises publishing terms',
                   'GlobalComix changes its creator contracts and publishing terms.', True, 'watchlist_business_change')

    def test_non_watchlist_platform_launch_can_qualify_from_headline(self):
        self.check('PanelPort launches a new comics platform', '', True, 'platform_launch_change')

    def test_watchlist_mention_alone_never_qualifies(self):
        for kind in ['official', 'trade']:
            with self.subTest(kind=kind):
                self.check('WEBTOON celebrates a favourite creator',
                           'WEBTOON highlights popular comics and the artists behind them.', False, source_kind=kind, region='US')

    def test_interview_with_actual_acquisition_qualifies(self):
        self.check('Interview: WEBTOON executive explains platform acquisition',
                   'The company has acquired a rival platform and will integrate its reader technology.', True, 'acquisition_merger')

    def test_review_with_actual_creator_terms_change_qualifies(self):
        self.check('Review and interview: new creator terms at GlobalComix',
                   'GlobalComix changes creator revenue share and introduces permanent paid downloads.', True, 'creator_economics')

    def test_idw_teaser_without_details_is_excluded(self):
        self.check('IDW teases something big for its publishing platform',
                   'The company says to stay tuned. More information is coming soon.', False, 'preview')

    def test_launch_teaser_needs_substantive_detail(self):
        self.check('WEBTOON teases a new app', 'More details soon. Stay tuned for a mystery announcement.', False)
        self.check('WEBTOON teases a new app',
                   'The app will introduce permanent paid downloads and allow readers to keep purchased comics.',
                   True, 'ownership_download_drm')

    def test_routine_platform_title_release_is_excluded(self):
        self.check('WEBTOON launches a new comic series on its platform',
                   'The publisher introduces a new title on the digital reading platform.', False)

    def test_title_promo_with_ordinary_download_and_price_is_excluded(self):
        self.check('Publisher announces a new graphic novel',
                   'The new graphic novel offers digital downloads with pricing announced for the print edition.', False)
        self.check('WEBTOON introduces a new graphic novel',
                   'The platform launches a new graphic novel available as a digital download.', False)

    def test_review_with_real_ownership_model_change_qualifies(self):
        self.check('Review: GlobalComix introduces a new ownership model',
                   'The platform now offers permanent DRM-free downloads for purchased comics.',
                   True, 'ownership_download_drm')

    def test_passing_terms_in_unrelated_sentences_do_not_qualify(self):
        self.check('Interview with an artist',
                   'The company has many comics. The hero acquires new powers. Fans discuss funding. '
                   'The platform is popular. A new story launches today.', False)

    def test_repeated_keywords_cannot_manufacture_materiality(self):
        self.check('Publisher news', 'platform digital launch licensing publisher ' * 25, False)

    def test_french_material_signals(self):
        self.check('Une nouvelle plateforme de lecture lance son application',
                   'La plateforme annonce une nouvelle application de lecture et ajoute des outils de publication.',
                   True, 'platform_launch_change', language='fr', region='EU')

    def test_spanish_material_signals(self):
        self.check('La plataforma anuncia nuevas herramientas para creadores',
                   'La empresa lanza una nueva aplicación y añade herramientas de publicación para creadores.',
                   True, 'platform_launch_change', language='es', region='EU')

    def test_french_and_spanish_reviews_are_excluded(self):
        self.check('Critique : le nouvel album du mois', 'Une chronique sur le dessin et les personnages.', False, language='fr')
        self.check('Reseña: entrevista sobre un nuevo cómic', 'El autor habla del dibujo de su novela gráfica.', False, language='es')

    def test_priority_regions_rank_before_otherwise_equal_regions(self):
        title, text = 'New comics app launches', 'The company launches a new app for comic reading.'
        scores = [score_article(article(dict(SOURCE, region=region), title, 'https://news.example/a', excerpt=text), [])
                  for region in ['US', 'UK', 'CA', 'EU', 'Asia']]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(len(set(scores)), 5)

    def collect_rows(self, rows, limit=20):
        cfg = dict(settings(), max_candidates=limit, min_healthy_sources=1)
        mapping = {SOURCE['url']: b'<rss/>'}
        mapping.update({a.url: page.encode() for a, page in rows})
        with patch('briefing.sources.parse_feed', return_value=copy.deepcopy([a for a, _ in rows])):
            return collect(FakePublic(mapping), [SOURCE], ALIASES, {}, NOW, cfg, True)

    def test_routine_candidates_never_reach_model(self):
        a = item('Review: WEBTOON graphic novel', 'The publisher launches a new series with charming artwork.')
        articles, collection = self.collect_rows([(a, '<article><p>Routine review</p></article>')])
        api = FakeAPI()
        value = edit(articles, collection, settings(), MemoryStore(), NOW, 'filter-test', api, 'key')
        self.assertEqual(value['status'], 'quiet')
        self.assertFalse(api.calls)
        self.assertEqual(collection['score_omitted'], 1)
        self.assertEqual(collection['article_fetch_attempts'], 0)
        diagnostic = collection['relevance_exclusions'][0]
        self.assertEqual(diagnostic['stage'], 'feed')
        self.assertFalse(diagnostic['business_materiality'])
        self.assertEqual(diagnostic['exclusion_reason'], 'routine_without_material_development')
        self.assertNotIn(a.excerpt, json.dumps(collection))

    def test_full_page_relevance_rejection_backfills_next_candidate(self):
        bad = item('Creator spotlight', 'The company acquires a rival platform and introduces new creator publishing tools '
                   'with updated revenue-sharing terms.', url='https://news.example/bad')
        good = item('Comic Social announcement', 'The company launches a new app for comic reading.', url='https://news.example/good')
        routine = 'The creator discusses a graphic novel and its characters, drawing methods and artwork. ' * 5
        articles, collection = self.collect_rows([(bad, f'<article><p>{routine}</p></article>'),
                                                (good, f'<article><p>{good.excerpt * 5}</p></article>')], limit=1)
        self.assertEqual([a.id for a in articles], [good.id])
        self.assertEqual(collection['relevance_after_fetch_omitted'], 1)
        self.assertEqual(collection['backfill_fetches'], 1)
        self.assertEqual(collection['candidate_diagnostics'][0]['outcome'], 'irrelevant_after_fetch')
        self.assertEqual(collection['selection_stop_reason'], 'queue_exhausted')

    def test_relevance_exclusion_sample_is_bounded(self):
        rows = [(item('Review: new comic', 'The art is interesting.', url=f'https://news.example/{i}'), '') for i in range(40)]
        _, collection = self.collect_rows(rows)
        self.assertEqual(collection['score_omitted'], 40)
        self.assertEqual(len(collection['relevance_exclusions']), 25)
        self.assertEqual(collection['relevance_exclusion_counts']['routine_without_material_development'], 40)


if __name__ == '__main__':
    unittest.main()
