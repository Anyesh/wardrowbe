'use client';

import { useState, useMemo } from 'react';
import { Calendar } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useCalendarOutfits, type Outfit, type OutfitFilters } from '@/lib/hooks/use-outfits';
import { OutfitCalendar } from '@/components/outfit-calendar';
import { OutfitHistoryCard } from '@/components/outfit-history-card';
import { FeedbackDialog } from '@/components/feedback-dialog';
import { OutfitPreviewDialog } from '@/components/outfit-preview-dialog';
import { format, isSameDay, parseISO } from 'date-fns';

function EmptyHistory() {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      <div className="rounded-full bg-muted p-6 mb-4">
        <Calendar className="h-12 w-12 text-muted-foreground" />
      </div>
      <h3 className="text-lg font-semibold mb-2">No recommendation history</h3>
      <p className="text-muted-foreground mb-6 max-w-sm">
        Your outfit recommendation history will appear here once you start
        receiving suggestions.
      </p>
      <Button variant="outline" asChild>
        <a href="/dashboard/suggest">Get Your First Suggestion</a>
      </Button>
    </div>
  );
}

function EmptyDate({ date }: { date: Date }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 px-4 text-center">
      <Calendar className="h-8 w-8 text-muted-foreground mb-2" />
      <p className="text-sm text-muted-foreground">
        No outfits for {format(date, 'MMMM d, yyyy')}
      </p>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      {[1, 2, 3].map((i) => (
        <Card key={i}>
          <CardContent className="p-4">
            <div className="flex items-start justify-between mb-3">
              <div>
                <Skeleton className="h-5 w-24 mb-2" />
                <Skeleton className="h-5 w-16" />
              </div>
              <Skeleton className="h-5 w-5" />
            </div>
            <div className="flex gap-2">
              {[1, 2, 3].map((j) => (
                <Skeleton key={j} className="w-16 h-16 rounded" />
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function CalendarSkeleton() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-4">
        <Skeleton className="h-8 w-8" />
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-8 w-8" />
      </div>
      <div className="grid grid-cols-7 gap-1">
        {[...Array(35)].map((_, i) => (
          <Skeleton key={i} className="h-10 w-full rounded-md" />
        ))}
      </div>
    </div>
  );
}

export default function HistoryPage() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [selectedDate, setSelectedDate] = useState<Date | null>(now);
  const [filters, setFilters] = useState<OutfitFilters>({});
  const [feedbackOutfit, setFeedbackOutfit] = useState<Outfit | null>(null);
  const [previewOutfit, setPreviewOutfit] = useState<Outfit | null>(null);

  const { data, isLoading, isError } = useCalendarOutfits(year, month, filters);

  // Filter outfits for the selected date
  const selectedDateOutfits = useMemo(() => {
    if (!data?.outfits || !selectedDate) return [];
    return data.outfits.filter((outfit) =>
      outfit.scheduled_for && isSameDay(parseISO(outfit.scheduled_for), selectedDate)
    );
  }, [data?.outfits, selectedDate]);

  const handleMonthChange = (newYear: number, newMonth: number) => {
    setYear(newYear);
    setMonth(newMonth);
  };

  const handleOccasionChange = (value: string) => {
    setFilters((prev) => ({
      ...prev,
      occasion: value === 'all' ? undefined : value,
    }));
  };

  const handleStatusChange = (value: string) => {
    setFilters((prev) => ({
      ...prev,
      status: value === 'all' ? undefined : value,
    }));
  };

  if (isError) {
    return (
      <div className="text-center py-8 text-red-500">
        Failed to load history. Please try again.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">History</h1>
          <p className="text-muted-foreground">
            View your past outfit recommendations
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <Select value={filters.occasion || 'all'} onValueChange={handleOccasionChange}>
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="All occasions" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All occasions</SelectItem>
            <SelectItem value="casual">Casual</SelectItem>
            <SelectItem value="office">Office</SelectItem>
            <SelectItem value="formal">Formal</SelectItem>
            <SelectItem value="date">Date</SelectItem>
            <SelectItem value="workout">Workout</SelectItem>
          </SelectContent>
        </Select>
        <Select value={filters.status || 'all'} onValueChange={handleStatusChange}>
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="All status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All status</SelectItem>
            <SelectItem value="accepted">Accepted</SelectItem>
            <SelectItem value="rejected">Rejected</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="viewed">Viewed</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Main content - two column layout */}
      <div className="grid lg:grid-cols-[350px_1fr] gap-6">
        {/* Calendar column */}
        <Card className="h-fit order-2 lg:order-1">
          <CardContent className="p-4">
            {isLoading ? (
              <CalendarSkeleton />
            ) : (
              <OutfitCalendar
                year={year}
                month={month}
                outfits={data?.outfits || []}
                selectedDate={selectedDate}
                onSelectDate={setSelectedDate}
                onMonthChange={handleMonthChange}
              />
            )}
          </CardContent>
        </Card>

        {/* Outfits column */}
        <div className="order-1 lg:order-2 space-y-4">
          {/* Selected date header */}
          {selectedDate && (
            <div className="border-b pb-3">
              <h2 className="text-lg font-semibold">
                {format(selectedDate, 'EEEE, MMMM d')}
              </h2>
              <p className="text-sm text-muted-foreground">
                {selectedDateOutfits.length} outfit{selectedDateOutfits.length !== 1 ? 's' : ''}
              </p>
            </div>
          )}

          {isLoading ? (
            <LoadingSkeleton />
          ) : !data || data.outfits.length === 0 ? (
            <EmptyHistory />
          ) : selectedDate && selectedDateOutfits.length === 0 ? (
            <EmptyDate date={selectedDate} />
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              {selectedDateOutfits.map((outfit) => (
                <OutfitHistoryCard
                  key={outfit.id}
                  outfit={outfit}
                  onFeedback={() => setFeedbackOutfit(outfit)}
                  onPreview={() => setPreviewOutfit(outfit)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Feedback dialog */}
      {feedbackOutfit && (
        <FeedbackDialog
          outfit={feedbackOutfit}
          open={!!feedbackOutfit}
          onClose={() => setFeedbackOutfit(null)}
        />
      )}

      {/* Preview dialog */}
      {previewOutfit && (
        <OutfitPreviewDialog
          outfit={previewOutfit}
          open={!!previewOutfit}
          onClose={() => setPreviewOutfit(null)}
        />
      )}
    </div>
  );
}
