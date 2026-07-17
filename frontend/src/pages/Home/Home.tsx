import { lazy, Suspense } from 'react'
import { Link } from 'react-router-dom'
import { useCompetitions } from '@/features/competitions/useCompetitions'
import { useAthletes } from '@/features/athletes/useAthletes'
import { CompetitionCard } from '@/components/ui/CompetitionCard'
import { AthleteCard } from '@/components/ui/AthleteCard'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'

const ArmTable3D = lazy(() => import('@/components/model/ArmTable3D').then((m) => ({ default: m.ArmTable3D })))

export function Home() {
  const competitions = useCompetitions({ status: 'published', page_size: 3 })
  const athletes = useAthletes({ page_size: 4 })

  return (
    <div>
      {/* Hero — тезис: сила хвата спортсмена читается так же однозначно,
          как давление на манометре буровой. */}
      <section className="hero-scene overflow-hidden border-b border-steel-dim/30">
        <div className="relative z-10 mx-auto grid max-w-6xl gap-10 px-5 py-16 sm:py-24 lg:grid-cols-[1.3fr_1fr] lg:items-center">
          <div>
            <p className="text-eyebrow text-rust">Соревнования | Статистика | новости</p>
            <h1 className="mt-4 font-display text-4xl font-extrabold leading-[1.05] text-bone sm:text-5xl">
              Федерация Армрестлинга
              <br />
              <span className="text-brass">Атырауской области</span>
            </h1>
            <p className="mt-5 max-w-lg text-steel">
              Единая база спортсменов, клубов и турниров города Атырау по армрестлингу,
              новости, статистика спортсменов и итоги соревнований — от районных отборов
              до чемпионатов области, в одном месте.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/athletes" className="btn btn-primary">
                Спортсмены
              </Link>
              <Link to="/competitions" className="btn btn-secondary">
                Соревнования
              </Link>
            </div>
            <div className="mt-9 flex items-center gap-3 border-t border-steel-dim/20 pt-6">
              <img
                src="/brand/logo-atyrau-city.png"
                alt="Герб города Атырау"
                className="h-10 w-auto opacity-90"
              />
              <p className="font-mono text-xs leading-snug text-steel-dim">
                Атырауская область · Казахстан
              </p>
            </div>
          </div>
          <div className="relative">
            <div
              className="pointer-events-none absolute inset-0 -z-10 rounded-full blur-3xl"
              style={{
                background:
                  'radial-gradient(closest-side, rgba(201,162,39,0.22), rgba(193,85,44,0.12) 55%, transparent 75%)',
              }}
              aria-hidden="true"
            />
            <div className="table-shadow h-[320px] sm:h-[420px]">
              <Suspense
                fallback={
                  <div className="flex h-full items-center justify-center">
                    <span className="text-eyebrow animate-pulse text-steel">Загрузка модели…</span>
                  </div>
                }
              >
                <ArmTable3D />
              </Suspense>
            </div>
          </div>
        </div>
      </section>

      {/* Ближайшие/последние турниры */}
      <section className="mx-auto max-w-6xl px-5 py-14">
        <div className="flex items-end justify-between">
          <h2 className="font-display text-2xl text-bone">Турниры</h2>
          <Link to="/competitions" className="text-sm font-medium text-brass hover:text-brass-dim">
            все турниры →
          </Link>
        </div>
        <div className="rivet-line my-5" />

        {competitions.isLoading && <LoadingState label="Загрузка турниров" />}
        {competitions.isError && (
          <ErrorState message={(competitions.error as Error).message} onRetry={() => competitions.refetch()} />
        )}
        {competitions.data && competitions.data.items.length === 0 && (
          <EmptyState title="Опубликованных турниров пока нет" message="Загляните позже — здесь появятся результаты." />
        )}
        {competitions.data && competitions.data.items.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {competitions.data.items.map((c) => (
              <CompetitionCard key={c.id} competition={c} />
            ))}
          </div>
        )}
      </section>

      {/* Тизер спортсменов */}
      <section className="mx-auto max-w-6xl px-5 pb-16">
        <div className="flex items-end justify-between">
          <h2 className="font-display text-2xl text-bone">Спортсмены</h2>
          <Link to="/athletes" className="text-sm font-medium text-brass hover:text-brass-dim">
            вся база →
          </Link>
        </div>
        <div className="rivet-line my-5" />

        {athletes.isLoading && <LoadingState label="Загрузка спортсменов" />}
        {athletes.isError && (
          <ErrorState message={(athletes.error as Error).message} onRetry={() => athletes.refetch()} />
        )}
        {athletes.data && athletes.data.items.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {athletes.data.items.map((a) => (
              <AthleteCard key={a.id} athlete={a} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
