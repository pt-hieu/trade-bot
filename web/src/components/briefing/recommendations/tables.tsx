import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { ArrowRight, Eye, type LucideIcon } from 'lucide-react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../ui/table'
import type { Recommendation, RecAction } from '../../../types/index'
import { formatVNDK } from '../../../lib/utils'
import {
  ROW_BORDERS,
  ColumnInfo,
  TickerCell,
  ActionCell,
  RationaleCell,
  EodCell,
  ResultCell,
  PnlCell,
  AlertCell,
  calcRR,
} from './shared'
import type { SectionKey } from './shared'

// ── CTA config ──────────────────────────────────────────────────────────────
// Maps recommendation actions to deep-link targets so the briefing narrative
// connects directly to the execution workspace without a generic "go to Trading".

interface CtaConfig {
  to: '/trades' | '/watchlist'
  buildSearch: (rec: Recommendation) => Record<string, string | undefined>
  colorClass: string
  label: string
  icon: LucideIcon
}

const ENTRY_CTA: CtaConfig = {
  to: '/trades',
  buildSearch: (rec) => ({ ticker: rec.ticker, strategy: rec.strategy ?? undefined }),
  colorClass: 'text-emerald-400 hover:text-emerald-300',
  label: 'Execute',
  icon: ArrowRight,
}

const EXIT_CTA: CtaConfig = {
  to: '/trades',
  buildSearch: (rec) => ({ ticker: rec.ticker }),
  colorClass: 'text-rose-400 hover:text-rose-300',
  label: 'Execute',
  icon: ArrowRight,
}

const WATCH_CTA: CtaConfig = {
  to: '/watchlist',
  buildSearch: (rec) => ({ add: rec.ticker }),
  colorClass: 'text-sky-400 hover:text-sky-300',
  label: 'Watch',
  icon: Eye,
}

const ACTION_CTA: Partial<Record<RecAction, CtaConfig>> = {
  BUY: ENTRY_CTA, ADD: ENTRY_CTA, LIMIT_BUY: ENTRY_CTA,
  EXIT: EXIT_CTA, TRIM: EXIT_CTA, SELL: EXIT_CTA,
  WATCH: WATCH_CTA,
}

function RecCtaCell({ rec }: { rec: Recommendation }) {
  const cta = ACTION_CTA[rec.action]
  if (!cta) return <TableCell />

  const Icon = cta.icon
  return (
    <TableCell className="text-right">
      <Link
        to={cta.to}
        search={cta.buildSearch(rec) as any}
        className={`inline-flex items-center gap-1 text-xs font-medium transition-colors cursor-pointer ${cta.colorClass}`}
      >
        {cta.label}
        <Icon className="h-3 w-3" />
      </Link>
    </TableCell>
  )
}

// ── TOP PICKS: full trade setup ──────────────────────────────────────────────

