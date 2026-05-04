# Miniapp Mobile UI Refresh Design

Date: 2026-05-04
Branch: `codex/wechat-taro-cloudbase`
Status: Approved for planning

## 1. Summary

Refresh the Taro miniapp so it feels like a mobile-first app / WeChat mini program instead of a compressed PC web dashboard.

This design keeps the existing data flow and backend contracts, but changes the miniapp's information hierarchy, page structure, interaction density, and tab navigation affordances.

The scope covers **all current miniapp pages**:

- `pages/home/index`
- `pages/wardrobe/index`
- `pages/wardrobe/detail`
- `pages/wardrobe/add`
- `pages/suggest/index`
- `pages/suggest/result`
- `pages/outfits/index`
- `pages/settings/index`

The tab bar will keep the current five destinations, but will gain **line-style icons** and a more native mobile visual rhythm.

## 2. Goals

1. Make the miniapp feel like a native mobile experience rather than a responsive web layout.
2. Improve one-handed use with clearer hierarchy and larger touch targets.
3. Introduce a coherent navigation language across all pages.
4. Add tab icons for all five tabs using a consistent outline style.
5. Preserve current business logic and API behavior wherever possible.
6. Keep the H5 build and WeChat miniapp flow maintainable inside the current Taro structure.

## 3. Non-goals

This refresh does **not** include:

- new product features or new backend endpoints
- replacing the native Taro tab bar with a custom tab bar
- introducing heavy animation systems or advanced gesture frameworks
- redesigning the app into a fully branded marketing style
- changing authentication architecture or session semantics

## 4. Product constraints

- The user explicitly prefers a **native app / mini program feel**.
- The user approved a scope that includes **all miniapp pages**.
- The user approved **outline / line-style icons** for the tab bar.
- The user approved **structural changes** where they improve mobile UX.
- We should prefer changes that work in both Taro H5 and WeChat miniapp builds.

## 5. UX principles

### 5.1 Mobile-first hierarchy

Each page should answer these questions quickly:

1. Where am I?
2. What is the main thing I can do here?
3. What secondary actions are available if I need them?

### 5.2 One dominant action per screen

Every page should have one clearly dominant action:

- Home: jump into a high-value next step
- Wardrobe: add item / inspect items
- Suggest: generate outfit
- Outfits: inspect and revisit outfits
- Settings: save settings
- Add / Result / Detail pages: primary action anchored near the bottom or in a fixed footer where appropriate

### 5.3 Bigger touch surfaces, fewer tiny controls

We will reduce use of mini buttons and dense horizontal control clusters. Primary controls should be thumb-friendly and visually obvious.

### 5.4 Fewer dashboard blocks, more task-oriented sections

Pages should not read like desktop dashboards. Instead, each page should be split into focused mobile sections with clear labels and spacing.

### 5.5 Consistent mobile component language

The same visual rules should apply across cards, chips, headers, empty states, lists, and footers.

## 6. Navigation design

## 6.1 Keep the existing five-tab structure

The miniapp keeps these tabs:

- Home
- Wardrobe
- Suggest
- Outfits
- Settings

## 6.2 Add outline icons to the native tab bar

We will continue using Taro's native tab bar configuration and add icon assets through `iconPath` and `selectedIconPath`.

### Icon semantics

- Home → home / house outline
- Wardrobe → hanger / closet outline
- Suggest → magic wand / spark outline
- Outfits → stacked look / clothing card outline
- Settings → gear outline

### Visual states

- Default: low-emphasis neutral outline icon + muted label
- Active: darker outline icon + darker label
- No filled style for the primary design language
- No exaggerated gradients or badges in tab icons

### Why native tab bar instead of custom tab bar

Using the native tab bar is the best trade-off for this phase:

- lower implementation risk
- better platform consistency
- simpler asset handling
- easier maintenance across H5 and weapp

## 7. Page-level design

## 7.1 Home

### Current problem

The current page resembles a compressed dashboard with multiple equally weighted cards.

### New structure

1. **Compact welcome header**
   - greeting
   - user name
   - short status line if relevant

2. **Today summary card**
   - weather / condition
   - one concise recommendation or context cue

3. **Quick stats row**
   - pending outfits
   - wardrobe item count

4. **Primary action cluster**
   - convert current mini buttons into larger mobile actions
   - prioritize the most likely next steps

5. **Insights feed**
   - short, scan-friendly insight items
   - avoid making this look like a data dashboard panel

### Interaction notes

- First screen should feel light and useful.
- Quick actions should be visually tappable, not tiny utility controls.

## 7.2 Wardrobe list

### Current problem

Search, sort, filters, refresh, and load-more controls are too desktop-like and fragmented.

### New structure

1. **Page header**
   - title
   - top-right add action

2. **Search bar**
   - persistent and prominent

3. **Lightweight filter row**
   - summary chips / sort summary
   - tap to open deeper filter controls

4. **Filter sheet / drawer**
   - mobile-oriented grouped controls
   - clear apply and reset actions

5. **Image-first wardrobe grid**
   - card visuals lead
   - text is secondary but readable

6. **Load more affordance**
   - cleaner bottom action pattern
   - no clutter near the top

### Interaction notes

- The list should feel like browsing a wardrobe, not configuring a query form.
- Empty state should explain what to do next and promote the add flow.

## 7.3 Wardrobe detail

### New emphasis

