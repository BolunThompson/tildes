# Copyright (c) 2019 Tildes contributors <code@tildes.net>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Contains the YoutubeScraper class."""

from datetime import timedelta
import re
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

from dateutil import parser
import requests

from tildes.enums import ScraperType
from tildes.models.scraper import ScraperResult


# Only parses the subset of ISO8601 durations that YouTube uses
# fmt: off
YOUTUBE_DURATION_REGEX = re.compile(
    "P"
    r"(?:(?P<days>\d+)D)?"
    "T"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?"
)
# fmt: on


class YoutubeScraper:
    """Scraper that uses the YouTube Data API."""

    def __init__(self, api_key: str):
        """Create a new scraper using the specified YouTube API key."""
        self.api_key = api_key

    def is_applicable(self, url: str) -> bool:
        """Return whether this scraper is applicable to a particular url."""
        parsed_url = urlparse(url)

        if parsed_url.hostname not in ("www.youtube.com", "youtube.com"):
            return False

        if parsed_url.path != "/watch":
            return False

        return True

    def scrape_url(self, url: str) -> ScraperResult:
        """Scrape a url and return the result."""
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        video_id = query_params["v"]

        if not video_id:
            raise ValueError("Invalid url, no video ID found.")

        params: Dict[str, Any] = {
            "key": self.api_key,
            "id": video_id,
            "part": "snippet,contentDetails,statistics",
        }

        response = requests.get(
            "https://www.googleapis.com/youtube/v3/videos", params=params, timeout=5
        )
        response.raise_for_status()

        return ScraperResult(url, ScraperType.YOUTUBE, response.json()["items"][0])

    @staticmethod
    def get_metadata_from_result(result: ScraperResult) -> Dict[str, Any]:
        """Get the metadata that we're interested in out of a scrape result."""
        if result.scraper_type != ScraperType.YOUTUBE:
            raise ValueError("Can't process a result from a different scraper.")

        metadata = {}

        snippet = result.data.get("snippet")

        if snippet.get("title"):
            metadata["title"] = snippet["title"]

        if snippet.get("description"):
            metadata["description"] = snippet["description"]

        if snippet.get("publishedAt"):
            published = parser.parse(snippet["publishedAt"], ignoretz=True)
            metadata["published"] = int(published.timestamp())

        if snippet.get("channelTitle"):
            metadata["authors"] = [snippet["channelTitle"]]

        content_details = result.data.get("contentDetails")

        if content_details.get("duration"):
            match = YOUTUBE_DURATION_REGEX.match(content_details["duration"])
            if not match:
                raise ValueError("Unable to parse duration")

            duration_components = {}

            # convert None to zero and all strings to integers
            for key, value in match.groupdict().items():
                if value is None:
                    duration_components[key] = 0
                else:
                    duration_components[key] = int(value)

            delta = timedelta(
                days=duration_components["days"],
                hours=duration_components["hours"],
                minutes=duration_components["minutes"],
                seconds=duration_components["seconds"],
            )

            # string version of timedelta always has hours, strip it off when it's zero
            duration = str(delta).lstrip("0:")

            metadata["duration"] = duration

        return metadata