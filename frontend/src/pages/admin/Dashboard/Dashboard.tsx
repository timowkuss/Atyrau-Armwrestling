import { Link } from 'react-router-dom'
import { useAuth } from '@/features/auth/useAuth'

const SECTIONS = [
  { to: '/admin/clubs', title: 'РљР»СѓР±С‹', desc: 'РЎРѕР·РґР°РЅРёРµ Рё СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёРµ РєР»СѓР±РѕРІ С„РµРґРµСЂР°С†РёРё.', roles: ['super_admin', 'admin'] },
  { to: '/admin/coaches', title: 'РўСЂРµРЅРµСЂС‹', desc: 'РљР°СЂС‚РѕС‡РєРё С‚СЂРµРЅРµСЂРѕРІ, РїСЂРёРІСЏР·РєР° Рє РєР»СѓР±Р°Рј.', roles: ['super_admin', 'admin'] },
  { to: '/admin/athletes', title: 'РЎРїРѕСЂС‚СЃРјРµРЅС‹', desc: 'РџСЂРѕС„РёР»Рё, РІРёРґРёРјРѕСЃС‚СЊ РЅР° СЃР°Р№С‚Рµ, СЂСѓС‡РЅР°СЏ РїСЂР°РІРєР° СЃС‚Р°С‚РёСЃС‚РёРєРё.', roles: ['super_admin', 'admin'] },
  { to: '/admin/news', title: 'РќРѕРІРѕСЃС‚Рё', desc: 'РџСѓР±Р»РёРєР°С†РёРё С„РµРґРµСЂР°С†РёРё.', roles: ['super_admin', 'admin', 'editor'] },
  { to: '/admin/gallery', title: 'РњРµРґРёР°', desc: 'РђР»СЊР±РѕРјС‹, С„РѕС‚Рѕ Рё РІРёРґРµРѕ С‚СѓСЂРЅРёСЂРѕРІ.', roles: ['super_admin', 'admin', 'editor'] },
  { to: '/admin/competitions', title: 'РўСѓСЂРЅРёСЂС‹ (РёРЅС„Рѕ)', desc: 'РўРѕР»СЊРєРѕ РѕРїРёСЃР°РЅРёРµ, Р°С„РёС€Р°, СЂРµРіР»Р°РјРµРЅС‚. РЎРµС‚РєР° Рё СЂРµР·СѓР»СЊС‚Р°С‚С‹ вЂ” РёР· РґРµСЃРєС‚РѕРїР°.', roles: ['super_admin', 'admin'] },
]

export function AdminDashboard() {
  const { user } = useAuth()
  const visible = SECTIONS.filter((s) => user && s.roles.includes(user.role_code))

  return (
    <div>
      <p className="text-eyebrow text-rust">РџР°РЅРµР»СЊ СѓРїСЂР°РІР»РµРЅРёСЏ</p>
      <h1 className="mt-2 font-display text-2xl text-bone">Р—РґСЂР°РІСЃС‚РІСѓР№С‚Рµ, {user?.full_name}</h1>
      <p className="mt-2 text-steel">
        Р РѕР»СЊ В«{user?.role_code}В». РЎРµС‚РєР° С‚СѓСЂРЅРёСЂРѕРІ, СѓС‡Р°СЃС‚РЅРёРєРё Рё СЂРµР·СѓР»СЊС‚Р°С‚С‹ РјР°С‚С‡РµР№ СЂРµРґР°РєС‚РёСЂСѓСЋС‚СЃСЏ
        С‚РѕР»СЊРєРѕ РёР· РґРµСЃРєС‚РѕРї-РїСЂРёР»РѕР¶РµРЅРёСЏ РЅР° РїР»РѕС‰Р°РґРєРµ вЂ” Р·РґРµСЃСЊ С‚РѕР»СЊРєРѕ РёРЅС„РѕСЂРјР°С†РёРѕРЅРЅР°СЏ С‡Р°СЃС‚СЊ СЃР°Р№С‚Р°.
      </p>

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {visible.map((s) => (
          <Link key={s.to} to={s.to} className="plate rounded-[var(--radius-rivet)] p-5 transition-transform hover:-translate-y-0.5 hover:border-brass/50">
            <h2 className="font-display text-lg text-bone">{s.title}</h2>
            <p className="mt-1 text-sm text-steel">{s.desc}</p>
          </Link>
        ))}
      </div>
    </div>
  )
}