function TopPicksTable({ recs }: { recs: Recommendation[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className="w-[70px]">Ticker</TableHead>
          <TableHead className="w-[80px]">Action</TableHead>
          <TableHead className="text-right w-[70px]">Entry</TableHead>
          <TableHead className="text-right w-[70px]">Stop</TableHead>
          <TableHead className="text-right w-[70px]">Target</TableHead>
          <TableHead className="text-right w-[50px]">R:R</TableHead>
          <TableHead className="text-center w-[80px]">
            <ColumnInfo label="Alert" tip="Live alert status from alert monitor. Active: watching for entry. Triggered: condition was hit during market hours." className="justify-center" />
          </TableHead>
          <TableHead className="text-right w-[70px]">EOD</TableHead>
          <TableHead className="text-right w-[90px]">
            <ColumnInfo label="Result" tip="WIN: target hit. LOSS: stop hit (intraday low breached stop). PENDING: entry hit, still open. MISSED: entry not reached." className="justify-end" />
          </TableHead>
          <TableHead className="text-right w-[60px]">
            <ColumnInfo label="P/L" tip="% change from entry to EOD close. Only calculated when entry was hit." className="justify-end" />
          </TableHead>
          <TableHead className="w-[70px]" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {recs.map((rec, i) => {
          const evalStatus = rec.evaluation?.status
          const borderClass = evalStatus ? ROW_BORDERS[evalStatus] ?? '' : ''
          const rr = calcRR(rec.entry_price_vnd, rec.stop_price_vnd, rec.target_price_vnd)
          return (
            <TableRow key={`${rec.ticker}-${i}`} className={borderClass}>
              <TickerCell ticker={rec.ticker} />
              <ActionCell action={rec.action} />
              <TableCell className="text-right font-mono tabular-nums text-xs">
                {formatVNDK(rec.entry_price_vnd)}
              </TableCell>
              <TableCell className="text-right font-mono tabular-nums text-xs text-rose-500">
                {formatVNDK(rec.stop_price_vnd)}
              </TableCell>
              <TableCell className="text-right font-mono tabular-nums text-xs text-emerald-500">
                {formatVNDK(rec.target_price_vnd)}
              </TableCell>
              <TableCell className="text-right font-mono tabular-nums text-xs">
                {rr ?? '—'}
              </TableCell>
              <AlertCell alerts={rec.alerts} />
              <EodCell evaluation={rec.evaluation} />
              <ResultCell evaluation={rec.evaluation} />
              <PnlCell evaluation={rec.evaluation} />
              <RecCtaCell rec={rec} />
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

// ── MY HOLDINGS: action + rationale + outcome ────────────────────────────────

function HoldingsTable({ recs }: { recs: Recommendation[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className="w-[70px]">Ticker</TableHead>
          <TableHead className="w-[80px]">Action</TableHead>
          <TableHead>Rationale</TableHead>
          <TableHead className="text-center w-[80px]">
            <ColumnInfo label="Alert" tip="Live alert status. Active: watching for trigger. Triggered: condition was hit." className="justify-center" />
          </TableHead>
          <TableHead className="text-right w-[70px]">EOD</TableHead>
          <TableHead className="text-right w-[90px]">
            <ColumnInfo label="Result" tip="HOLD: position maintained. EXIT: position closed. Evaluated by day change, not entry-based." className="justify-end" />
          </TableHead>
          <TableHead className="text-right w-[60px]">
            <ColumnInfo label="P/L" tip="Intraday % change (open to close) for the stock." className="justify-end" />
          </TableHead>
          <TableHead className="w-[70px]" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {recs.map((rec, i) => {
          const evalStatus = rec.evaluation?.status
          const borderClass = evalStatus ? ROW_BORDERS[evalStatus] ?? '' : ''
          return (
            <TableRow key={`${rec.ticker}-${i}`} className={borderClass}>
              <TickerCell ticker={rec.ticker} />
              <ActionCell action={rec.action} />
              <RationaleCell rationale={rec.rationale} />
              <AlertCell alerts={rec.alerts} />
              <EodCell evaluation={rec.evaluation} />
              <ResultCell evaluation={rec.evaluation} />
              <PnlCell evaluation={rec.evaluation} />
              <RecCtaCell rec={rec} />
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

// ── SKIP / LONG-TERM / OTHER: minimal ────────────────────────────────────────

function SimpleTableRow({ rec, index }: { rec: Recommendation; index: number }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <TableRow
      key={`${rec.ticker}-${index}`}
      className="cursor-pointer"
      onClick={() => setExpanded(!expanded)}
    >
      <TickerCell ticker={rec.ticker} />
      <ActionCell action={rec.action} />
      <TableCell className="text-xs text-muted-foreground align-top">
        <span className={expanded ? 'whitespace-normal break-words' : 'line-clamp-2 whitespace-normal break-words'}>
          {rec.rationale || '—'}
        </span>
      </TableCell>
    </TableRow>
  )
}

function SimpleTable({ recs }: { recs: Recommendation[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className="w-[70px]">Ticker</TableHead>
          <TableHead className="w-[80px]">Action</TableHead>
          <TableHead>Rationale</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {recs.map((rec, index) => (
          <SimpleTableRow key={`${rec.ticker}-${index}`} rec={rec} index={index} />
        ))}
      </TableBody>
    </Table>
  )
}

// ── Router ───────────────────────────────────────────────────────────────────

export function SectionTable({ section, recs }: { section: SectionKey; recs: Recommendation[] }) {
  switch (section) {
    case 'TOP_PICKS':
      return <TopPicksTable recs={recs} />
    case 'MY_HOLDINGS':
      return <HoldingsTable recs={recs} />
    default:
      return <SimpleTable recs={recs} />
  }
}
