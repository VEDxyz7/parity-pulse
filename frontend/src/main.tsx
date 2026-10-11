import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App } from './App'
import { PresentationApp } from './PresentationApp'
import { LandingEntrance } from './landing/LandingEntrance'
import './styles.css'
import './ui/design-system.css'
import './ui/polish.css'

const client = new QueryClient()
const Workspace = new URLSearchParams(location.search).get('workspace') === 'verified' ? App : PresentationApp

createRoot(document.getElementById('root')!).render(
  <StrictMode><QueryClientProvider client={client}><LandingEntrance><Workspace /></LandingEntrance></QueryClientProvider></StrictMode>,
)
