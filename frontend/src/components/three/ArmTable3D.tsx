import { useEffect, useRef } from 'react'
import * as THREE from 'three'

/**
 * Процедурная 3D-модель турнирного стола для армрестлинга, медленно
 * вращающаяся на подиуме в стиле циферблата манометра (перекликается
 * с Gauge — те же насечки-деления, только по кругу постамента).
 *
 * Модель строится из примитивов (без внешних .glb), чтобы точно попадать
 * в палитру дизайн-системы и не тянуть лишний вес на главный экран.
 */

const COLORS = {
  ink: 0x0b0f10,
  inkSoft: 0x12181a,
  petrol: 0x12363b,
  petrol2: 0x1d4f56,
  rust: 0xc1552c,
  rustDim: 0x8f3f21,
  brass: 0xc9a227,
  steel: 0x92a0a6,
  steelDim: 0x5c666b,
  bone: 0xede7d8,
}

function buildDialTexture(): THREE.CanvasTexture {
  const size = 1024
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')!
  const cx = size / 2
  const cy = size / 2
  const rOuter = size * 0.48

  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, rOuter)
  grad.addColorStop(0, 'rgba(18,54,59,0.55)')
  grad.addColorStop(0.7, 'rgba(11,15,16,0.4)')
  grad.addColorStop(1, 'rgba(11,15,16,0)')
  ctx.fillStyle = grad
  ctx.beginPath()
  ctx.arc(cx, cy, rOuter, 0, Math.PI * 2)
  ctx.fill()

  // концентрические кольца
  ctx.strokeStyle = 'rgba(146,160,166,0.16)'
  ctx.lineWidth = 1.5
  for (let i = 1; i <= 3; i++) {
    ctx.beginPath()
    ctx.arc(cx, cy, rOuter * (i / 3.6), 0, Math.PI * 2)
    ctx.stroke()
  }

  // насечки по кругу, как деления манометра
  const ticks = 60
  for (let i = 0; i < ticks; i++) {
    const angle = (i / ticks) * Math.PI * 2
    const major = i % 5 === 0
    const rIn = rOuter * (major ? 0.86 : 0.9)
    const rOut = rOuter * 0.94
    ctx.strokeStyle = major ? 'rgba(201,162,39,0.55)' : 'rgba(146,160,166,0.28)'
    ctx.lineWidth = major ? 3 : 1.5
    ctx.beginPath()
    ctx.moveTo(cx + Math.cos(angle) * rIn, cy + Math.sin(angle) * rIn)
    ctx.lineTo(cx + Math.cos(angle) * rOut, cy + Math.sin(angle) * rOut)
    ctx.stroke()
  }

  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  return tex
}

function buildTable(): THREE.Group {
  const root = new THREE.Group()

  const felt = new THREE.MeshStandardMaterial({ color: COLORS.petrol, roughness: 0.85, metalness: 0.05 })
  const brass = new THREE.MeshStandardMaterial({ color: COLORS.brass, roughness: 0.35, metalness: 0.75 })
  const steel = new THREE.MeshStandardMaterial({ color: COLORS.steel, roughness: 0.4, metalness: 0.8 })
  const steelDark = new THREE.MeshStandardMaterial({ color: COLORS.steelDim, roughness: 0.5, metalness: 0.7 })
  const leather = new THREE.MeshStandardMaterial({ color: COLORS.inkSoft, roughness: 0.9, metalness: 0.02 })
  const rust = new THREE.MeshStandardMaterial({ color: COLORS.rust, roughness: 0.45, metalness: 0.5 })

  // --- постамент ---
  const foot = new THREE.Mesh(new THREE.CylinderGeometry(1.15, 1.3, 0.14, 48), steelDark)
  foot.position.y = -1.35
  root.add(foot)

  const column = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.36, 1.1, 32), steel)
  column.position.y = -0.75
  root.add(column)

  const collar = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.42, 0.08, 32), brass)
  collar.position.y = -0.22
  root.add(collar)

  // --- столешница ---
  const trim = new THREE.Mesh(new THREE.BoxGeometry(3.85, 0.09, 2.2), brass)
  trim.position.y = -0.14
  root.add(trim)

  const top = new THREE.Mesh(new THREE.BoxGeometry(3.6, 0.22, 1.95), felt)
  top.position.y = 0
  root.add(top)

  // --- центральный штырь захвата ---
  const pin = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.05, 0.42, 16), rust)
  pin.position.y = 0.32
  root.add(pin)

  const pinCap = new THREE.Mesh(new THREE.SphereGeometry(0.08, 16, 16), brass)
  pinCap.position.y = 0.53
  root.add(pinCap)

  // --- локтевые подушки ---
  const padGeom = new THREE.CylinderGeometry(0.32, 0.32, 0.07, 32)
  ;[-0.95, 0.95].forEach((x) => {
    const pad = new THREE.Mesh(padGeom, leather)
    pad.position.set(x, 0.145, 0)
    root.add(pad)
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.32, 0.015, 8, 32), brass)
    ring.position.set(x, 0.18, 0)
    ring.rotation.x = Math.PI / 2
    root.add(ring)
  })

  // --- боковые штыри-упоры для свободной руки ---
  const pegGeom = new THREE.CylinderGeometry(0.035, 0.04, 0.3, 12)
  ;[
    [-1.62, 0.62],
    [-1.62, -0.62],
    [1.62, 0.62],
    [1.62, -0.62],
  ].forEach(([x, z]) => {
    const peg = new THREE.Mesh(pegGeom, rust)
    peg.position.set(x, 0.26, z)
    root.add(peg)
  })

  // --- заклёпки по углам ---
  const rivetGeom = new THREE.SphereGeometry(0.035, 12, 12)
  ;[
    [-1.72, 0.9],
    [1.72, 0.9],
    [-1.72, -0.9],
    [1.72, -0.9],
  ].forEach(([x, z]) => {
    const rivet = new THREE.Mesh(rivetGeom, brass)
    rivet.position.set(x, 0.12, z)
    root.add(rivet)
  })

  root.traverse((obj) => {
    if (obj instanceof THREE.Mesh) {
      obj.castShadow = true
      obj.receiveShadow = true
    }
  })

  return root
}

