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
      <h3 className="text-lg font-semibold mb-2">还没有推荐历史</h3>
      <p className="text-muted-foreground mb-6 max-w-sm">
        开始接收穿搭建议后，你的历史记录会显示在这里。
      </p>
      <Button variant="outline" asChild>
        <a href="/dashboard/suggest">获取第一套建议</a>
      </Button>
    </div>
  );
}

function Empty约会({ date }: { date: 约会 }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 px-4 text-center">
      <Calendar className="h-8 w-8 text-muted-foreground mb-2" />
      <p className="text-sm text-muted-foreground">
        当天没有穿搭记录：{format(date, 'MMMM d, yyyy')}
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
  const now = new 约会();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [selected约会, setSelected约会] = useState<约会 | null>(now);
  const [filters, setFilters] = useState<OutfitFilters>({});
  const [feedbackOutfit, setFeedbackOutfit] = useState<Outfit | null>(null);
  const [previewOutfit, setPreviewOutfit] = useState<Outfit | null>(null);

  const { data, isLoading, isError } = useCalendarOutfits(year, month, filters);

  // Filter outfits for the selected date
  const selected约会Outfits = useMemo(() => {
    if (!data?.outfits || !selected约会) return [];
    return data.outfits.filter((outfit) =>
      outfit.scheduled_for && isSameDay(parseISO(outfit.scheduled_for), selected约会)
    );
  }, [data?.outfits, selected约会]);

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
        加载历史失败，请稍后重试。
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">历史</h1>
          <p className="text-muted-foreground">
            查看你过往收到的穿搭建议
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <Select value={filters.occasion || 'all'} onValueChange={handleOccasionChange}>
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="全部场景" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部场景</SelectItem>
            <SelectItem value="casual">休闲</SelectItem>
            <SelectItem value="office">通勤</SelectItem>
            <SelectItem value="formal">正式</SelectItem>
            <SelectItem value="date">约会</SelectItem>
            <SelectItem value="workout">运动</SelectItem>
          </SelectContent>
        </Select>
        <Select value={filters.status || 'all'} onValueChange={handleStatusChange}>
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="全部状态" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            <SelectItem value="accepted">已接受</SelectItem>
            <SelectItem value="rejected">已拒绝</SelectItem>
            <SelectItem value="pending">待处理</SelectItem>
            <SelectItem value="viewed">已查看</SelectItem>
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
                selected约会={selected约会}
                onSelect约会={setSelected约会}
                onMonthChange={handleMonthChange}
              />
            )}
          </CardContent>
        </Card>

        {/* Outfits column */}
        <div className="order-1 lg:order-2 space-y-4">
          {/* Selected date header */}
          {selected约会 && (
            <div className="border-b pb-3">
              <h2 className="text-lg font-semibold">
                {format(selected约会, 'EEEE, MMMM d')}
              </h2>
              <p className="text-sm text-muted-foreground">
                {selected约会Outfits.length} 套穿搭
              </p>
            </div>
          )}

          {isLoading ? (
            <LoadingSkeleton />
          ) : !data || data.outfits.length === 0 ? (
            <EmptyHistory />
          ) : selected约会 && selected约会Outfits.length === 0 ? (
            <Empty约会 date={selected约会} />
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              {selected约会Outfits.map((outfit) => (
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
