# Miniapp Mobile UI Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh the Taro miniapp so every current page feels mobile-first, the bottom tab bar includes outline icons, and the H5 + WeChat flows remain functional.

**Architecture:** Keep the existing Taro route structure, service layer, and native tab bar. Add static tab icon assets, introduce a small mobile UI foundation in shared SCSS and shared components, then refactor the eight miniapp pages in batches so the most important action on each page is clearer and touch-friendly.

**Tech Stack:** Taro 4, React, SCSS, native Taro tabBar, existing service modules, `pnpm build:h5`, Playwright smoke verification.

---

## File map

### Existing files to modify

- `miniapp/src/app.config.ts` — tab bar metadata, icon wiring, shell-level visual adjustments
- `miniapp/src/app.scss` — global mobile design tokens, spacing, surface, button, chip, form, footer, and section primitives
- `miniapp/src/components/ItemCard.tsx` — image-first wardrobe card redesign
- `miniapp/src/components/OutfitCard.tsx` — outfit list/result card redesign
- `miniapp/src/components/FilterSheet.tsx` — mobile-oriented filter surface with clearer grouping and actions
- `miniapp/src/pages/home/index.tsx`
- `miniapp/src/pages/home/index.scss`
- `miniapp/src/pages/wardrobe/index.tsx`
- `miniapp/src/pages/wardrobe/index.scss`
- `miniapp/src/pages/wardrobe/detail.tsx`
- `miniapp/src/pages/wardrobe/detail.scss`
- `miniapp/src/pages/wardrobe/add.tsx`
- `miniapp/src/pages/wardrobe/add.scss`
- `miniapp/src/pages/suggest/index.tsx`
- `miniapp/src/pages/suggest/index.scss`
- `miniapp/src/pages/suggest/result.tsx`
- `miniapp/src/pages/suggest/result.scss`
- `miniapp/src/pages/outfits/index.tsx`
- `miniapp/src/pages/outfits/index.scss`
- `miniapp/src/pages/settings/index.tsx`
- `miniapp/src/pages/settings/index.scss`
- `miniapp/package.json` — only if a verification helper script is needed during implementation

### New files to create

- `miniapp/src/assets/tabbar/home.png`
- `miniapp/src/assets/tabbar/home-active.png`
- `miniapp/src/assets/tabbar/wardrobe.png`
- `miniapp/src/assets/tabbar/wardrobe-active.png`
- `miniapp/src/assets/tabbar/suggest.png`
- `miniapp/src/assets/tabbar/suggest-active.png`
- `miniapp/src/assets/tabbar/outfits.png`
- `miniapp/src/assets/tabbar/outfits-active.png`
- `miniapp/src/assets/tabbar/settings.png`
- `miniapp/src/assets/tabbar/settings-active.png`
- `miniapp/src/components/PageHeader.tsx`
- `miniapp/src/components/BottomActionBar.tsx`
- `miniapp/src/components/EmptyState.tsx`
- `miniapp/src/components/StatCard.tsx`

### Existing files to leave alone unless a task explicitly requires them

- `miniapp/src/services/**` — no product-scope reason to change API behavior in this refresh
- `miniapp/src/shared/types.ts` — only touch if a page currently violates existing typings
- backend files — not part of this UI refresh

---

## Task 1: Add native tab bar icons and wire app shell metadata

**Files:**
- Create: `miniapp/src/assets/tabbar/*.png`
- Modify: `miniapp/src/app.config.ts`
- Verify: `miniapp/src/app.config.ts`, H5 route boot, WeChat tab bar config in compiled output

- [ ] **Step 1: Create the icon asset set**

Create ten 81x81 PNG assets in `miniapp/src/assets/tabbar/`.

Asset list:
- `home.png`, `home-active.png`
- `wardrobe.png`, `wardrobe-active.png`
- `suggest.png`, `suggest-active.png`
- `outfits.png`, `outfits-active.png`
- `settings.png`, `settings-active.png`

Asset requirements:
- outline-only icon language
- neutral/default icons use muted gray on transparent background
- active icons use near-black or dark charcoal on transparent background
- 2px-ish visual stroke at source resolution so the icons survive downscaling cleanly
- no filled circles, gradients, drop shadows, or color accents

