'use client';

import { useMemo } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  startOfMonth,
  endOfMonth,
  startOfWeek,
  endOfWeek,
  eachDayOfInterval,
  format,
  isSameMonth,
  isSameDay,
  isToday,
  addMonths,
  subMonths,
} from 'date-fns';
import type { Outfit, OutfitSource } from '@/lib/hooks/use-outfits';

interface OutfitCalendarProps {
  year: number;
  month: number;
  outfits: Outfit[];
  selectedDate: Date | null;
  onSelectDate: (date: Date) => void;
  onMonthChange: (year: number, month: number) => void;
}

export function OutfitCalendar({
  year,
  month,
  outfits,
  selectedDate,
  onSelectDate,
  onMonthChange,
}: OutfitCalendarProps) {
  const currentMonth = new Date(year, month - 1, 1);

  // Build a map of date -> outfit sources for quick lookup
  const outfitsByDate = useMemo(() => {
    const map = new Map<string, Set<OutfitSource>>();
    outfits.forEach((outfit) => {
      const dateKey = outfit.scheduled_for;
      if (!dateKey) return;
      if (!map.has(dateKey)) {
        map.set(dateKey, new Set());
      }
      map.get(dateKey)!.add(outfit.source);
    });
    return map;
  }, [outfits]);

  // Generate calendar days
  const calendarDays = useMemo(() => {
    const monthStart = startOfMonth(currentMonth);
    const monthEnd = endOfMonth(currentMonth);
    const calendarStart = startOfWeek(monthStart, { weekStartsOn: 0 });
    const calendarEnd = endOfWeek(monthEnd, { weekStartsOn: 0 });

    return eachDayOfInterval({ start: calendarStart, end: calendarEnd });
  }, [currentMonth]);

  const handlePrevMonth = () => {
    const prev = subMonths(currentMonth, 1);
    onMonthChange(prev.getFullYear(), prev.getMonth() + 1);
  };

  const handleNextMonth = () => {
    const next = addMonths(currentMonth, 1);
    onMonthChange(next.getFullYear(), next.getMonth() + 1);
  };

  const weekDays = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];

  return (
    <div className="w-full">
      {/* Month navigation */}
      <div className="flex items-center justify-between mb-4">
        <Button variant="ghost" size="icon" onClick={handlePrevMonth}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <h3 className="font-semibold text-lg">
          {format(currentMonth, 'MMMM yyyy')}
        </h3>
        <Button variant="ghost" size="icon" onClick={handleNextMonth}>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>

      {/* Weekday headers */}
      <div className="grid grid-cols-7 mb-2">
        {weekDays.map((day) => (
          <div
            key={day}
            className="text-center text-xs text-muted-foreground font-medium py-1"
          >
            {day}
          </div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="grid grid-cols-7 gap-1">
        {calendarDays.map((day) => {
          const dateKey = format(day, 'yyyy-MM-dd');
          const sources = outfitsByDate.get(dateKey);
          const hasScheduled = sources?.has('scheduled');
          const hasOnDemand = sources?.has('on_demand') || sources?.has('manual');
          const isSelected = selectedDate && isSameDay(day, selectedDate);
          const isCurrentMonth = isSameMonth(day, currentMonth);
          const isDayToday = isToday(day);

          return (
            <button
              key={dateKey}
              type="button"
              onClick={() => onSelectDate(day)}
              className={cn(
                'relative h-10 w-full rounded-md text-sm transition-colors',
                'hover:bg-accent hover:text-accent-foreground',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                !isCurrentMonth && 'text-muted-foreground/50',
                isSelected && 'bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground',
                isDayToday && !isSelected && 'bg-accent font-semibold'
              )}
            >
              <span>{format(day, 'd')}</span>
              {/* Outfit indicators */}
              {sources && sources.size > 0 && (
                <div className="absolute bottom-1 left-1/2 -translate-x-1/2 flex gap-0.5">
                  {hasScheduled && (
                    <span
                      className={cn(
                        'w-1.5 h-1.5 rounded-full',
                        isSelected ? 'bg-primary-foreground' : 'bg-primary'
                      )}
                    />
                  )}
                  {hasOnDemand && (
                    <span
                      className={cn(
                        'w-1.5 h-1.5 rounded-full',
                        isSelected ? 'bg-primary-foreground' : 'bg-orange-500'
                      )}
                    />
                  )}
                </div>
              )}
            </button>
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-4 text-xs text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-primary" />
          <span>Scheduled</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-orange-500" />
          <span>On-demand</span>
        </div>
      </div>
    </div>
  );
}
