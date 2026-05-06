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
      {
        pagePath: 'pages/home/index',
        text: '首页',
        iconPath: 'assets/tabbar/home.png',
        selectedIconPath: 'assets/tabbar/home-active.png',
      },
      {
        pagePath: 'pages/wardrobe/index',
        text: '衣橱',
        iconPath: 'assets/tabbar/wardrobe.png',
        selectedIconPath: 'assets/tabbar/wardrobe-active.png',
      },
      {
        pagePath: 'pages/suggest/index',
        text: '建议',
        iconPath: 'assets/tabbar/suggest.png',
        selectedIconPath: 'assets/tabbar/suggest-active.png',
      },
      {
        pagePath: 'pages/outfits/index',
        text: '穿搭',
        iconPath: 'assets/tabbar/outfits.png',
        selectedIconPath: 'assets/tabbar/outfits-active.png',
      },
      {
        pagePath: 'pages/settings/index',
        text: '设置',
        iconPath: 'assets/tabbar/settings.png',
        selectedIconPath: 'assets/tabbar/settings-active.png',
      },
    ],
  },
} as const