- hero image first
- concise metadata sections
- status chips and care state clearly visible
- actions grouped by importance
- avoid presenting all fields with equal weight

### Likely action layout

- primary action: edit / next relevant workflow if available
- secondary metadata below the fold

## 7.4 Add item

### New emphasis

The add flow should feel like a mobile capture / input task, not a plain form.

### Structure

1. media / image block
2. essential item fields
3. optional attributes grouped below
4. fixed or strongly emphasized bottom submit button

### Interaction notes

- Reduce visual fatigue in long forms.
- Group related fields into clear sections.

## 7.5 Suggest

### Current problem

The page is functional but visually flat and under-prioritized.

### New structure

1. **Context block**
   - weather summary
   - location cue if available

2. **Occasion selection block**
   - chips that feel like mobile segmented options

3. **Optional advanced adjustment**
   - manual temperature override folded beneath core controls

4. **Strong bottom CTA**
   - generate outfit

### Interaction notes

This page should feel like starting a task, with one clear forward action.

## 7.6 Suggest result

### New emphasis

The result page should privilege the conclusion first:

- what outfit was generated
- why it was suggested
- what the user can do next

### Structure

1. headline / recommendation summary
2. items in the outfit
3. reasoning summary
4. follow-up actions (accept / revisit / explore alternatives if supported)

## 7.7 Outfits list

### Current problem

The current screen mixes filter chips, search, month selection, and list rendering without a clear mobile hierarchy.

### New structure

1. page header
2. search bar
3. horizontal filter chip row
4. secondary month filter
5. result list

### Interaction notes

- The screen should feel like browsing saved looks.
- The list cards should emphasize occasion, status, date, and image strip.

## 7.8 Settings

### Current problem

The page reads like a backend configuration form rather than a mobile settings surface.

### New structure

Split into 3 sections:

1. **Connection & account**
   - API base URL
   - token status
   - sync / clear token actions

2. **Profile**
   - display name
   - location
   - timezone

3. **Preferences**
   - default occasion
   - temperature unit

### Interaction notes

- The save action should be the dominant page CTA.
- Secondary debug actions should remain accessible but visually subordinate.

## 8. Component design system

We do not need a large new component library, but we should standardize the miniapp around a small set of reusable mobile patterns.

## 8.1 Shared patterns to introduce or normalize

- `PageHeader`
- `SectionCard`
- `PrimaryButton`
- `SecondaryButton`
- `BottomActionBar`
- `FilterBar`
- `EmptyState`
- upgraded `ItemCard`
- upgraded `OutfitCard`
- upgraded `FilterSheet`

These can be implemented as explicit components or as a combination of components plus shared utility classes; the important thing is consistent behavior and styling.

## 8.2 ItemCard redesign

### Target behavior

- image-first composition
- stronger visual hierarchy
- title up top, metadata secondary
- status chips readable but restrained
- favorite marker subtle and mobile-appropriate

### Anti-goals

- tiny metadata rows
- dense multi-line labels that turn the card into a data table

## 8.3 OutfitCard redesign

### Target behavior

- occasion + status + date visible quickly
- image strip compact and neat
- reasoning shown as short summary, not a long paragraph wall

## 8.4 FilterSheet redesign

### Target behavior

- grouped controls
- clearer labels
- mobile sheet feeling rather than card-like form block
- explicit apply / reset affordances if state handling supports it cleanly

## 9. Visual system rules

## 9.1 Spacing

- increase vertical spacing between major sections
- reduce crowding between inline controls
- use a more consistent mobile spacing scale

## 9.2 Touch targets

All tappable controls should be mobile-friendly in both perceived and actual size.

## 9.3 Surface hierarchy

- page background slightly separated from card surfaces
- cards should feel lighter and less desktop-dashboard-like
- use fewer hard visual dividers

## 9.4 Typography

- shorter headings
- stronger section labels
- clearer primary vs secondary text contrast
- avoid desktop-style oversized dashboard titles except where truly useful

## 9.5 Chips and badges

- chips should read as touchable filters
- badges should read as state indicators
- do not style both the same way

## 10. Technical design notes

1. Keep current data-fetching hooks and service calls intact where possible.
2. Prefer localized page/component refactors over introducing a new app-wide state system.
3. Keep tab icons as static assets and wire them through Taro tab configuration.
4. Use shared SCSS tokens / utility classes where they reduce duplication.
5. Preserve current route structure.
6. Avoid custom tab bar complexity in this phase.

## 11. Testing and verification strategy

Before claiming implementation complete, verify at least:

1. `pnpm build:h5` passes for `miniapp/`
2. key screens render in H5 without layout breakage
3. native tab bar icons appear for all five tabs
4. primary mobile flows remain usable:
   - open home
   - browse wardrobe
   - open suggest and trigger generation
   - browse outfits
   - edit settings and save
5. empty states and loading states still render cleanly

## 12. Acceptance criteria

The design is successful when:

- the miniapp no longer feels like a shrunken desktop dashboard
- each page has one clear primary action
- tab bar icons are present and coherent
- common controls feel thumb-friendly
- pages use a unified mobile visual language
- business behavior remains intact
- the H5 build continues to work

## 13. Recommended implementation sequence

1. establish shared mobile visual foundation and tab icons
2. refactor shared cards / buttons / filter surfaces
3. refresh the five tab pages
4. refresh detail / add / result pages
5. verify H5 build and mobile usability across flows