- [ ] **Step 2: Update `miniapp/src/app.config.ts` to use icon assets**

Apply this shape to the tab configuration:

```ts
export default {
  // ...existing pages/window
  tabBar: {
    color: '#6b7280',
    selectedColor: '#111827',
    backgroundColor: '#ffffff',
    borderStyle: 'black',
    list: [
      {
        pagePath: 'pages/home/index',
        text: 'Home',
        iconPath: 'assets/tabbar/home.png',
        selectedIconPath: 'assets/tabbar/home-active.png',
      },
      {
        pagePath: 'pages/wardrobe/index',
        text: 'Wardrobe',
        iconPath: 'assets/tabbar/wardrobe.png',
        selectedIconPath: 'assets/tabbar/wardrobe-active.png',
      },
      {
        pagePath: 'pages/suggest/index',
        text: 'Suggest',
        iconPath: 'assets/tabbar/suggest.png',
        selectedIconPath: 'assets/tabbar/suggest-active.png',
      },
      {
        pagePath: 'pages/outfits/index',
        text: 'Outfits',
        iconPath: 'assets/tabbar/outfits.png',
        selectedIconPath: 'assets/tabbar/outfits-active.png',
      },
      {
        pagePath: 'pages/settings/index',
        text: 'Settings',
        iconPath: 'assets/tabbar/settings.png',
        selectedIconPath: 'assets/tabbar/settings-active.png',
      },
    ],
  },
} as const
```

- [ ] **Step 3: Verify the app config compiles cleanly**

Run:

```bash
cd miniapp
pnpm build:h5
```

Expected:
- command exits `0`
- `miniapp/dist/index.html` exists
- no missing-asset errors for the tab bar PNG files

- [ ] **Step 4: Commit the navigation asset wiring**

```bash
git add miniapp/src/app.config.ts miniapp/src/assets/tabbar
git commit -m "feat: add miniapp tab bar icons"
```

---

## Task 2: Establish the shared mobile UI foundation

**Files:**
- Modify: `miniapp/src/app.scss`
- Create: `miniapp/src/components/PageHeader.tsx`
- Create: `miniapp/src/components/BottomActionBar.tsx`
- Create: `miniapp/src/components/EmptyState.tsx`
- Create: `miniapp/src/components/StatCard.tsx`
- Verify: `miniapp/src/app.scss`, component imports in later tasks

- [ ] **Step 1: Expand `miniapp/src/app.scss` with mobile primitives**

Add or revise shared classes so the app has consistent mobile spacing, lighter surfaces, larger controls, and fixed footer support.

Required primitives to define:

```scss
.page {
  min-height: 100vh;
  padding: 28rpx 24rpx 180rpx;
  box-sizing: border-box;
}

.page--with-footer {
  padding-bottom: 220rpx;
}

.page-header {
  display: flex;
  flex-direction: column;
  gap: 10rpx;
}

.page-header__eyebrow {
  color: #6b7280;
  font-size: 24rpx;
}

.page-header__title {
  font-size: 48rpx;
  line-height: 1.15;
  font-weight: 700;
}

.page-header__subtitle {
  color: #4b5563;
  font-size: 26rpx;
  line-height: 1.45;
}

.section-card {
  background: #ffffff;
  border-radius: 28rpx;
  padding: 28rpx;
  box-shadow: 0 10rpx 30rpx rgba(15, 23, 42, 0.06);
}

.primary-button,
.secondary-button {
  min-height: 88rpx;
  border-radius: 22rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}

.bottom-action-bar {
  position: fixed;
  left: 24rpx;
  right: 24rpx;
  bottom: 32rpx;
  display: flex;
  flex-direction: column;
  gap: 16rpx;
}
```

Also normalize:
- chips
- badges
- search / input controls
- two-column stat area
- image card radii
- empty state blocks

- [ ] **Step 2: Create `PageHeader.tsx`**

Add a reusable page header wrapper:

```tsx
import React from 'react'
import { Text, View } from '@tarojs/components'

interface PageHeaderProps {
  eyebrow?: string
  title: string
  subtitle?: string
  rightSlot?: React.ReactNode
}

export default function PageHeader({ eyebrow, title, subtitle, rightSlot }: PageHeaderProps) {
  return (
    <View className='page-header'>
      <View className='row page-header__row'>
        <View className='stack page-header__content'>
          {eyebrow ? <Text className='page-header__eyebrow'>{eyebrow}</Text> : null}
          <Text className='page-header__title'>{title}</Text>
          {subtitle ? <Text className='page-header__subtitle'>{subtitle}</Text> : null}
        </View>
        {rightSlot ? <View>{rightSlot}</View> : null}
      </View>
    </View>
  )
}
```

- [ ] **Step 3: Create `BottomActionBar.tsx`, `EmptyState.tsx`, and `StatCard.tsx`**

Add small focused helpers instead of repeating footer and empty-state markup.

Scaffold them as:

```tsx
// BottomActionBar.tsx
import React from 'react'
import { View } from '@tarojs/components'

export default function BottomActionBar({ children }: { children: React.ReactNode }) {
  return <View className='bottom-action-bar'>{children}</View>
}
```

```tsx
// EmptyState.tsx
import React from 'react'
import { Text, View } from '@tarojs/components'

interface EmptyStateProps {
  title: string
  description: string
  action?: React.ReactNode
}

export default function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <View className='section-card empty-state'>
      <Text className='card-title'>{title}</Text>
      <Text className='muted'>{description}</Text>
      {action ? <View className='empty-state__action'>{action}</View> : null}
    </View>
  )
}
```

```tsx
// StatCard.tsx
import React from 'react'
import { Text, View } from '@tarojs/components'

interface StatCardProps {
  label: string
  value: string | number
  hint: string
}

export default function StatCard({ label, value, hint }: StatCardProps) {
  return (
    <View className='section-card stat-card'>
      <Text className='section-title'>{label}</Text>
      <Text className='hero-title'>{value}</Text>
      <Text className='muted'>{hint}</Text>
    </View>
  )
}
```

- [ ] **Step 4: Verify the foundation still builds**

Run:

```bash
cd miniapp
pnpm build:h5
```

Expected:
- build succeeds
- no unresolved import errors for the new shared components

- [ ] **Step 5: Commit the shared mobile foundation**

```bash
git add miniapp/src/app.scss miniapp/src/components/PageHeader.tsx miniapp/src/components/BottomActionBar.tsx miniapp/src/components/EmptyState.tsx miniapp/src/components/StatCard.tsx
git commit -m "feat: add miniapp mobile ui foundation"
```

---

## Task 3: Refactor shared cards and filter surfaces

**Files:**
- Modify: `miniapp/src/components/ItemCard.tsx`
- Modify: `miniapp/src/components/OutfitCard.tsx`
- Modify: `miniapp/src/components/FilterSheet.tsx`
- Modify: `miniapp/src/app.scss`
- Verify: wardrobe grid, outfits list, suggest result, filter display

- [ ] **Step 1: Redesign `ItemCard.tsx` into an image-first mobile card**

Reshape the component so the image leads, metadata is tighter, and touch affordance is clearer.

Target structure:

```tsx
<View className='item-card section-card' onClick={onClick}>
  <Image className='item-card__image' ... />
  <View className='stack item-card__body'>
    <View className='row item-card__headline'>
      <Text className='card-title'>{item.name || titleCase(item.type)}</Text>
      {item.favorite ? <Text className='badge'>★</Text> : null}
    </View>
    <Text className='muted'>{joinList([...])}</Text>
    <View className='row-wrap item-card__meta'>
      <Text className={`badge ${item.status === 'ready' ? 'badge--ok' : ''}`}>{titleCase(item.status)}</Text>
      {item.needs_wash ? <Text className='badge badge--warn'>需要清洗</Text> : null}
    </View>
  </View>
</View>
```

- [ ] **Step 2: Redesign `OutfitCard.tsx` into a result-oriented list card**

Keep the same data, but reorder it to emphasize occasion, state, date, and thumbnails before long copy.

Target structure:

```tsx
<View className='outfit-card section-card' onClick={onClick}>
  <View className='row'>
    <Text className='card-title'>{titleCase(outfit.occasion)}</Text>
    <Text className='badge'>{titleCase(outfit.status)}</Text>
  </View>
  <Text className='muted'>Created {formatDate(outfit.created_at)}</Text>
  <View className='thumb-strip'>...</View>
  {outfit.reasoning ? <Text className='outfit-card__summary'>{outfit.reasoning}</Text> : null}
</View>
```

Clamp or visually de-emphasize long reasoning text in CSS if needed.

- [ ] **Step 3: Upgrade `FilterSheet.tsx` from card-form to mobile filter module**

Keep the same filter inputs, but change the layout to feel like a mobile sheet:
- grouped labels
- stronger separation between toggles and type selector
- clearer reset/apply affordance if local draft state is introduced

If a draft state is added, the component contract should become:

```tsx
interface FilterSheetProps {
  value: ItemFilter
  onChange: (value: ItemFilter) => void
}
```

The outer signature stays the same, even if the internals gain local state.

- [ ] **Step 4: Add companion shared styles for card variants**

Update `miniapp/src/app.scss` with:
- `.item-card`
- `.item-card__image`
- `.item-card__body`
- `.outfit-card`
- `.outfit-card__summary`
- `.filter-sheet`
- `.filter-sheet__group`
- `.empty-state__action`

- [ ] **Step 5: Verify build and visual imports**

Run:

```bash
cd miniapp
pnpm build:h5
```

Expected:
- build succeeds
- no duplicate-class or import-resolution issues

- [ ] **Step 6: Commit shared component refactors**

```bash
git add miniapp/src/components/ItemCard.tsx miniapp/src/components/OutfitCard.tsx miniapp/src/components/FilterSheet.tsx miniapp/src/app.scss
git commit -m "feat: refresh miniapp shared cards"
```

---

## Task 4: Refresh Home, Suggest, and Outfits tab pages

**Files:**
- Modify: `miniapp/src/pages/home/index.tsx`
- Modify: `miniapp/src/pages/home/index.scss`
- Modify: `miniapp/src/pages/suggest/index.tsx`
- Modify: `miniapp/src/pages/suggest/index.scss`
- Modify: `miniapp/src/pages/outfits/index.tsx`
- Modify: `miniapp/src/pages/outfits/index.scss`
- Reuse: `miniapp/src/components/PageHeader.tsx`, `BottomActionBar.tsx`, `StatCard.tsx`, `EmptyState.tsx`, `OutfitCard.tsx`

- [ ] **Step 1: Refactor Home into a mobile summary flow**

Replace the current loose card stack with this order:
1. `PageHeader`
2. weather / today summary section
3. two stat cards
4. large quick-action buttons
5. insights feed section

Target quick-action block example:

```tsx
<View className='section-card stack'>
  <Text className='section-title'>Quick actions</Text>
  <Button className='primary-button' onClick={() => Taro.switchTab({ url: '/pages/suggest/index' })}>生成今日穿搭</Button>
  <View className='grid-2'>
    <Button className='secondary-button' onClick={() => Taro.switchTab({ url: '/pages/wardrobe/index' })}>浏览衣橱</Button>
    <Button className='secondary-button' onClick={() => Taro.navigateTo({ url: '/pages/wardrobe/add' })}>添加单品</Button>
  </View>
</View>
```

- [ ] **Step 2: Refactor Suggest into a one-task screen with bottom CTA**

Use this layout:
- `PageHeader`
- context/weather card
- occasion block
- optional override input block
- `BottomActionBar` with one dominant button

Target footer pattern:

```tsx
<BottomActionBar>
  <Button className='primary-button' loading={loading} onClick={generate}>生成穿搭</Button>
</BottomActionBar>
```

- [ ] **Step 3: Refactor Outfits into a browse-first mobile list**

Keep search and filters, but reorder them into:
- header
- search
- horizontal filter chip row
- month selector as secondary control
- list or empty state

If no results:

```tsx
<EmptyState
  title='还没有符合条件的穿搭'
  description='调整筛选条件，或者先去 Suggest 生成一套新的穿搭。'
  action={<Button className='primary-button' onClick={() => Taro.switchTab({ url: '/pages/suggest/index' })}>去生成穿搭</Button>}
/>
```

- [ ] **Step 4: Add page-specific SCSS for structure, not primitive duplication**

Each page SCSS should only contain page-specific layout helpers, e.g.:
- `.home-page__actions`
- `.suggest-page__occasion`
- `.outfits-page__filters`

Do not re-declare global button, card, or typography primitives there.

- [ ] **Step 5: Verify the three-page batch**

Run:

```bash
cd miniapp
pnpm build:h5
```

Then smoke-check manually or with browser:
- `/pages/home/index`
- `/pages/suggest/index`
- `/pages/outfits/index`

Expected:
- no blank pages
- clear primary action on each screen
- no overlapping footer/action bar

- [ ] **Step 6: Commit the first page batch**

```bash
git add miniapp/src/pages/home miniapp/src/pages/suggest miniapp/src/pages/outfits
git commit -m "feat: refresh miniapp core tab pages"
```

---

## Task 5: Refresh Wardrobe list, detail, and add flows

**Files:**
- Modify: `miniapp/src/pages/wardrobe/index.tsx`
- Modify: `miniapp/src/pages/wardrobe/index.scss`
- Modify: `miniapp/src/pages/wardrobe/detail.tsx`
- Modify: `miniapp/src/pages/wardrobe/detail.scss`
- Modify: `miniapp/src/pages/wardrobe/add.tsx`
- Modify: `miniapp/src/pages/wardrobe/add.scss`
- Reuse: `PageHeader`, `BottomActionBar`, `EmptyState`, `ItemCard`, `FilterSheet`

- [ ] **Step 1: Refactor wardrobe list into a browse-first layout**

Target order:
- `PageHeader` with add action in `rightSlot`
- search bar
- compact sort / filter summary row
- `FilterSheet`
- image-first grid
- cleaner load-more area at the bottom

Do not keep a row of tiny utility buttons near the top.

- [ ] **Step 2: Improve wardrobe empty state**

Replace the current mixed-language copy with:

```tsx
<EmptyState
  title='衣橱还是空的'
  description='先添加第一件单品，后续才能生成更准确的穿搭建议。'
  action={<Button className='primary-button' onClick={() => Taro.navigateTo({ url: '/pages/wardrobe/add' })}>添加第一件单品</Button>}
/>
```

- [ ] **Step 3: Refactor wardrobe detail into a hero-image detail page**

New order:
- hero image
- top summary card (name, type, state)
- edit fields card
- secondary actions grouped below
- destructive action visually separated

Move save into a stronger bottom or trailing action instead of burying it between many small buttons.

- [ ] **Step 4: Refactor add page into a capture-first mobile form**

New order:
- page header
- image selection card
- essential metadata block
- optional metadata block
- bottom submit CTA

Use `BottomActionBar` for submit if the page length benefits from it.

- [ ] **Step 5: Add/adjust wardrobe-specific SCSS**

Define only wardrobe-specific helpers such as:
- `.wardrobe-page__toolbar`
- `.detail-hero`
- `.detail-actions`
- `.add-page__preview`

- [ ] **Step 6: Verify the wardrobe batch**

Run:

```bash
cd miniapp
pnpm build:h5
```

Then smoke-check:
- `/pages/wardrobe/index`
- `/pages/wardrobe/detail?id=<existing-id>` if available
- `/pages/wardrobe/add`

Expected:
- list is easier to scan on mobile
- detail emphasizes image and state
- add page has a clear image-first task flow

- [ ] **Step 7: Commit the wardrobe batch**

```bash
git add miniapp/src/pages/wardrobe
git commit -m "feat: refresh miniapp wardrobe flows"
```

---

## Task 6: Refresh Suggest result and Settings

**Files:**
- Modify: `miniapp/src/pages/suggest/result.tsx`
- Modify: `miniapp/src/pages/suggest/result.scss`
- Modify: `miniapp/src/pages/settings/index.tsx`
- Modify: `miniapp/src/pages/settings/index.scss`
- Reuse: `PageHeader`, `BottomActionBar`, `EmptyState`, `OutfitCard`

