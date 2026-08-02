/// <reference types="vite/client" />
import { createRootRoute, HeadContent, Outlet, Scripts } from '@tanstack/react-router'
import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TooltipProvider } from '../components/ui/tooltip'
import { Nav } from '../components/nav'
import { ChatPanel } from '../components/chat/chat-panel'
import globalsCss from '../styles/globals.css?url'

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: 'utf-8' },
      { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      { title: 'Swingy - Trading Dashboard' },
      {
        name: 'description',
        content: 'Swing trading dashboard for Vietnamese stocks',
      },
    ],
    links: [
      { rel: 'stylesheet', href: globalsCss },
      {
        rel: 'stylesheet',
        href: 'https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&family=Geist+Mono&display=swap',
      },
      { rel: 'icon', href: '/icon.svg' },
    ],
  }),
  shellComponent: RootDocument,
  component: RootComponent,
})

function RootDocument({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <HeadContent />
      </head>
      <body
        className="font-sans antialiased"
        style={
          {
            '--font-geist-sans': "'Montserrat', sans-serif",
            '--font-geist-mono': "'Geist Mono', monospace",
          } as React.CSSProperties
        }
      >
        {children}
        <Scripts />
      </body>
    </html>
  )
}

function RootComponent() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000,
            refetchOnWindowFocus: false,
          },
        },
      })
  )

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={200}>
        <Nav />
        <Outlet />
        <ChatPanel />
      </TooltipProvider>
    </QueryClientProvider>
  )
}
