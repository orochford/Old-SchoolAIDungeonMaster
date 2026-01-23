import { Calendar, Sun, Moon, Cloud, Clock, CalendarDays } from 'lucide-react'

interface TimeData {
  day: number
  month: number
  month_name: string
  year: number
  hour: number
  time_of_day: string
  formatted_date: string
  formatted_time: string
  moon_phase: string
  season: string
  weather: string
}

interface UpcomingEvent {
  id: string
  name: string
  description: string
  days_until: number
}

interface Props {
  timeData: TimeData | null
  upcomingEvents?: UpcomingEvent[]
}

export function CalendarPanel({ timeData, upcomingEvents = [] }: Props) {
  if (!timeData) {
    return null
  }

  const getTimeIcon = () => {
    const hour = timeData.hour
    if (hour >= 6 && hour < 18) {
      return <Sun className="w-4 h-4 text-yellow-400" />
    }
    return <Moon className="w-4 h-4 text-blue-300" />
  }

  const getMoonIcon = () => {
    const phase = timeData.moon_phase.toLowerCase()
    if (phase.includes('new')) {
      return '🌑'
    } else if (phase.includes('full')) {
      return '🌕'
    } else if (phase.includes('waxing crescent')) {
      return '🌒'
    } else if (phase.includes('first quarter')) {
      return '🌓'
    } else if (phase.includes('waxing gibbous')) {
      return '🌔'
    } else if (phase.includes('waning gibbous')) {
      return '🌖'
    } else if (phase.includes('last quarter')) {
      return '🌗'
    } else if (phase.includes('waning crescent')) {
      return '🌘'
    }
    return '🌙'
  }

  const getSeasonColor = () => {
    switch (timeData.season.toLowerCase()) {
      case 'winter':
        return 'text-blue-300'
      case 'spring':
        return 'text-green-400'
      case 'summer':
        return 'text-yellow-400'
      case 'autumn':
        return 'text-orange-400'
      default:
        return 'text-parchment-400'
    }
  }

  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-3">
        <Calendar className="w-4 h-4 text-parchment-400" />
        <h3 className="font-display text-sm text-parchment-100">Time & Calendar</h3>
      </div>

      {/* Date */}
      <div className="flex items-center gap-2 mb-2">
        <CalendarDays className="w-4 h-4 text-parchment-500" />
        <span className="text-parchment-200 text-sm">
          {timeData.formatted_date}
        </span>
      </div>

      {/* Time of Day */}
      <div className="flex items-center gap-2 mb-2">
        {getTimeIcon()}
        <span className="text-parchment-200 text-sm capitalize">
          {timeData.time_of_day} ({timeData.formatted_time})
        </span>
      </div>

      {/* Season */}
      <div className="flex items-center gap-2 mb-2">
        <Clock className="w-4 h-4 text-parchment-500" />
        <span className={`text-sm capitalize ${getSeasonColor()}`}>
          {timeData.season}
        </span>
      </div>

      {/* Moon Phase */}
      <div className="flex items-center gap-2 mb-2">
        <span className="text-base">{getMoonIcon()}</span>
        <span className="text-parchment-300 text-sm">
          {timeData.moon_phase}
        </span>
      </div>

      {/* Weather */}
      {timeData.weather && (
        <div className="flex items-center gap-2 mb-2">
          <Cloud className="w-4 h-4 text-parchment-500" />
          <span className="text-parchment-300 text-sm capitalize">
            {timeData.weather}
          </span>
        </div>
      )}

      {/* Upcoming Events */}
      {upcomingEvents.length > 0 && (
        <div className="mt-3 pt-3 border-t border-dungeon-600">
          <div className="text-parchment-500 text-xs uppercase tracking-wide mb-2">
            Upcoming Events
          </div>
          <div className="space-y-1">
            {upcomingEvents.slice(0, 3).map((event) => (
              <div
                key={event.id}
                className="flex items-center justify-between text-xs"
                title={event.description}
              >
                <span className="text-parchment-300 truncate max-w-[120px]">
                  {event.name}
                </span>
                <span className="text-parchment-500">
                  {event.days_until === 0
                    ? 'Today!'
                    : event.days_until === 1
                    ? 'Tomorrow'
                    : `${event.days_until} days`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
