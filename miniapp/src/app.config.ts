export default {
  pages: [
    'pages/home/index',
    'pages/wardrobe/index',
    'pages/wardrobe/detail',
    'pages/wardrobe/add',
    'pages/suggest/index',
    'pages/suggest/result',
    'pages/outfits/index',
    'pages/settings/index',
  ],
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: '#ffffff',
    navigationBarTitleText: 'wardrowbe',
    navigationBarTextStyle: 'black',
  },
  tabBar: {
    color: '#6b7280',
    selectedColor: '#111827',
    backgroundColor: '#ffffff',
    borderStyle: 'black',
    list: [
      { pagePath: 'pages/home/index', text: 'Home' },
      { pagePath: 'pages/wardrobe/index', text: 'Wardrobe' },
      { pagePath: 'pages/suggest/index', text: 'Suggest' },
      { pagePath: 'pages/outfits/index', text: 'Outfits' },
      { pagePath: 'pages/settings/index', text: 'Settings' },
    ],
  },
} as const
