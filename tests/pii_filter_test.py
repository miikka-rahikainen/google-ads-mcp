# Copyright 2026 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for blocking resources and fields with personal data."""

import unittest
from unittest.mock import MagicMock, patch

from fastmcp.exceptions import ToolError

import ads_mcp.utils as utils
from ads_mcp import pii_filter
from ads_mcp.tools import get_resource_metadata, search


class TestPiiFilter(unittest.TestCase):

    def test_blocked_resources_exist_in_api(self):
        # Catches typos: every blocked name must be a real queryable resource.
        with open(utils.get_gaql_resources_filepath()) as file:
            resources = {line.strip() for line in file if line.strip()}
        self.assertEqual(pii_filter.BLOCKED_RESOURCES - resources, set())

    def test_requested_resources_are_blocked(self):
        for name in ("click_view", "search_term_view", "user_list"):
            self.assertIn(name, pii_filter.BLOCKED_RESOURCES)

    def test_validate_resource_name(self):
        pii_filter.validate_resource_name("campaign")
        for bad in (
            "click_view",
            "user_list",
            "campaign, click_view",
            "campaign WHERE 1=1",
            "Campaign",
            "",
        ):
            with self.assertRaises(ValueError, msg=bad):
                pii_filter.validate_resource_name(bad)

    def test_finds_blocked_names_in_any_clause(self):
        queries = [
            "SELECT click_view.gclid FROM campaign",
            "SELECT campaign.id FROM campaign WHERE search_term_view.status = 'X'",
            "SELECT campaign.id FROM campaign ORDER BY USER_LIST.name",
            "SELECT change_event.user_email FROM change_event",
        ]
        for query in queries:
            self.assertTrue(pii_filter.find_blocked_references(query), query)

    def test_does_not_flag_allowed_names(self):
        queries = [
            "SELECT campaign.id FROM campaign",
            "SELECT change_event.change_date_time FROM change_event LIMIT 10",
            "SELECT campaign_search_term_insight.category_label "
            "FROM campaign_search_term_insight",
            "SELECT ad_group_criterion.user_list.user_list FROM ad_group_criterion",
        ]
        for query in queries:
            self.assertEqual(
                pii_filter.find_blocked_references(query), [], query
            )

    def test_longer_name_does_not_hide_blocked_name(self):
        found = pii_filter.find_blocked_references(
            "SELECT campaign_search_term_view.search_term "
            "FROM campaign_search_term_view"
        )
        self.assertEqual(found, ["campaign_search_term_view"])

    def test_remove_blocked_resources(self):
        listed = pii_filter.remove_blocked_resources(
            "campaign\nclick_view\nsearch_term_view\nuser_list\nad_group"
        )
        self.assertEqual(listed, "campaign\nad_group")


class TestSearchBlocking(unittest.TestCase):

    @patch("ads_mcp.utils.get_googleads_service")
    def test_blocked_resource_is_rejected_before_api_call(self, mock_service):
        for resource in ("click_view", "search_term_view", "user_list"):
            with self.assertRaises(ToolError, msg=resource):
                search.search(
                    customer_id="1234567890",
                    fields=[f"{resource}.resource_name"],
                    resource=resource,
                )
        mock_service.assert_not_called()

    @patch("ads_mcp.utils.get_googleads_service")
    def test_blocked_field_is_rejected_before_api_call(self, mock_service):
        with self.assertRaises(ToolError):
            search.search(
                customer_id="1234567890",
                fields=["change_event.user_email"],
                resource="change_event",
                limit=10,
            )
        mock_service.assert_not_called()

    def test_description_does_not_list_blocked_resources(self):
        listed = search.search.__doc__.split("### Valid resources", 1)[1]
        lines = {line.strip() for line in listed.splitlines()}
        for name in ("click_view", "search_term_view", "user_list"):
            self.assertNotIn(name, lines)
        self.assertIn("campaign", lines)


class TestMetadataBlocking(unittest.TestCase):

    @patch("ads_mcp.utils.get_googleads_service")
    def test_blocked_resource_is_rejected(self, mock_service):
        with self.assertRaises(ToolError):
            get_resource_metadata.get_resource_metadata("click_view")
        mock_service.assert_not_called()

    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_service")
    def test_blocked_field_is_removed(self, mock_service, mock_type):
        field = MagicMock(selectable=True, filterable=True, sortable=True)
        field.name = "change_event.user_email"
        other = MagicMock(selectable=True, filterable=True, sortable=True)
        other.name = "change_event.change_date_time"
        mock_service.return_value.search_google_ads_fields.side_effect = [
            [field, other],
            [],
        ]
        result = get_resource_metadata.get_resource_metadata("change_event")
        for key in ("selectable", "filterable", "sortable"):
            self.assertEqual(result[key], ["change_event.change_date_time"])


if __name__ == "__main__":
    unittest.main()
