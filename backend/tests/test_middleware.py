"""Tests for the game middleware system."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.game.movement_handler import MovementHandler, MovementResult
from app.game.search_handler import SearchHandler, SearchResult
from app.game.damage_extractor import DamageExtractor, DamageExtractionResult


class TestMovementHandler:
    """Test movement detection and resolution."""

    def test_detect_direction_go_north(self):
        """Test 'go north' detection."""
        handler = MovementHandler(MagicMock())
        result = handler._detect_direction("go north")
        assert result == "north"

    def test_detect_direction_abbreviation(self):
        """Test single-letter abbreviations."""
        handler = MovementHandler(MagicMock())
        assert handler._detect_direction("n") == "north"
        assert handler._detect_direction("s") == "south"
        assert handler._detect_direction("e") == "east"
        assert handler._detect_direction("w") == "west"

    def test_detect_direction_variants(self):
        """Test various movement phrases."""
        handler = MovementHandler(MagicMock())
        assert handler._detect_direction("walk east") == "east"
        assert handler._detect_direction("head south") == "south"
        assert handler._detect_direction("proceed west") == "west"
        assert handler._detect_direction("enter the door") == "door"

    def test_detect_no_movement(self):
        """Test non-movement input."""
        handler = MovementHandler(MagicMock())
        assert handler._detect_direction("attack the goblin") is None
        assert handler._detect_direction("search the room") is None
        assert handler._detect_direction("hello") is None

    def test_match_exit_direct(self):
        """Test direct exit matching."""
        handler = MovementHandler(MagicMock())
        exits = {"north": "2", "south": "1", "door": "3"}

        key, name = handler._match_exit("north", exits)
        assert key == "2"
        assert name == "north"

    def test_match_exit_partial(self):
        """Test partial exit matching."""
        handler = MovementHandler(MagicMock())
        exits = {"north passage": "Area 2", "south corridor": "Area 1"}

        key, name = handler._match_exit("north", exits)
        assert key == "2"
        assert name == "north passage"

    def test_extract_location_key(self):
        """Test location key extraction from destination strings."""
        handler = MovementHandler(MagicMock())

        assert handler._extract_location_key("2") == "2"
        assert handler._extract_location_key("Area 2") == "2"
        assert handler._extract_location_key("Kitchen (Area 3)") == "3"
        assert handler._extract_location_key("4a") == "4a"


class TestSearchHandler:
    """Test search detection and resolution."""

    def test_detect_search_basic(self):
        """Test basic search detection."""
        handler = SearchHandler(MagicMock())

        # "search the room" extracts "the room" as target, making it "specific"
        is_search, stype, target = handler._detect_search("search the room")
        assert is_search is True
        assert stype == "specific"

        # "search around" without specific target would be general
        is_search2, stype2, target2 = handler._detect_search("search")
        assert is_search2 is True

    def test_detect_search_treasure(self):
        """Test treasure-specific search."""
        handler = SearchHandler(MagicMock())

        is_search, stype, target = handler._detect_search("search for treasure")
        assert is_search is True
        assert stype == "treasure"

    def test_detect_search_secrets(self):
        """Test secret-specific search."""
        handler = SearchHandler(MagicMock())

        is_search, stype, target = handler._detect_search("search for secret doors")
        assert is_search is True
        assert stype == "secrets"

    def test_detect_search_body(self):
        """Test body search."""
        handler = SearchHandler(MagicMock())

        is_search, stype, target = handler._detect_search("search the body")
        assert is_search is True
        assert stype == "body"

    def test_detect_no_search(self):
        """Test non-search input."""
        handler = SearchHandler(MagicMock())

        is_search, stype, target = handler._detect_search("go north")
        assert is_search is False

    def test_parse_gold_value(self):
        """Test gold value parsing."""
        handler = SearchHandler(MagicMock())

        assert handler._parse_gold_value("100 gp") == 100
        assert handler._parse_gold_value("1,000 gold") == 1000
        assert handler._parse_gold_value("50 gold pieces") == 50
        assert handler._parse_gold_value("25") == 25


class TestDamageExtractor:
    """Test damage extraction from LLM responses."""

    def test_extract_player_damage(self):
        """Test extracting damage to player."""
        extractor = DamageExtractor(MagicMock())

        events = extractor._extract_player_damage(
            "the goblin deals 5 damage to you",
            "TestPlayer"
        )
        assert len(events) == 1
        assert events[0].amount == 5
        assert events[0].target == "player"

    def test_extract_player_damage_variants(self):
        """Test various damage phrase patterns."""
        extractor = DamageExtractor(MagicMock())

        # "you take X damage"
        events = extractor._extract_player_damage("you take 3 damage", "Player")
        assert len(events) == 1
        assert events[0].amount == 3

        # "hits you for X damage"
        events = extractor._extract_player_damage("the orc hits you for 7 damage", "Player")
        assert len(events) == 1
        assert events[0].amount == 7

    def test_extract_healing(self):
        """Test extracting healing."""
        extractor = DamageExtractor(MagicMock())

        events = extractor._extract_healing("you heal 5 hit points", "Player")
        assert len(events) == 1
        assert events[0].amount == -5  # Negative for healing

    def test_extract_full_response(self):
        """Test full response extraction."""
        extractor = DamageExtractor(MagicMock())

        result = extractor.extract(
            "The goblin swings its rusty sword and deals 4 damage to you!",
            [],  # No tool calls
            "TestPlayer"
        )

        assert result.player_damage_total == 4
        assert result.needs_application is True

    def test_extract_with_tool_call(self):
        """Test that existing tool calls are recognized."""
        extractor = DamageExtractor(MagicMock())

        tool_calls = [{
            "name": "apply_damage_or_healing",
            "input": {"target": "player", "amount": 4}
        }]

        result = extractor.extract(
            "The goblin deals 4 damage to you!",
            tool_calls,
            "TestPlayer"
        )

        # Damage was already applied via tool, so player_damage_total should be 0
        assert result.player_damage_total == 0
        # The tool was called
        assert "apply_damage_or_healing" in result.tool_calls_made


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
