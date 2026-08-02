import { useCallback, useEffect, useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, Calendar } from 'lucide-react'
import { formatDisplayDate, parseDate } from '../../lib/date'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '../ui/popover'
import dayjs from 'dayjs'

interface DateNavProps {
  dates: string[]
  current: string
  onChange: (date: string) => void
}

export function DateNav({ dates, current, onChange }: DateNavProps) {
  const idx = dates.indexOf(current)
  const canPrev = idx < dates.length - 1
  const canNext = idx > 0
  const [open, setOpen] = useState(false)

  const goPrev = useCallback(() => {
    if (canPrev) onChange(dates[idx + 1])
  }, [canPrev, dates, idx, onChange])

  const goNext = useCallback(() => {
    if (canNext) onChange(dates[idx - 1])
  }, [canNext, dates, idx, onChange])

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (open) return
      if (e.key === 'ArrowLeft') goPrev()
      if (e.key === 'ArrowRight') goNext()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [goPrev, goNext, open])

  const handleSelect = useCallback(
    (date: string) => {
      onChange(date)
      setOpen(false)
    },
    [onChange]
  )

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={goPrev}
        disabled={!canPrev}
        className="p-1.5 rounded-md hover:bg-muted disabled:opacity-20 disabled:cursor-not-allowed transition-colors cursor-pointer"
        data-test-id="date-prev"
      >
        <ChevronLeft className="w-4 h-4" />
      </button>

      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            className="flex items-center gap-2 px-3 py-1.5 rounded-md hover:bg-muted transition-colors cursor-pointer"
            data-test-id="date-picker-trigger"
          >
            <Calendar className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="font-mono text-sm tabular-nums tracking-tight">
              {formatDisplayDate(current)}
            </span>
          </button>
        </PopoverTrigger>
        <PopoverContent align="center" className="w-auto p-0">
          <CalendarPicker
            dates={dates}
            current={current}
            onSelect={handleSelect}
          />
        </PopoverContent>
      </Popover>

      <button
        onClick={goNext}
        disabled={!canNext}
        className="p-1.5 rounded-md hover:bg-muted disabled:opacity-20 disabled:cursor-not-allowed transition-colors cursor-pointer"
        data-test-id="date-next"
      >
        <ChevronRight className="w-4 h-4" />
      </button>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Mini calendar grid                                                 */
/* ------------------------------------------------------------------ */

interface CalendarPickerProps {
  dates: string[]
  current: string
  onSelect: (date: string) => void
}

const WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']

function CalendarPicker({ dates, current, onSelect }: CalendarPickerProps) {
  const currentParsed = parseDate(current)
  const [viewMonth, setViewMonth] = useState(currentParsed.month())
  const [viewYear, setViewYear] = useState(currentParsed.year())

  // Build a Set for O(1) lookup
  const dateSet = useMemo(() => new Set(dates), [dates])

  // Build calendar grid for the viewed month
  const weeks = useMemo(() => {
    const firstDay = dayjs()
      .year(viewYear)
      .month(viewMonth)
      .date(1)
      .startOf('day')
    const daysInMonth = firstDay.daysInMonth()

    // Monday=0 ... Sunday=6 (ISO week)
    const startDow = (firstDay.day() + 6) % 7

    const cells: (string | null)[] = []
    // Pad leading blanks
    for (let i = 0; i < startDow; i++) cells.push(null)
    // Fill days
    for (let d = 1; d <= daysInMonth; d++) {
      const iso = firstDay.date(d).format('YYYY-MM-DD')
      cells.push(iso)
    }
    // Pad trailing blanks to complete last week
    while (cells.length % 7 !== 0) cells.push(null)

    // Split into weeks of 7
    const rows: (string | null)[][] = []
    for (let i = 0; i < cells.length; i += 7) {
      rows.push(cells.slice(i, i + 7))
    }
    return rows
  }, [viewMonth, viewYear])

  const prevMonth = () => {
    if (viewMonth === 0) {
      setViewMonth(11)
      setViewYear(viewYear - 1)
    } else {
      setViewMonth(viewMonth - 1)
    }
  }

  const nextMonth = () => {
    if (viewMonth === 11) {
      setViewMonth(0)
      setViewYear(viewYear + 1)
    } else {
      setViewMonth(viewMonth + 1)
    }
  }

  const monthLabel = dayjs()
    .year(viewYear)
    .month(viewMonth)
    .format('MMM YYYY')

  return (
    <div className="p-3 select-none" data-test-id="calendar-picker">
      {/* Month nav */}
      <div className="flex items-center justify-between mb-2">
        <button
          onClick={prevMonth}
          className="p-1 rounded hover:bg-muted transition-colors cursor-pointer"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        <span className="text-sm font-medium tracking-tight">{monthLabel}</span>
        <button
          onClick={nextMonth}
          className="p-1 rounded hover:bg-muted transition-colors cursor-pointer"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>

      {/* Weekday headers */}
      <div className="grid grid-cols-7 mb-1">
        {WEEKDAYS.map((d) => (
          <span
            key={d}
            className="text-xs text-muted-foreground text-center font-medium"
          >
            {d}
          </span>
        ))}
      </div>

      {/* Day grid */}
      <div className="grid grid-cols-7">
        {weeks.flat().map((iso, i) => {
          if (!iso) {
            return <div key={`blank-${i}`} className="w-8 h-8" />
          }

          const available = dateSet.has(iso)
          const isSelected = iso === current
          const dayNum = dayjs(iso + 'T12:00:00').date()

          return (
            <button
              key={iso}
              disabled={!available}
              onClick={() => onSelect(iso)}
              className={`
                w-8 h-8 rounded-md text-xs font-mono relative
                flex items-center justify-center transition-colors
                ${
                  isSelected
                    ? 'bg-emerald-500/20 text-emerald-400 font-semibold'
                    : available
                      ? 'hover:bg-muted cursor-pointer text-foreground'
                      : 'text-zinc-600 cursor-not-allowed'
                }
              `}
              data-test-id={available ? `cal-day-${iso}` : undefined}
            >
              {dayNum}
              {available && !isSelected && (
                <span className="absolute bottom-1 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-emerald-500/50" />
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
