"""Service for managing in-game time and calendar."""

import random
import logging
from typing import Dict, Any, Optional, List, Tuple
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from sqlalchemy.exc import IntegrityError
from app.domains.campaigns.models import Campaign, CampaignCalendar, DEFAULT_CALENDAR_CONFIG

logger = logging.getLogger(__name__)


class CalendarService:
    """Manage in-game time, moon phases, weather, and events."""

    MOON_PHASES = [
        "New Moon",
        "Waxing Crescent",
        "First Quarter",
        "Waxing Gibbous",
        "Full Moon",
        "Waning Gibbous",
        "Last Quarter",
        "Waning Crescent",
    ]

    TIME_OF_DAY = {
        (0, 4): "midnight",
        (5, 6): "dawn",
        (7, 11): "morning",
        (12, 12): "midday",
        (13, 16): "afternoon",
        (17, 18): "dusk",
        (19, 21): "evening",
        (22, 23): "night",
    }

    WEATHER_BY_SEASON = {
        "winter": [
            ("clear and cold", 20),
            ("overcast", 25),
            ("light snow", 20),
            ("heavy snow", 10),
            ("blizzard", 5),
            ("freezing rain", 10),
            ("bitter cold", 10),
        ],
        "spring": [
            ("clear and mild", 25),
            ("partly cloudy", 20),
            ("light rain", 20),
            ("heavy rain", 10),
            ("thunderstorm", 10),
            ("fog", 10),
            ("overcast", 5),
        ],
        "summer": [
            ("clear and hot", 30),
            ("sunny", 25),
            ("partly cloudy", 15),
            ("humid and hazy", 10),
            ("thunderstorm", 10),
            ("hot and dry", 10),
        ],
        "autumn": [
            ("clear and cool", 25),
            ("partly cloudy", 20),
            ("overcast", 20),
            ("light rain", 15),
            ("foggy morning", 10),
            ("breezy", 10),
        ],
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_calendar(
        self,
        campaign_id: UUID
    ) -> CampaignCalendar:
        """Get existing calendar or create a new one for the campaign."""
        result = await self.db.execute(
            select(CampaignCalendar).where(CampaignCalendar.campaign_id == campaign_id)
        )
        calendar = result.scalar_one_or_none()

        if not calendar:
            try:
                # Use savepoint so we only rollback this insert, not the whole transaction
                async with self.db.begin_nested():
                    calendar = CampaignCalendar(
                        campaign_id=campaign_id,
                        calendar_config=DEFAULT_CALENDAR_CONFIG,
                    )
                    self.db.add(calendar)
                    await self.db.flush()
                await self.db.refresh(calendar)
            except IntegrityError:
                # Race condition - another request created the calendar
                # Savepoint already rolled back, just re-query
                result = await self.db.execute(
                    select(CampaignCalendar).where(CampaignCalendar.campaign_id == campaign_id)
                )
                calendar = result.scalar_one_or_none()

        return calendar

    async def advance_time(
        self,
        campaign_id: UUID,
        hours: int = 0,
        days: int = 0,
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        Advance time by specified hours and/or days.

        Returns a dict with:
        - old_time, new_time
        - day_changed, month_changed, year_changed
        - triggered_events
        - weather_change
        - moon_phase_change
        """
        calendar = await self.get_or_create_calendar(campaign_id)
        config = calendar.calendar_config or DEFAULT_CALENDAR_CONFIG

        # Store old values
        old_time = self._format_time(calendar, config)
        old_moon_phase = self.get_moon_phase(calendar.moon_day, config.get("moon_cycle_days", 28))

        # Calculate total hours to advance
        total_hours = hours + (days * config.get("hours_per_day", 24))

        # Track changes
        day_changed = False
        month_changed = False
        year_changed = False

        # Advance hours
        calendar.current_hour += total_hours
        hours_per_day = config.get("hours_per_day", 24)

        # Handle day overflow
        while calendar.current_hour >= hours_per_day:
            calendar.current_hour -= hours_per_day
            calendar.current_day += 1
            calendar.moon_day = (calendar.moon_day + 1) % config.get("moon_cycle_days", 28)
            day_changed = True

        # Handle month overflow
        months = config.get("months", DEFAULT_CALENDAR_CONFIG["months"])
        while True:
            current_month_days = months[calendar.current_month - 1]["days"]
            if calendar.current_day > current_month_days:
                calendar.current_day -= current_month_days
                calendar.current_month += 1
                month_changed = True

                # Handle year overflow
                if calendar.current_month > len(months):
                    calendar.current_month = 1
                    calendar.current_year += 1
                    year_changed = True
            else:
                break

        # Check for triggered events
        triggered_events = await self._check_triggered_events(calendar, config)

        # Update weather if day changed
        weather_change = None
        if day_changed:
            old_weather = calendar.current_weather
            new_weather = self.get_weather(calendar.current_month, config)
            if new_weather != old_weather:
                calendar.current_weather = new_weather
                weather_change = {"old": old_weather, "new": new_weather}

        # Save changes
        await self.db.flush()

        # Get new values
        new_time = self._format_time(calendar, config)
        new_moon_phase = self.get_moon_phase(calendar.moon_day, config.get("moon_cycle_days", 28))

        moon_phase_change = None
        if new_moon_phase != old_moon_phase:
            moon_phase_change = {"old": old_moon_phase, "new": new_moon_phase}

        return {
            "old_time": old_time,
            "new_time": new_time,
            "hours_advanced": total_hours,
            "day_changed": day_changed,
            "month_changed": month_changed,
            "year_changed": year_changed,
            "triggered_events": triggered_events,
            "weather_change": weather_change,
            "moon_phase_change": moon_phase_change,
            "reason": reason,
        }

    async def get_current_time(
        self,
        campaign_id: UUID
    ) -> Dict[str, Any]:
        """Get the current time, date, moon phase, and weather."""
        calendar = await self.get_or_create_calendar(campaign_id)
        config = calendar.calendar_config or DEFAULT_CALENDAR_CONFIG

        # Get current month info
        months = config.get("months", DEFAULT_CALENDAR_CONFIG["months"])
        current_month_name = months[calendar.current_month - 1]["name"]

        # Get time of day
        time_of_day = self.get_time_of_day(calendar.current_hour)

        # Get moon phase
        moon_phase = self.get_moon_phase(
            calendar.moon_day,
            config.get("moon_cycle_days", 28)
        )

        # Get season
        season = self._get_season(calendar.current_month, config)

        # Get weather (or generate if not set)
        if not calendar.current_weather:
            calendar.current_weather = self.get_weather(calendar.current_month, config)
            await self.db.flush()

        return {
            "day": calendar.current_day,
            "month": calendar.current_month,
            "month_name": current_month_name,
            "year": calendar.current_year,
            "hour": calendar.current_hour,
            "time_of_day": time_of_day,
            "formatted_date": f"Day {calendar.current_day} of {current_month_name}, Year {calendar.current_year}",
            "formatted_time": f"{calendar.current_hour:02d}:00",
            "moon_phase": moon_phase,
            "moon_day": calendar.moon_day,
            "season": season,
            "weather": calendar.current_weather,
        }

    async def schedule_event(
        self,
        campaign_id: UUID,
        name: str,
        day: int,
        month: int,
        year: Optional[int] = None,
        recurring: bool = False,
        description: str = "",
    ) -> Dict[str, Any]:
        """Schedule a future event."""
        import uuid

        calendar = await self.get_or_create_calendar(campaign_id)

        event = {
            "id": str(uuid.uuid4()),
            "name": name,
            "day": day,
            "month": month,
            "year": year,  # None for recurring yearly events
            "recurring": recurring,
            "triggered": False,
            "description": description,
        }

        events = list(calendar.scheduled_events or [])
        events.append(event)
        calendar.scheduled_events = events
        await self.db.flush()

        return {
            "success": True,
            "event": event,
        }

    async def get_upcoming_events(
        self,
        campaign_id: UUID,
        days_ahead: int = 30,
    ) -> List[Dict[str, Any]]:
        """Get events happening within the next N days."""
        calendar = await self.get_or_create_calendar(campaign_id)
        config = calendar.calendar_config or DEFAULT_CALENDAR_CONFIG

        events = calendar.scheduled_events or []
        upcoming = []

        # Calculate date range
        current_day = calendar.current_day
        current_month = calendar.current_month
        current_year = calendar.current_year

        for event in events:
            if event.get("triggered") and not event.get("recurring"):
                continue

            event_day = event.get("day", 1)
            event_month = event.get("month", 1)
            event_year = event.get("year")

            # Check if event is within range
            days_until = self._days_until_event(
                current_day, current_month, current_year,
                event_day, event_month, event_year,
                config
            )

            if days_until is not None and 0 <= days_until <= days_ahead:
                upcoming.append({
                    **event,
                    "days_until": days_until,
                })

        # Sort by days until
        upcoming.sort(key=lambda e: e.get("days_until", 999))
        return upcoming

    def get_moon_phase(self, moon_day: int, cycle_length: int = 28) -> str:
        """Calculate current moon phase from moon day."""
        phase_length = cycle_length / len(self.MOON_PHASES)
        phase_index = int(moon_day / phase_length) % len(self.MOON_PHASES)
        return self.MOON_PHASES[phase_index]

    def get_time_of_day(self, hour: int) -> str:
        """Get time of day description from hour."""
        for (start, end), name in self.TIME_OF_DAY.items():
            if start <= hour <= end:
                return name
        return "night"

    def get_weather(self, month: int, config: Dict[str, Any]) -> str:
        """Generate weather based on season."""
        season = self._get_season(month, config)
        weather_options = self.WEATHER_BY_SEASON.get(season, self.WEATHER_BY_SEASON["spring"])

        # Weighted random selection
        total_weight = sum(w for _, w in weather_options)
        roll = random.randint(1, total_weight)

        cumulative = 0
        for weather, weight in weather_options:
            cumulative += weight
            if roll <= cumulative:
                return weather

        return weather_options[0][0]

    def _get_season(self, month: int, config: Dict[str, Any]) -> str:
        """Determine season from month."""
        seasons = config.get("seasons", DEFAULT_CALENDAR_CONFIG["seasons"])
        for season_name, months in seasons.items():
            if month in months:
                return season_name
        return "spring"

    def _format_time(
        self,
        calendar: CampaignCalendar,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Format current time as a dict."""
        months = config.get("months", DEFAULT_CALENDAR_CONFIG["months"])
        month_name = months[calendar.current_month - 1]["name"]

        return {
            "day": calendar.current_day,
            "month": calendar.current_month,
            "month_name": month_name,
            "year": calendar.current_year,
            "hour": calendar.current_hour,
            "formatted": f"Day {calendar.current_day} of {month_name}, Year {calendar.current_year}, {calendar.current_hour:02d}:00",
        }

    async def _check_triggered_events(
        self,
        calendar: CampaignCalendar,
        config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Check and mark any events that should trigger."""
        events = list(calendar.scheduled_events or [])
        triggered = []

        for i, event in enumerate(events):
            if event.get("triggered") and not event.get("recurring"):
                continue

            event_day = event.get("day", 1)
            event_month = event.get("month", 1)
            event_year = event.get("year")

            # Check if event triggers today
            if (calendar.current_day == event_day and
                calendar.current_month == event_month and
                (event_year is None or calendar.current_year == event_year)):

                triggered.append(event)
                events[i]["triggered"] = True

        if triggered:
            calendar.scheduled_events = events

        return triggered

    def _days_until_event(
        self,
        current_day: int,
        current_month: int,
        current_year: int,
        event_day: int,
        event_month: int,
        event_year: Optional[int],
        config: Dict[str, Any],
    ) -> Optional[int]:
        """Calculate days until an event. Returns None if event has passed."""
        months = config.get("months", DEFAULT_CALENDAR_CONFIG["months"])

        # For yearly recurring events, use current or next year
        if event_year is None:
            if (event_month < current_month or
                (event_month == current_month and event_day < current_day)):
                event_year = current_year + 1
            else:
                event_year = current_year

        # If event year has passed, return None
        if event_year < current_year:
            return None
        if event_year == current_year and event_month < current_month:
            return None
        if (event_year == current_year and
            event_month == current_month and
            event_day < current_day):
            return None

        # Count days
        days = 0

        # Days remaining in current month
        if event_year == current_year and event_month == current_month:
            return event_day - current_day

        days += months[current_month - 1]["days"] - current_day

        # Add full months
        m = current_month + 1
        y = current_year
        while not (m == event_month and y == event_year):
            if m > len(months):
                m = 1
                y += 1
            days += months[m - 1]["days"]
            m += 1
            if days > 365:  # Safety limit
                break

        # Add days in event month
        days += event_day

        return days
