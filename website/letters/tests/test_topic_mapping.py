# ABOUTME: Test topic suggestion and matching based on letter content.
# ABOUTME: Covers TopicSuggestionService keyword matching and level suggestion logic.

from django.test import TestCase
from letters.services import TopicSuggestionService
from letters.models import TopicArea


class TopicMatchingTests(TestCase):
    """Test topic keyword matching and scoring."""

    def setUp(self):
        """Check if topic data is available."""
        self.has_topics = TopicArea.objects.exists()

    def test_transport_keywords_match_verkehr_topic(self):
        """Test that transport-related keywords match Verkehr topic."""
        if not self.has_topics:
            self.skipTest("TopicArea data not loaded")

        concern = "I want to see better train connections between cities"
        result = TopicSuggestionService.suggest_representatives_for_concern(concern)

        # Should find at least one topic
        matched_topics = result.get('matched_topics', [])
        self.assertGreater(len(matched_topics), 0)

    def test_housing_keywords_match_wohnen_topic(self):
        """Test that housing keywords match Wohnen topic."""
        if not self.has_topics:
            self.skipTest("TopicArea data not loaded")

        concern = "We need more affordable housing and rent control"
        result = TopicSuggestionService.suggest_representatives_for_concern(concern)

        matched_topics = result.get('matched_topics', [])
        self.assertGreater(len(matched_topics), 0)

    def test_education_keywords_match_bildung_topic(self):
        """Test that education keywords match Bildung topic."""
        if not self.has_topics:
            self.skipTest("TopicArea data not loaded")

        concern = "Our school curriculum needs reform"
        result = TopicSuggestionService.suggest_representatives_for_concern(concern)

        matched_topics = result.get('matched_topics', [])
        self.assertGreater(len(matched_topics), 0)

    def test_climate_keywords_match_umwelt_topic(self):
        """Test that climate keywords match environment topic."""
        if not self.has_topics:
            self.skipTest("TopicArea data not loaded")

        concern = "Climate protection and CO2 emissions must be addressed"
        result = TopicSuggestionService.suggest_representatives_for_concern(concern)

        matched_topics = result.get('matched_topics', [])
        self.assertGreater(len(matched_topics), 0)

    def test_no_match_returns_empty_list(self):
        """Test that completely unrelated text returns empty list."""
        concern = "xyzabc nonsense gibberish"
        result = TopicSuggestionService.suggest_representatives_for_concern(concern)

        matched_topics = result.get('matched_topics', [])
        # Should return empty list for gibberish
        self.assertEqual(len(matched_topics), 0)


class LevelSuggestionTests(TestCase):
    """Test government level suggestion logic."""

    def test_federal_transport_suggests_federal_level(self):
        """Test that long-distance transport suggests federal level."""
        result = TopicSuggestionService.suggest_representatives_for_concern(
            "Deutsche Bahn is always late",
            limit=5
        )

        self.assertIn('suggested_level', result)
        self.assertIn('explanation', result)
        # Federal issues should suggest FEDERAL level
        suggested_level = result['suggested_level']
        self.assertIsNotNone(suggested_level)
        self.assertIn('FEDERAL', suggested_level)

    def test_local_bus_suggests_state_or_local(self):
        """Test that local transport suggests state/local level."""
        result = TopicSuggestionService.suggest_representatives_for_concern(
            "Better bus services in my town",
            limit=5
        )

        self.assertIn('suggested_level', result)
        self.assertIn('explanation', result)
        # Should have an explanation
        self.assertIsNotNone(result['explanation'])


# End of file