- [ ] **Step 1: Refactor Suggest result into a recommendation-first screen**

Target order:
- `PageHeader`
- `OutfitCard`
- highlights section
- style notes section
- bottom action group with a dominant primary button and quieter secondary actions

Suggested action order:
1. 接受 / 很喜欢
2. 换一套
3. 拒绝

Keep the existing API calls and state transitions unchanged.

- [ ] **Step 2: Refactor Settings into grouped mobile sections**

Split the page into:
- connection & account
- personal profile
- preferences

Move save to a persistent or strongly emphasized bottom action.

Keep sync and clear-token actions secondary.

- [ ] **Step 3: Improve labels and copy for mobile clarity**

Examples:
- `连接设置` instead of generic debug phrasing
- `个人资料` and `偏好设置` section names
- remove mixed-language or desktop-console sounding text where it still exists

- [ ] **Step 4: Add page-specific SCSS only where necessary**

Define layout helpers such as:
- `.result-page__actions`
- `.settings-page__section`
- `.settings-page__token`

- [ ] **Step 5: Verify the final page batch**

Run:

```bash
cd miniapp
pnpm build:h5
```

Then smoke-check:
- `/pages/suggest/result?id=<existing-id>` if available
- `/pages/settings/index`

Expected:
- result page has a clear next step
- settings page no longer feels like a desktop admin form

- [ ] **Step 6: Commit the final page batch**

```bash
git add miniapp/src/pages/suggest/result.* miniapp/src/pages/settings
git commit -m "feat: refresh miniapp result and settings pages"
```

---

## Task 7: Final verification, screenshots, and cleanup

**Files:**
- Modify only if needed for final polish from verification feedback
- Verify: `miniapp/` build output and running local app

- [ ] **Step 1: Run final build verification**

```bash
cd miniapp
pnpm build:h5
```

Expected:
- exit `0`
- `index.html` emitted
- no missing tab icon assets

- [ ] **Step 2: Run the local bootstrap script and verify routes**

```bash
cd /Users/bytedance/external/wardrowbe
./scripts/setup-and-run-taro-web.sh --skip-install
```

Expected:
- backend returns `200` on `http://localhost:8000/api/v1/health`
- taro returns `200` on `http://localhost:10086/`
- app resolves to `/pages/home/index`

- [ ] **Step 3: Browser smoke-test the five tab pages**

Check these routes manually or with Playwright:
- `http://localhost:10086/pages/home/index`
- `http://localhost:10086/pages/wardrobe/index`
- `http://localhost:10086/pages/suggest/index`
- `http://localhost:10086/pages/outfits/index`
- `http://localhost:10086/pages/settings/index`

Verify:
- tab bar icons are present
- no page renders like a desktop dashboard
- primary actions are visually dominant
- no footer overlaps critical content

- [ ] **Step 4: Browser smoke-test secondary flows**

Check if practical in current data state:
- wardrobe add
- wardrobe detail
- suggest result

Verify:
- image-first layouts render cleanly
- action groups are touch-friendly
- no obvious clipping or spacing regressions

- [ ] **Step 5: Final polish commit**

```bash
git add miniapp/src miniapp/package.json
git commit -m "feat: finalize miniapp mobile ui refresh"
```

---

## Self-review

### Spec coverage

Covered:
- native mobile feel across all current miniapp pages → Tasks 2 through 6
- line-style tab icons → Task 1
- stronger primary actions and mobile hierarchy → Tasks 4 through 6
- shared mobile component language → Tasks 2 and 3
- preserve existing backend/service behavior → reflected in task constraints
- keep H5 build working → every task includes `pnpm build:h5`, final verification in Task 7

No spec gaps found.

### Placeholder scan

Checked for `TBD`, `TODO`, `FIXME`, `implement later`, and similar placeholders while drafting. None intentionally remain.

### Type consistency

- Shared component names are consistent across all tasks: `PageHeader`, `BottomActionBar`, `EmptyState`, `StatCard`
- Existing page and component file paths match current repo structure
- The plan preserves current service contracts instead of inventing new API methods

