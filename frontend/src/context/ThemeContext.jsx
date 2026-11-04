import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

const ThemeContext = createContext(null)

function initialTheme() {
  try {
    const saved = localStorage.getItem('theme')
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    // storage unavailable
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(initialTheme)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    try {
      localStorage.setItem('theme', theme)
    } catch {
      // storage unavailable
    }
  }, [theme])

  const toggle = useCallback(() => setTheme((t) => (t === 'dark' ? 'light' : 'dark')), [])
  const value = useMemo(() => ({ theme, toggle }), [theme, toggle])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  return useContext(ThemeContext)
}

/** Resolved colors for Recharts (SVG attributes need concrete values). */
export function useChartColors() {
  const { theme } = useTheme()
  return useMemo(() => {
    const css = getComputedStyle(document.documentElement)
    const v = (name) => css.getPropertyValue(name).trim()
    return {
      series1: v('--series-1'),
      series2: v('--series-2'),
      grid: v('--grid'),
      axis: v('--text-3'),
      text: v('--text'),
      surface: v('--surface'),
      critical: v('--critical'),
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme])
}
