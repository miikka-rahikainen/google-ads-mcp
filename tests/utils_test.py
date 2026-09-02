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

"""Test cases for the utils module."""

import unittest
import os
from unittest.mock import MagicMock, patch
from google.ads.googleads.v25.enums.types.campaign_status import (
    CampaignStatusEnum,
)
from google.ads.googleads.v25.common.types.metrics import Metrics
from google.protobuf.field_mask_pb2 import FieldMask

from ads_mcp import utils


class TestUtils(unittest.TestCase):
    """Test cases for the utils module."""

    def test_format_output_value(self):
        """Tests that output values are formatted correctly."""

        self.assertEqual(
            utils.format_output_value(
                CampaignStatusEnum.CampaignStatus.ENABLED
            ),
            "ENABLED",
        )

    def test_format_output_value_primitive(self):
        """Tests that primitive values are returned as is."""
        self.assertEqual(utils.format_output_value(123), 123)
        self.assertEqual(utils.format_output_value("abc"), "abc")

    def test_format_output_value_message(self):
        """Tests that proto messages are converted to dict."""
        metrics = Metrics(clicks=10, impressions=100)
        formatted = utils.format_output_value(metrics)
        self.assertIsInstance(formatted, dict)
        self.assertEqual(formatted.get("clicks"), "10")
        self.assertEqual(formatted.get("impressions"), "100")

    def test_format_output_value_repeated_primitive(self):
        """Tests that repeated primitive values are formatted."""
        self.assertEqual(
            utils.format_output_value([1, 2, 3]),
            [1, 2, 3],
        )

    def test_format_output_value_repeated_message(self):
        """Tests that repeated proto messages are formatted."""
        metrics1 = Metrics(clicks=10)
        metrics2 = Metrics(clicks=20)
        formatted = utils.format_output_value([metrics1, metrics2])
        self.assertIsInstance(formatted, list)
        self.assertEqual(len(formatted), 2)
        self.assertEqual(formatted[0].get("clicks"), "10")
        self.assertEqual(formatted[1].get("clicks"), "20")

    def test_format_output_value_bare_protobuf(self):
        """Tests that bare protobuf messages are formatted correctly."""
        fm = FieldMask(paths=["foo", "bar"])
        formatted = utils.format_output_value(fm)
        self.assertEqual(formatted, "foo,bar")

    def test_prevent_stdio_inheritance(self):
        """Tests that prevent_stdio_inheritance sets stdin to DEVNULL if not specified."""
        import subprocess
        from unittest.mock import MagicMock, patch
        from ads_mcp.utils import prevent_stdio_inheritance

        mock_popen = MagicMock()
        with patch("subprocess.Popen", mock_popen):
            with prevent_stdio_inheritance():
                subprocess.Popen(["mock_cmd"])

        mock_popen.assert_called_once_with(
            ["mock_cmd"], stdin=subprocess.DEVNULL
        )

    def test_prevent_stdio_inheritance_explicit_stdin(self):
        """Tests that prevent_stdio_inheritance preserves explicit stdin."""
        import subprocess
        from unittest.mock import MagicMock, patch
        from ads_mcp.utils import prevent_stdio_inheritance

        mock_popen = MagicMock()
        with patch("subprocess.Popen", mock_popen):
            with prevent_stdio_inheritance():
                subprocess.Popen(["mock_cmd"], stdin=subprocess.PIPE)

        mock_popen.assert_called_once_with(["mock_cmd"], stdin=subprocess.PIPE)

    @patch("ads_mcp.utils.GoogleAdsClient")
    @patch("ads_mcp.utils._get_developer_token", return_value="dev-token")
    @patch("ads_mcp.utils._create_credentials")
    def test_googleads_client_uses_explicit_login_customer_id(
        self, mock_credentials, _mock_developer_token, mock_client
    ):
        """A request-level manager id overrides the deployment default."""
        credentials = MagicMock()
        mock_credentials.return_value = credentials

        with patch.dict(
            os.environ,
            {"GOOGLE_ADS_LOGIN_CUSTOMER_ID": "1111111111"},
            clear=False,
        ):
            utils._get_googleads_client(login_customer_id="4741284197")

        mock_client.assert_called_once_with(
            credentials=credentials,
            developer_token="dev-token",
            use_proto_plus=True,
            login_customer_id="4741284197",
        )

    @patch("ads_mcp.utils.GoogleAdsClient")
    @patch("ads_mcp.utils._get_developer_token", return_value="dev-token")
    @patch("ads_mcp.utils._create_credentials")
    def test_googleads_client_falls_back_to_environment_login_customer_id(
        self, mock_credentials, _mock_developer_token, mock_client
    ):
        """The environment setting remains supported when no override is supplied."""
        credentials = MagicMock()
        mock_credentials.return_value = credentials

        with patch.dict(
            os.environ,
            {"GOOGLE_ADS_LOGIN_CUSTOMER_ID": "2524599092"},
            clear=False,
        ):
            utils._get_googleads_client()

        mock_client.assert_called_once_with(
            credentials=credentials,
            developer_token="dev-token",
            use_proto_plus=True,
            login_customer_id="2524599092",
        )

    @patch("ads_mcp.utils._get_developer_token", return_value="dev-token")
    @patch("ads_mcp.utils._create_credentials")
    def test_googleads_client_rejects_invalid_login_customer_id(
        self, _mock_credentials, _mock_developer_token
    ):
        """Manager ids must be sent without punctuation."""
        with self.assertRaisesRegex(ValueError, "digits only"):
            utils._get_googleads_client(login_customer_id="474-128-4197")
