import type { createTranslator } from 'next-intl';
import type enWardrobe from '@/messages/en/wardrobe.json';

export type ExportFileTranslator = ReturnType<
  typeof createTranslator<{ wardrobe: typeof enWardrobe }, 'wardrobe.exportFile'>
>;

export type ExportSection =
  | 'tops'
  | 'bottoms'
  | 'full_body'
  | 'outerwear'
  | 'footwear'
  | 'accessories'
  | 'other';

export interface ExportedItem {
  section: ExportSection;
  name: string | null;
  type: string;
  subtype: string | null;
  brand: string | null;
  primary_color: string | null;
  colors: string[];
  pattern: string | null;
  material: string | null;
  style: string[];
  formality: string | null;
  season: string[];
  fit: string | null;
  description: string | null;
  notes: string | null;
}

export interface WardrobeExport {
  exported_at: string;
  item_count: number;
  items: ExportedItem[];
}

type Label = (value: string) => string;

export interface CatalogueLabels {
  t: ExportFileTranslator;
  locale: string;
  type: Label;
  subtype: Label;
  color: Label;
  material: Label;
  pattern: Label;
  formality: Label;
  style: Label;
  season: Label;
  fit: Label;
}

export type CatalogueFormat = 'markdown' | 'text';

const SECTION_KEYS = {
  tops: 'sections.tops',
  bottoms: 'sections.bottoms',
  full_body: 'sections.fullBody',
  outerwear: 'sections.outerwear',
  footwear: 'sections.footwear',
  accessories: 'sections.accessories',
  other: 'sections.other',
} as const satisfies Record<ExportSection, string>;

const DETAIL_SEPARATOR = ' | ';

function oneLine(text: string | null): string {
  return (text ?? '').split(/\s+/).filter(Boolean).join(' ');
}

function groupBySection(items: ExportedItem[]) {
  const groups: { section: ExportSection; items: ExportedItem[] }[] = [];
  for (const item of items) {
    const last = groups[groups.length - 1];
    if (last && last.section === item.section) last.items.push(item);
    else groups.push({ section: item.section, items: [item] });
  }
  return groups;
}

function itemTitle(item: ExportedItem, labels: CatalogueLabels): string {
  const { t } = labels;
  const parts: string[] = [];
  const name = oneLine(item.name);
  if (name) parts.push(t('named', { name }));
  parts.push(
    item.subtype
      ? t('kind', { subtype: labels.subtype(item.subtype), type: labels.type(item.type) })
      : labels.type(item.type)
  );
  const brand = oneLine(item.brand);
  if (brand) parts.push(t('byBrand', { brand }));
  return parts.join(' - ');
}

function itemDetails(
  item: ExportedItem,
  labels: CatalogueLabels,
  list: (values: string[]) => string
): string[] {
  const { t } = labels;
  const others = item.colors.filter((c) => c !== item.primary_color).map(labels.color);
  let color = others.length ? list(others) : '';
  if (item.primary_color) {
    const primary = labels.color(item.primary_color);
    color = others.length ? t('withColors', { primary, others: color }) : primary;
  }

  const details: string[] = [];
  if (color) details.push(t('labels.color', { value: color }));
  if (item.material) details.push(t('labels.material', { value: labels.material(item.material) }));
  if (item.pattern && item.pattern !== 'solid') {
    details.push(t('labels.pattern', { value: labels.pattern(item.pattern) }));
  }
  if (item.formality) {
    details.push(t('labels.formality', { value: labels.formality(item.formality) }));
  }
  if (item.style.length) details.push(t('labels.style', { value: list(item.style.map(labels.style)) }));
  if (item.season.length) {
    details.push(t('labels.season', { value: list(item.season.map(labels.season)) }));
  }
  if (item.fit) details.push(t('labels.fit', { value: labels.fit(item.fit) }));
  return details;
}

function renderMarkdown(data: WardrobeExport, labels: CatalogueLabels): string {
  const { t, locale } = labels;
  const listFormat = new Intl.ListFormat(locale, { type: 'conjunction' });
  const list = (values: string[]) => listFormat.format(values);
  const date = new Intl.DateTimeFormat(locale, { dateStyle: 'long' }).format(
    new Date(data.exported_at)
  );

  let number = 0;
  const sections = groupBySection(data.items).map(({ section, items }) => {
    const entries = items.map((item) => {
      number += 1;
      const lines = [`- **[${number}] ${itemTitle(item, labels)}**`];
      const description = oneLine(item.description);
      if (description) lines.push(`  - ${t('labels.description', { value: description })}`);
      const details = itemDetails(item, labels, list);
      if (details.length) {
        lines.push(`  - ${t('labels.details', { value: details.join(DETAIL_SEPARATOR) })}`);
      }
      const notes = oneLine(item.notes);
      if (notes) lines.push(`  - ${t('labels.notes', { value: notes })}`);
      return lines.join('\n');
    });
    const heading = t(SECTION_KEYS[section] ?? SECTION_KEYS.other, { count: items.length });
    return `## ${heading}\n${entries.join('\n')}\n`;
  });

  const head = `# ${t('title')}\n\n_${t('summary', { count: data.items.length, date })}_\n`;
  return [head, ...sections].join('\n');
}

function renderText(data: WardrobeExport, labels: CatalogueLabels): string {
  const lines = data.items.map((item, index) => {
    const facts = [
      item.primary_color && labels.color(item.primary_color),
      item.material && labels.material(item.material),
    ].filter(Boolean);
    let title = itemTitle(item, labels);
    if (facts.length) title += ` [${facts.join(DETAIL_SEPARATOR)}]`;
    const description = oneLine(item.description);
    const line = description ? labels.t('textLine', { title, description }) : title;
    return `${index + 1}. ${line}`;
  });
  return lines.length ? `${lines.join('\n')}\n` : '';
}

export function renderCatalogue(
  data: WardrobeExport,
  format: CatalogueFormat,
  labels: CatalogueLabels
): string {
  return format === 'markdown' ? renderMarkdown(data, labels) : renderText(data, labels);
}
