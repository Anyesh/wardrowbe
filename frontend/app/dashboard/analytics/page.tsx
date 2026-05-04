'use client';

import {
  Shirt,
  Sparkles,
  TrendingUp,
  Activity,
  Lightbulb,
  PieChart,
  BarChart,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';
import { useAnalytics } from '@/lib/hooks/use-analytics';
import Image from 'next/image';
import Link from 'next/link';

function StatCard({
  title,
  value,
  description,
  icon: Icon,
  trend,
}: {
  title: string;
  value: string | number;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  trend?: 'up' | 'down' | 'neutral';
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        <p className="text-xs text-muted-foreground flex items-center gap-1">
          {trend === 'up' && <TrendingUp className="h-3 w-3 text-green-500" />}
          {trend === 'down' && <TrendingUp className="h-3 w-3 text-red-500 rotate-180" />}
          {description}
        </p>
      </CardContent>
    </Card>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i}>
            <CardHeader className="pb-2">
              <Skeleton className="h-4 w-24" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-16 mb-1" />
              <Skeleton className="h-3 w-32" />
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-32" />
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-6 w-full" />
              ))}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-32" />
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-6 w-full" />
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function ColorBar({ color, percentage }: { color: string; percentage: number }) {
  const colorMap: Record<string, string> = {
    black: 'bg-gray-900',
    white: 'bg-gray-100 border',
    gray: 'bg-gray-500',
    grey: 'bg-gray-500',
    navy: 'bg-blue-900',
    blue: 'bg-blue-500',
    red: 'bg-red-500',
    green: 'bg-green-500',
    yellow: 'bg-yellow-400',
    orange: 'bg-orange-500',
    purple: 'bg-purple-500',
    pink: 'bg-pink-500',
    brown: 'bg-amber-700',
    beige: 'bg-amber-200',
    cream: 'bg-amber-100',
    khaki: 'bg-yellow-700',
    olive: 'bg-lime-700',
    teal: 'bg-teal-500',
    burgundy: 'bg-red-900',
    maroon: 'bg-red-800',
    coral: 'bg-orange-400',
    salmon: 'bg-red-300',
  };

  const bgColor = colorMap[color.toLowerCase()] || 'bg-muted';

  return (
    <div className="flex items-center gap-3">
      <div className={`w-4 h-4 rounded ${bgColor}`} />
      <div className="flex-1">
        <div className="flex justify-between text-sm mb-1">
          <span className="capitalize">{color}</span>
          <span className="text-muted-foreground">{percentage.toFixed(1)}%</span>
        </div>
        <Progress value={percentage} className="h-2" />
      </div>
    </div>
  );
}

