const happyWindow = window as typeof window & {
  happyDOM?: {
    settings?: {
      disableIframePageLoading?: boolean
      navigation?: { disableChildFrameNavigation?: boolean }
    }
  }
}

const settings = happyWindow.happyDOM?.settings
if (settings) {
  settings.disableIframePageLoading = true
  if (settings.navigation) settings.navigation.disableChildFrameNavigation = true
}
