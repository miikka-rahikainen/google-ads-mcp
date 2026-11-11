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

"""Blocks Google Ads resources and fields that can contain personal data."""

import re

# Resources whose rows can contain personal data or user-level identifiers.
BLOCKED_RESOURCES = frozenset(
    {
        # Click-level data with GCLIDs.
        "click_view",
        # Raw search queries typed by users.
        "search_term_view",
        "campaign_search_term_view",
        "dynamic_search_ads_search_term_view",
        "paid_organic_search_term_view",
        "smart_campaign_search_term_view",
        "ai_max_search_term_ad_combination_view",
        # Audience lists.
        "user_list",
        "user_list_customer_type",
        # Contact details submitted through lead forms.
        "lead_form_submission_data",
        # Local Services leads, conversations, employees and verifications.
        "local_services_lead",
        "local_services_lead_conversation",
        "local_services_employee",
        "local_services_verification_artifact",
        # E-mail addresses of people with access to the account.
        "customer_user_access",
        "customer_user_access_invitation",
    }
)

# Individual fields with personal data on otherwise allowed resources.
BLOCKED_FIELDS = frozenset(
    {
        # E-mail address of the person who made a change.
        "change_event.user_email",
    }
)

_RESOURCE_NAME = re.compile(r"[a-z][a-z0-9_]*")


def _mentions(name: str, text: str) -> bool:
    # Identifier characters on either side mean a different, longer name,
    # e.g. campaign_search_term_view must not match search_term_view.
    pattern = rf"(?<![A-Za-z0-9_.]){re.escape(name)}(?![A-Za-z0-9_])"
    return re.search(pattern, text, re.IGNORECASE) is not None


def validate_resource_name(resource: str) -> None:
    """Raises ValueError unless ``resource`` is a single allowed resource name."""
    if not _RESOURCE_NAME.fullmatch(resource):
        raise ValueError(f"Invalid resource name: {resource!r}")
    if resource in BLOCKED_RESOURCES:
        raise ValueError(
            f"Resource '{resource}' is blocked because it can contain "
            "personal data."
        )


def find_blocked_references(query: str) -> list[str]:
    """Returns the blocked resources and fields referenced in a GAQL query.

    The whole query is scanned, so a blocked name is caught in any clause.
    A blocked name inside a string literal is also rejected, which errs on
    the side of blocking.
    """
    names = sorted(BLOCKED_RESOURCES) + sorted(BLOCKED_FIELDS)
    return [name for name in names if _mentions(name, query)]


def remove_blocked_resources(resource_list: str) -> str:
    """Removes blocked resources from a newline-separated resource list."""
    return "\n".join(
        line
        for line in resource_list.splitlines()
        if line.strip() not in BLOCKED_RESOURCES
    )