export function ArmTable3D() {
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    const scene = new THREE.Scene()

    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 50)
    camera.position.set(0, 2.05, 4.6)
    camera.lookAt(0, -0.1, 0)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.05
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap
    container.appendChild(renderer.domElement)

    // студийный свет: тёплый ключевой (латунь), холодный заполняющий (сталь),
    // и контровой в цвете ржавчины для контура
    const key = new THREE.DirectionalLight(0xf3e3b0, 2.2)
    key.position.set(3, 4.2, 2.4)
    key.castShadow = true
    key.shadow.mapSize.set(1024, 1024)
    key.shadow.camera.near = 1
    key.shadow.camera.far = 12
    scene.add(key)

    const fill = new THREE.DirectionalLight(0x6f97a0, 0.55)
    fill.position.set(-3.5, 1.5, -1)
    scene.add(fill)

    const rim = new THREE.PointLight(0xc1552c, 6, 8, 2)
    rim.position.set(-1.4, 1.2, -2.6)
    scene.add(rim)

    const ambient = new THREE.AmbientLight(0x223338, 0.9)
    scene.add(ambient)

    // круговой "циферблат" под столом
    const dialTexture = buildDialTexture()
    const dial = new THREE.Mesh(
      new THREE.CircleGeometry(2.7, 64),
      new THREE.MeshBasicMaterial({ map: dialTexture, transparent: true, depthWrite: false }),
    )
    dial.rotation.x = -Math.PI / 2
    dial.position.y = -1.42
    scene.add(dial)

    const shadowCatcher = new THREE.Mesh(
      new THREE.CircleGeometry(2.7, 64),
      new THREE.ShadowMaterial({ opacity: 0.35 }),
    )
    shadowCatcher.rotation.x = -Math.PI / 2
    shadowCatcher.position.y = -1.41
    shadowCatcher.receiveShadow = true
    scene.add(shadowCatcher)

    const table = buildTable()
    table.rotation.y = Math.PI * 0.15
    scene.add(table)

    function resize() {
      if (!container) return
      const { clientWidth, clientHeight } = container
      if (clientWidth === 0 || clientHeight === 0) return
      camera.aspect = clientWidth / clientHeight
      camera.updateProjectionMatrix()
      renderer.setSize(clientWidth, clientHeight)
    }
    resize()

    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(container)

    let raf = 0
    const rotationSpeed = reduceMotion ? 0 : 0.14 // рад/сек — один оборот ~45с
    let last = performance.now()

    function animate(now: number) {
      const dt = (now - last) / 1000
      last = now
      table.rotation.y += rotationSpeed * dt
      renderer.render(scene, camera)
      raf = requestAnimationFrame(animate)
    }
    raf = requestAnimationFrame(animate)

    return () => {
      cancelAnimationFrame(raf)
      resizeObserver.disconnect()
      dialTexture.dispose()
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh) {
          obj.geometry.dispose()
          if (Array.isArray(obj.material)) {
            obj.material.forEach((m) => m.dispose())
          } else {
            obj.material.dispose()
          }
        }
      })
      renderer.dispose()
      if (renderer.domElement.parentElement === container) {
        container.removeChild(renderer.domElement)
      }
    }
  }, [])

  return (
    <div
      ref={containerRef}
      className="h-full w-full"
      role="img"
      aria-label="Трёхмерная модель турнирного стола для армрестлинга, медленно вращается"
    />
  )
}