function ItemCard({ item }: { item: { id: string; name: string | null; type: string; thumbnail_url: string | null; wear_count: number } }) {
  return (
    <Link
      href={`/dashboard/wardrobe?item=${item.id}`}
      className="flex items-center gap-3 p-2 rounded-lg hover:bg-muted transition-colors"
    >
      <div className="w-12 h-12 rounded bg-muted overflow-hidden relative flex-shrink-0">
        {item.thumbnail_url ? (
          <Image
            src={item.thumbnail_url}
            alt={item.name || item.type}
            fill
            className="object-cover"
            sizes="48px"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <Shirt className="h-6 w-6 text-muted-foreground" />
          </div>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-medium truncate">{item.name || item.type}</p>
        <p className="text-sm text-muted-foreground capitalize">{item.type}</p>
      </div>
      <Badge variant="secondary">{item.wear_count}x</Badge>
    </Link>
  );
}

function AcceptanceTrendChart({ data }: { data: { period: string; rate: number; total: number }[] }) {
  const maxTotal = Math.max(...data.map((d) => d.total), 1);

  return (
    <div className="space-y-2">
      {data.map((week, i) => (
        <div key={i} className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground w-16 flex-shrink-0">{week.period}</span>
          <div className="flex-1 flex items-center gap-2">
            <div
              className="h-4 bg-primary/20 rounded relative overflow-hidden"
              style={{ width: `${(week.total / maxTotal) * 100}%`, minWidth: week.total > 0 ? '20px' : '0' }}
            >
              <div
                className="absolute inset-y-0 left-0 bg-primary rounded"
                style={{ width: `${week.rate}%` }}
              />
            </div>
            {week.total > 0 && (
              <span className="text-xs text-muted-foreground">{week.rate.toFixed(0)}%</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function AnalyticsPage() {
  const { data, isLoading, isError } = useAnalytics(60);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">分析</h1>
          <p className="text-muted-foreground">你的衣橱洞察与统计</p>
        </div>
        <LoadingSkeleton />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="text-center py-8 text-red-500">
        加载分析数据失败，请稍后重试。
      </div>
    );
  }

  const { wardrobe, color_distribution, type_distribution, most_worn, least_worn, never_worn, acceptance_trend, insights } = data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">分析</h1>
        <p className="text-muted-foreground">你的衣橱洞察与统计</p>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="单品总数"
          value={wardrobe.total_items}
          description={`${wardrobe.items_by_status.ready} 件可穿`}
          icon={Shirt}
        />
        <StatCard
          title="生成穿搭数"
          value={wardrobe.total_outfits}
          description={`${wardrobe.outfits_this_week} 本周`}
          icon={Sparkles}
        />
        <StatCard
          title="接受率"
          value={wardrobe.acceptance_rate ? `${wardrobe.acceptance_rate}%` : '-'}
          description={wardrobe.acceptance_rate ? '建议接受率' : '暂无数据'}
          icon={TrendingUp}
          trend={wardrobe.acceptance_rate && wardrobe.acceptance_rate > 50 ? 'up' : undefined}
        />
        <StatCard
          title="穿着总次数"
          value={wardrobe.total_wears}
          description={wardrobe.average_rating ? `Avg rating: ${wardrobe.average_rating}/5` : '记录你的穿搭'}
          icon={Activity}
        />
      </div>

      {/* 洞察 */}
      {insights.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Lightbulb className="h-5 w-5" />
              洞察
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {insights.map((insight, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <div className="h-1.5 w-1.5 rounded-full bg-primary mt-2 flex-shrink-0" />
                  <span>{insight}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {/* 颜色分布 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PieChart className="h-5 w-5" />
              颜色分布
            </CardTitle>
            <CardDescription>你衣橱里最常见的颜色</CardDescription>
          </CardHeader>
          <CardContent>
            {color_distribution.length === 0 ? (
              <p className="text-muted-foreground text-sm">暂无颜色数据</p>
            ) : (
              <div className="space-y-3">
                {color_distribution.slice(0, 8).map((color) => (
                  <ColorBar key={color.color} color={color.color} percentage={color.percentage} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Type Distribution */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart className="h-5 w-5" />
              单品类型
            </CardTitle>
            <CardDescription>按衣物类型拆分统计</CardDescription>
          </CardHeader>
          <CardContent>
            {type_distribution.length === 0 ? (
              <p className="text-muted-foreground text-sm">暂无单品数据</p>
            ) : (
              <div className="space-y-3">
                {type_distribution.map((type) => (
                  <div key={type.type} className="flex items-center justify-between">
                    <span className="capitalize">{type.type}</span>
                    <div className="flex items-center gap-2">
                      <Progress value={type.percentage} className="w-24 h-2" />
                      <span className="text-sm text-muted-foreground w-12 text-right">
                        {type.count}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {/* 最常穿 */}
        <Card>
          <CardHeader>
            <CardTitle>最常穿</CardTitle>
            <CardDescription>Your favorites</CardDescription>
          </CardHeader>
          <CardContent>
            {most_worn.length === 0 ? (
              <p className="text-muted-foreground text-sm">Start tracking your outfits!</p>
            ) : (
              <div className="space-y-1">
                {most_worn.map((item) => (
                  <ItemCard key={item.id} item={item} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* 最少穿 */}
        <Card>
          <CardHeader>
            <CardTitle>最少穿</CardTitle>
            <CardDescription>Consider wearing these</CardDescription>
          </CardHeader>
          <CardContent>
            {least_worn.length === 0 ? (
              <p className="text-muted-foreground text-sm">Keep tracking!</p>
            ) : (
              <div className="space-y-1">
                {least_worn.map((item) => (
                  <ItemCard key={item.id} item={item} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* 从未穿过 */}
        <Card>
          <CardHeader>
            <CardTitle>从未穿过</CardTitle>
            <CardDescription>Time to try these?</CardDescription>
          </CardHeader>
          <CardContent>
            {never_worn.length === 0 ? (
              <p className="text-muted-foreground text-sm">All items have been worn!</p>
            ) : (
              <div className="space-y-1">
                {never_worn.map((item) => (
                  <ItemCard key={item.id} item={item} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 接受趋势 */}
      {acceptance_trend.length > 0 && acceptance_trend.some((t) => t.total > 0) && (
        <Card>
          <CardHeader>
            <CardTitle>接受率 Trend</CardTitle>
            <CardDescription>How you&apos;ve responded to suggestions over time</CardDescription>
          </CardHeader>
          <CardContent>
            <AcceptanceTrendChart data={acceptance_trend} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
